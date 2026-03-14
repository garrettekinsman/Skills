#!/usr/bin/env python3
"""
Research Loop Orchestrator — the single correct flow for launching loops.

This script is the REFERENCE IMPLEMENTATION. Every loop launch should follow
this exact flow. If you're spawning a loop manually, copy these steps.

Usage (from skills/research-loops/):
    python3 scripts/run_loop.py --topic "AI singularity thesis" --budget 30 --model qwen3-coder

Or call the functions directly from the agent:
    from scripts.run_loop import preflight, get_next_id, build_task, register_loop
"""

import os
import sys
import json
import time
import sqlite3
import argparse
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
SKILL_DIR = Path(__file__).parent.parent
STATE_DIR = SKILL_DIR / "state"
LOOPS_DB = STATE_DIR / "loops.db"


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1: PRE-FLIGHT — verify everything works before spending tokens
# ═══════════════════════════════════════════════════════════════════════════════

def _inference_probe(litellm_url: str, model: str, timeout_sec: int = 90) -> dict:
    """
    Send a tiny completion request to verify the model actually generates tokens.
    
    This catches failures that /v1/models won't:
      - Model listed but Ollama OOM'd trying to load it
      - GPU driver crash / Vulkan error
      - Model file corrupted
      - LiteLLM proxy up but upstream Ollama down
    
    Uses max_tokens=5 to minimize cost/time. Timeout is 90s — generous
    because a cold start may need to load a 50GB+ model into VRAM first.
    Reports latency so you can see if it was a cold start vs warm.
    
    Returns:
        {"ok": True, "latency_ms": 1234, "tokens": 5}
        {"ok": False, "error": "description"}
    """
    import urllib.request
    import urllib.error
    
    url = litellm_url.rstrip("/") + "/v1/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "Say OK"}],
        "max_tokens": 5,
        "temperature": 0,
    }).encode()
    
    req = urllib.request.Request(url, data=payload, headers={
        "Authorization": f"Bearer {os.environ['LITELLM_API_KEY']}",
        "Content-Type": "application/json",
    })
    
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read())
            latency = int((time.time() - t0) * 1000)
            
            # Verify we got actual content back
            choices = data.get("choices", [])
            if not choices:
                return {"ok": False, "error": "Empty choices in response"}
            
            content = choices[0].get("message", {}).get("content", "")
            tokens = data.get("usage", {}).get("completion_tokens", 0)
            
            if not content.strip():
                return {"ok": False, "error": "Model returned empty content"}
            
            return {"ok": True, "latency_ms": latency, "tokens": tokens}
    
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()[:200]
        except Exception:
            pass
        return {"ok": False, "error": f"HTTP {e.code}: {body}"}
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"Connection failed: {e.reason}"}
    except TimeoutError:
        return {"ok": False, "error": f"Inference timed out after {timeout_sec}s — model may be loading or GPU crashed"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def preflight(model: str = "qwen3-coder") -> dict:
    """
    Verify all dependencies before launching. Returns dict with status.
    
    Checks:
      1. Required env vars exist
      2. LiteLLM is reachable and the model is available
      3. State DB exists and is writable
      4. Framework1 is reachable via SSH (optional but logged)
    
    Returns:
        {"ok": True/False, "errors": [...], "warnings": [...], "litellm_url": "..."}
    """
    result = {"ok": True, "errors": [], "warnings": [], "litellm_url": None}
    
    # 1. Environment variables
    required_env = {
        "LITELLM_URL": "LiteLLM API URL (e.g. http://100.112.143.23:4000)",
        "LITELLM_API_KEY": "LiteLLM API key",
    }
    optional_env = {
        "FRAMEWORK1_SSH_HOST": "Framework1 Tailscale IP for SSH health checks",
        "FRAMEWORK1_SSH_USER": "SSH username for Framework1",
    }
    
    for var, desc in required_env.items():
        val = os.environ.get(var)
        if not val:
            result["errors"].append(f"Missing env var: {var} — {desc}")
            result["ok"] = False
        elif var == "LITELLM_URL":
            result["litellm_url"] = val
    
    for var, desc in optional_env.items():
        if not os.environ.get(var):
            result["warnings"].append(f"Optional env var missing: {var} — {desc}")
    
    if not result["ok"]:
        return result
    
    # 2. LiteLLM reachability + model check
    try:
        import urllib.request
        url = result["litellm_url"].rstrip("/") + "/v1/models"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {os.environ['LITELLM_API_KEY']}"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            model_ids = [m["id"] for m in data.get("data", [])]
            if model not in model_ids:
                result["errors"].append(
                    f"Model '{model}' not found on LiteLLM. Available: {model_ids}"
                )
                result["ok"] = False
            else:
                result["available_models"] = model_ids
    except Exception as e:
        result["errors"].append(f"LiteLLM unreachable at {result['litellm_url']}: {e}")
        result["ok"] = False
    
    # 3. Live inference probe — confirm model actually generates tokens
    #    (catches: OOM, Ollama crash, model loaded but broken, GPU errors)
    if result["ok"]:
        try:
            probe_result = _inference_probe(result["litellm_url"], model)
            if not probe_result["ok"]:
                result["errors"].append(
                    f"Inference probe FAILED for '{model}': {probe_result['error']}"
                )
                result["ok"] = False
            else:
                result["probe_latency_ms"] = probe_result["latency_ms"]
                result["probe_tokens"] = probe_result["tokens"]
        except Exception as e:
            result["errors"].append(f"Inference probe exception: {e}")
            result["ok"] = False
    
    # 4. State DB
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(str(LOOPS_DB))
        conn.execute("""CREATE TABLE IF NOT EXISTS loops (
            id TEXT PRIMARY KEY,
            name TEXT,
            status TEXT DEFAULT 'pending',
            sprints_done INTEGER DEFAULT 0,
            sprints_max INTEGER DEFAULT 60,
            findings TEXT,
            cost_usd REAL DEFAULT 0.0,
            kwh REAL DEFAULT 0.0,
            started_at INTEGER,
            finished_at INTEGER,
            notes TEXT
        )""")
        conn.commit()
        conn.close()
    except Exception as e:
        result["errors"].append(f"State DB error: {e}")
        result["ok"] = False
    
    # 5. Framework1 SSH (optional — just a warning)
    ssh_host = os.environ.get("FRAMEWORK1_SSH_HOST")
    ssh_user = os.environ.get("FRAMEWORK1_SSH_USER")
    if ssh_host and ssh_user:
        try:
            import subprocess
            r = subprocess.run(
                ["ssh", "-i", os.environ.get("FRAMEWORK1_SSH_KEY", "~/.ssh/framework_key"),
                 "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no",
                 f"{ssh_user}@{ssh_host}", "echo alive"],
                capture_output=True, text=True, timeout=10
            )
            if r.returncode != 0:
                result["warnings"].append(f"Framework1 SSH failed: {r.stderr.strip()}")
        except Exception as e:
            result["warnings"].append(f"Framework1 SSH check error: {e}")
    
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2: LOOP ID — get next sequential ID from database
# ═══════════════════════════════════════════════════════════════════════════════

def get_next_id() -> str:
    """Get next loop ID (L0001, L0002, ...) from the SQLite database."""
    conn = sqlite3.connect(str(LOOPS_DB))
    row = conn.execute("SELECT id FROM loops ORDER BY id DESC LIMIT 1").fetchone()
    if row:
        num = int(row[0][1:]) + 1
    else:
        num = 1
    conn.close()
    return f"L{num:04d}"


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3: TASK PROMPT — build the sub-agent's instructions
# ═══════════════════════════════════════════════════════════════════════════════

def build_task(loop_id: str, topic: str, budget_min: int, extra_context: str = "") -> str:
    """
    Build the task prompt for the sub-agent.
    
    Key elements:
      - Numbered sprint counter (MIN_SPRINTS = budget_min * 2)
      - Role rotation (Researcher → Adversary → Synthesizer)
      - Never-stop-early enforcement
      - Security nonce system for state files
      - Output format specification
    
    Args:
        loop_id: e.g. "L0016"
        topic: research question / thesis
        budget_min: time budget in minutes
        extra_context: additional context to inject (prior research, etc.)
    
    Returns:
        Complete task prompt string
    """
    min_sprints = budget_min * 2
    findings_path = f"state/{loop_id}_findings.md"
    
    task = f"""You are a research loop agent. Loop ID: {loop_id}. Time budget: {budget_min} minutes.

## MISSION
{topic}

{f"## PRIOR CONTEXT{chr(10)}{extra_context}{chr(10)}" if extra_context else ""}

## TIME ENFORCEMENT (MANDATORY — NEVER STOP EARLY)
You MUST complete at least {min_sprints} numbered sprints before writing the final report.
Each sprint = search → analyze → challenge → write sprint summary.
Do NOT write the final report until {min_sprints} sprints are done.

Label every sprint:
```
--- SPRINT 1/{min_sprints}+ [RESEARCHER] ---
[content]
--- END SPRINT 1 ---
```

## SPRINT ROLES (rotate)
- **RESEARCHER** (sprints 1, 3, 5, ...): Deep-dive with web_search. Find data, prices, analyst views.
- **ADVERSARY** (sprints 2, 4, 6, ...): Challenge previous sprint's findings. What's the bear case?
- **SYNTHESIZER** (every 5th sprint): Consolidate into ranked recommendations with conviction levels.

If findings converge early → EXPAND SCOPE (adjacent sectors, second-order effects, historical parallels).

## OUTPUT
Write sprint summaries incrementally. After each synthesizer sprint, output:
```
=== SYNTHESIS SPRINT N ===
[Ranked findings with conviction levels 1-10]
===
```

Final report format:
```
# {loop_id} — [Topic]
## Date: [today] | Sprints: N | Time: X min
## Key Findings
## Adversarial Challenges
## Synthesized Recommendations
## Confidence: X/10
```

## TOOLS
Use web_search extensively for current data:
- Stock prices, market caps, P/E ratios
- Recent earnings, guidance, analyst targets
- Insider buying/selling, institutional flows
- Breaking news, geopolitical developments
- Industry reports, supply chain data

Start NOW. Sprint 1 begins."""

    return task


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 4: REGISTER — write loop to database before spawning
# ═══════════════════════════════════════════════════════════════════════════════

def register_loop(loop_id: str, name: str, budget_min: int, model: str, 
                   session_key: str = None) -> None:
    """Register a loop in the SQLite database."""
    conn = sqlite3.connect(str(LOOPS_DB))
    conn.execute(
        """INSERT OR REPLACE INTO loops 
           (id, name, status, sprints_done, sprints_max, started_at, notes)
           VALUES (?, ?, 'active', 0, ?, ?, ?)""",
        (loop_id, name, budget_min * 2, int(time.time()),
         f"model={model}, budget={budget_min}min, session={session_key or 'pending'}")
    )
    conn.commit()
    conn.close()


def complete_loop(loop_id: str, sprints_done: int, findings: str = None) -> None:
    """Mark a loop as completed in the database."""
    conn = sqlite3.connect(str(LOOPS_DB))
    conn.execute(
        """UPDATE loops SET status='completed', sprints_done=?, findings=?, 
           finished_at=? WHERE id=?""",
        (sprints_done, findings or "", int(time.time()), loop_id)
    )
    conn.commit()
    conn.close()


def fail_loop(loop_id: str, error: str) -> None:
    """Mark a loop as failed in the database."""
    conn = sqlite3.connect(str(LOOPS_DB))
    conn.execute(
        """UPDATE loops SET status='failed', notes=?, finished_at=? WHERE id=?""",
        (f"ERROR: {error}", int(time.time()), loop_id)
    )
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 5: NOTIFY — tell the group a loop is starting (NO topic, NO findings)
# ═══════════════════════════════════════════════════════════════════════════════

def build_start_notification(loop_id: str, model: str, budget_min: int) -> str:
    """
    Build the group notification message for loop start.
    
    RULE: NEVER include the research topic or any findings.
    Group only sees: ID, model, duration.
    """
    return (
        f"🔁 Research loop starting\n"
        f"• ID: {loop_id}\n"
        f"• Model: {model}\n"
        f"• Duration: {budget_min} min"
    )


def build_completion_notification(loop_id: str, status: str, duration_min: int = None) -> str:
    """
    Build the group notification for loop completion.
    
    RULE: NEVER include findings, summaries, or topic.
    Group only sees: ID, status, duration.
    """
    duration = f" ({duration_min}min)" if duration_min else ""
    icon = "✅" if status == "completed" else "❌"
    return f"{icon} Loop {loop_id} {status}{duration}"


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 6: SPAWN — the actual sessions_spawn call
# ═══════════════════════════════════════════════════════════════════════════════

def build_spawn_params(loop_id: str, topic: str, budget_min: int, 
                        model: str = "qwen3-coder", extra_context: str = "") -> dict:
    """
    Build the parameters for sessions_spawn().
    
    Returns a dict ready to be unpacked into sessions_spawn(**params).
    
    CRITICAL: model string MUST be "litellm/<model>" — without the prefix,
    OpenClaw silently falls back to cloud models.
    """
    task = build_task(loop_id, topic, budget_min, extra_context)
    
    return {
        "task": task,
        "label": f"{loop_id}-{_slugify(topic)[:30]}",
        "model": f"litellm/{model}",  # MUST have litellm/ prefix
        "mode": "run",
        "runTimeoutSeconds": (budget_min * 60) + 300,  # 5-min buffer
    }


def _slugify(text: str) -> str:
    """Convert text to a URL-safe label."""
    import re
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')


# ═══════════════════════════════════════════════════════════════════════════════
# COMPLETE FLOW — the exact sequence an agent should follow
# ═══════════════════════════════════════════════════════════════════════════════

def run_loop_flow(topic: str, budget_min: int, model: str = "qwen3-coder",
                   extra_context: str = "", dry_run: bool = False) -> dict:
    """
    Complete loop launch flow. Call this OR follow these steps manually.
    
    Returns:
        {
            "ok": True/False,
            "loop_id": "L0016",
            "session_key": "agent:...",
            "spawn_params": {...},
            "start_notification": "...",
            "errors": [...]
        }
    
    FLOW:
        1. preflight()          → verify LiteLLM, env vars, DB
        2. get_next_id()        → L0016
        3. build_spawn_params() → task prompt + model + timeout
        4. register_loop()      → write to DB as 'active'
        5. notify group         → ID + model + duration ONLY
        6. sessions_spawn()     → launch sub-agent
        7. (on completion)      → notify group: ID + status ONLY
        8. (deliver findings)   → DM to owner ONLY, never group
    
    ERROR PATHS:
        - preflight fails       → stop, report errors, don't spawn
        - LiteLLM unreachable   → stop, suggest: ssh framework1 sudo systemctl restart litellm
        - model not found       → stop, list available models
        - spawn fails           → mark loop as 'failed' in DB, notify group
        - loop times out        → OpenClaw kills it at runTimeoutSeconds, mark 'failed'
        - loop completes        → mark 'completed', deliver findings to DM
    """
    result = {
        "ok": False, "loop_id": None, "session_key": None,
        "spawn_params": None, "start_notification": None, "errors": []
    }
    
    # Phase 1: Pre-flight
    pf = preflight(model)
    if not pf["ok"]:
        result["errors"] = pf["errors"]
        return result
    if pf.get("warnings"):
        result["warnings"] = pf["warnings"]
    
    # Phase 2: Loop ID
    loop_id = get_next_id()
    result["loop_id"] = loop_id
    
    # Phase 3+6: Build spawn params
    spawn_params = build_spawn_params(loop_id, topic, budget_min, model, extra_context)
    result["spawn_params"] = spawn_params
    
    # Phase 4: Register
    register_loop(loop_id, topic[:100], budget_min, model)
    
    # Phase 5: Build notifications
    result["start_notification"] = build_start_notification(loop_id, model, budget_min)
    
    if dry_run:
        result["ok"] = True
        result["dry_run"] = True
        return result
    
    # Phase 6: Spawn would happen here via sessions_spawn()
    # The agent calls sessions_spawn(**spawn_params) after this function returns
    result["ok"] = True
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# CLI — for testing and manual runs
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Research Loop Orchestrator")
    parser.add_argument("--topic", required=False, help="Research question/thesis")
    parser.add_argument("--budget", type=int, default=15, help="Time budget in minutes")
    parser.add_argument("--model", default="qwen3-coder", help="LiteLLM model ID")
    parser.add_argument("--dry-run", action="store_true", help="Validate without spawning")
    parser.add_argument("--preflight-only", action="store_true", help="Only run pre-flight checks")
    args = parser.parse_args()
    
    if args.preflight_only:
        pf = preflight(args.model)
        print(json.dumps(pf, indent=2))
        sys.exit(0 if pf["ok"] else 1)
    
    if not args.topic:
        parser.error("--topic is required (unless using --preflight-only)")
    
    result = run_loop_flow(args.topic, args.budget, args.model, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, default=str))
    
    if result["ok"] and not result.get("dry_run"):
        print(f"\n✅ Ready to spawn. Call:")
        print(f"   sessions_spawn(**{json.dumps(result['spawn_params'], indent=2)})")
    elif not result["ok"]:
        print(f"\n❌ Pre-flight failed:")
        for e in result["errors"]:
            print(f"   • {e}")
        sys.exit(1)
