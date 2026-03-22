"""
orchestrator.py — Thin loop relay orchestrator.
Spawns workers via CLI, polls for completion,
manages checkpoints, generates batons, handles crash recovery.

Python 3.9 compatible. No external deps.

⚠️ WARNING (2026-03-04): The _spawn_worker() method in this file uses
`openclaw sessions spawn --task-file` which DOES NOT EXIST as a CLI command.
This is a hallucinated API. Use orchestrator_cli.py instead, which subclasses
this orchestrator and replaces spawn/poll with the correct synchronous mechanism:

    openclaw agent --session-id <id> --message <prompt> --json --timeout 300

orchestrator_cli.py is the production-ready version. This file is kept for
reference and as the base class.

Usage:
    python3 orchestrator_cli.py --config job_config.json  # USE THIS
    python3 orchestrator.py --config job_config.json      # BROKEN SPAWN
    python3 orchestrator.py --resume JOB_ID
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

# Add project dir to path so we can import siblings
sys.path.insert(0, str(Path(__file__).parent))

from checkpoint_manager import CheckpointManager, STALE_SPRINT_MINUTES, CONVERGENCE_THRESHOLD
from baton import Baton, _call_litellm
from worker_prompt_template import render_worker_prompt, render_conclusion_prompt, get_domain_extras

# ─── Constants ────────────────────────────────────────────────────────────────

SOFT_BUDGET_FRACTION = 0.75   # worker self-stops at 75% of token budget
HARD_BUDGET_FRACTION = 0.94   # orchestrator kills at 94%
SUMMARIZE_EVERY_K = 5         # digest every K sprints (start at sprint 10)
SUMMARIZE_START_SPRINT = 10   # don't summarize before this sprint

POLL_INTERVAL_SEC = 15        # how often to poll session status
MAX_POLL_RETRIES = 3          # retry session status poll this many times on error

OPENCLAW_CLI = os.environ.get("OPENCLAW_CLI", "openclaw")


# ─── Orchestrator ─────────────────────────────────────────────────────────────

class Orchestrator:
    def __init__(self, config: dict, db_path: Optional[str] = None):
        self.config = config
        self.job_id: str = config.get("job_id") or str(uuid.uuid4())
        self.domain: str = config.get("domain", "research")
        self.max_sprints: int = config.get("max_sprints", 50)
        self.time_budget_sec: int = config.get("time_budget_seconds", 3600 * 4)
        self.token_budget: int = config.get("token_budget", 80000)
        self.model: str = config.get("model", "anthropic/claude-sonnet-4-6")

        self.cm = CheckpointManager(db_path)
        self.start_time = time.time()
        self.session_id = f"orchestrator:{self.job_id[:8]}:{int(self.start_time)}"

    @property
    def elapsed_sec(self) -> float:
        return time.time() - self.start_time

    @property
    def time_remaining_sec(self) -> int:
        return max(0, int(self.time_budget_sec - self.elapsed_sec))

    def run(self) -> None:
        """Main orchestrator loop. Runs until done or time budget exhausted."""
        print(f"[orchestrator] Starting job {self.job_id} (domain={self.domain})", flush=True)

        # Register job (idempotent)
        self.cm.create_job(self.job_id, self.domain, {
            **self.config,
            "job_id": self.job_id,
            "orchestrator_started_utc": _utcnow(),
        })

        # Crash recovery: check for existing state
        resume = self.cm.resume_job(self.job_id)
        print(f"[orchestrator] Resume state: action={resume['action']}, next_sprint={resume['next_sprint']}", flush=True)

        if resume["action"] == "already_complete":
            print(f"[orchestrator] Job already complete ({resume['status']}). Nothing to do.", flush=True)
            return

        if resume["action"] == "wait":
            print(f"[orchestrator] Sprint {resume['next_sprint']} still running "
                  f"(worker={resume.get('worker_session_id')}). "
                  f"Waiting for completion...", flush=True)
            result = self._wait_for_running_sprint(resume["next_sprint"],
                                                    resume.get("worker_session_id", ""))
            if not result:
                print(f"[orchestrator] Sprint {resume['next_sprint']} timed out — marking crashed.", flush=True)
                self.cm.mark_zombie(self.job_id)
                resume = self.cm.resume_job(self.job_id)

        current_sprint = resume["next_sprint"] or 1
        baton_json = resume.get("baton_json")

        # If no baton yet, create initial one
        if baton_json is None:
            initial_baton = Baton.initial(
                self.job_id, self.domain, self.config,
                orchestrator_session_id=self.session_id,
            )
            baton_json = initial_baton.to_json()

        # Main loop
        while True:
            if self.time_remaining_sec < 120:
                print(f"[orchestrator] Time budget exhausted. Stopping.", flush=True)
                break

            if current_sprint > self.max_sprints:
                print(f"[orchestrator] Reached max sprints ({self.max_sprints}). Stopping.", flush=True)
                self.cm.complete_job(self.job_id, "complete")
                break

            # Check convergence
            baton = Baton.from_json(baton_json)
            if (baton.loop_health.consecutive_no_progress_sprints >= CONVERGENCE_THRESHOLD
                    or baton.loop_health.termination_triggered):
                print(f"[orchestrator] Convergence detected. Running conclusion sprint.", flush=True)
                baton_json = self._run_conclusion_sprint(current_sprint, baton_json)
                self.cm.complete_job(self.job_id, "converged")
                break

            print(f"[orchestrator] Starting sprint {current_sprint}...", flush=True)
            baton_json = self._run_sprint(current_sprint, baton_json)

            if baton_json is None:
                print(f"[orchestrator] Sprint {current_sprint} failed — aborting.", flush=True)
                break

            # Maybe summarize
            baton_json = self._maybe_summarize(current_sprint, baton_json)

            current_sprint += 1

        print(f"[orchestrator] Done. Elapsed: {self.elapsed_sec:.0f}s", flush=True)

    def _run_sprint(self, sprint_num: int, baton_json: str) -> Optional[str]:
        """
        Run one sprint: spawn worker, poll, collect results, build next baton.
        Returns updated baton_json or None on unrecoverable failure.
        """
        soft = int(self.token_budget * SOFT_BUDGET_FRACTION)
        hard = int(self.token_budget * HARD_BUDGET_FRACTION)

        baton = Baton.from_json(baton_json)

        # Render worker prompt
        prompt = render_worker_prompt(
            domain=self.domain,
            baton_json=baton_json,
            sprint_num=sprint_num,
            time_remaining_seconds=self.time_remaining_sec,
            token_budget=self.token_budget,
            soft_budget=soft,
            hard_budget=hard,
            db_path=str(self.cm.db_path),
            job_id=self.job_id,
            worker_prompt_version=self.config.get("worker_prompt_version", "v1"),
            extra_instructions=get_domain_extras(self.domain),
        )

        # Spawn worker
        session_id = self._spawn_worker(sprint_num, prompt)
        if not session_id:
            print(f"[orchestrator] Failed to spawn worker for sprint {sprint_num}.", flush=True)
            return None

        # Record sprint start
        self.cm.start_sprint(self.job_id, sprint_num, session_id, self.session_id)
        print(f"[orchestrator] Sprint {sprint_num} running (session={session_id})", flush=True)

        # Poll until done or hard limit
        handoff_type, tokens_used = self._poll_until_done(session_id, sprint_num)
        cost_usd = self._estimate_cost(tokens_used)

        print(f"[orchestrator] Sprint {sprint_num} complete: "
              f"handoff={handoff_type}, tokens={tokens_used}, cost=${cost_usd:.4f}", flush=True)

        # Read findings that the worker wrote to DB (worker writes directly)
        # Orchestrator only needs to close out the sprint record
        # Get findings written during this sprint
        findings_in_db = self.cm.get_findings(self.job_id, sprint_nums=[sprint_num])

        # complete_sprint also builds the baton
        new_baton = self.cm.complete_sprint(
            job_id=self.job_id,
            sprint_num=sprint_num,
            findings=findings_in_db,  # pass through what's already in DB
            cost_usd=cost_usd,
            handoff_type=handoff_type,
            tokens_consumed=tokens_used,
        )

        return new_baton.to_json()

    def _run_conclusion_sprint(self, sprint_num: int, baton_json: str) -> Optional[str]:
        """Run a conclusion/synthesis sprint."""
        prompt = render_conclusion_prompt(
            domain=self.domain,
            baton_json=baton_json,
            sprint_num=sprint_num,
            job_id=self.job_id,
            db_path=str(self.cm.db_path),
        )

        session_id = self._spawn_worker(sprint_num, prompt, label_suffix="conclusion")
        if not session_id:
            return baton_json

        self.cm.start_sprint(self.job_id, sprint_num, session_id, self.session_id)
        handoff_type, tokens_used = self._poll_until_done(session_id, sprint_num)
        cost_usd = self._estimate_cost(tokens_used)

        findings_in_db = self.cm.get_findings(self.job_id, sprint_nums=[sprint_num])
        new_baton = self.cm.complete_sprint(
            job_id=self.job_id,
            sprint_num=sprint_num,
            findings=findings_in_db,
            cost_usd=cost_usd,
            handoff_type=handoff_type,
            tokens_consumed=tokens_used,
        )
        return new_baton.to_json()

    def _spawn_worker(self, sprint_num: int, prompt: str,
                      label_suffix: str = "") -> Optional[str]:
        """
        Spawn a worker session via the openclaw CLI.
        Returns session ID string, or None on failure.

        openclaw sessions spawn --task "..." --label "..." --model "..."
        """
        label = f"loop-{self.job_id[:8]}-s{sprint_num}"
        if label_suffix:
            label += f"-{label_suffix}"

        # Write prompt to tmp file to avoid shell quoting issues
        import tempfile
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="relay-prompt-")
        try:
            with os.fdopen(tmp_fd, "w") as f:
                f.write(prompt)

            cmd = [
                OPENCLAW_CLI, "sessions", "spawn",
                "--task-file", tmp_path,
                "--label", label,
                "--model", self.model,
                "--output-json",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if result.returncode != 0:
            print(f"[orchestrator] sessions spawn failed: {result.stderr}", flush=True)
            return None

        # Parse session ID from JSON output
        try:
            data = json.loads(result.stdout.strip())
            # Expected: {"session_id": "...", "label": "..."}
            return data.get("session_id") or data.get("id")
        except (json.JSONDecodeError, KeyError):
            # Try to find session ID in plain text output
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("agent:") or "subagent:" in line:
                    return line
            print(f"[orchestrator] Could not parse session ID from: {result.stdout[:200]}", flush=True)
            return None

    def _poll_until_done(self, session_id: str, sprint_num: int) -> tuple:
        """
        Poll the worker session until it's done or hard budget is hit.
        Returns (handoff_type, tokens_used).
        """
        hard = int(self.token_budget * HARD_BUDGET_FRACTION)
        tokens_used = 0
        errors = 0
        sprint_deadline = time.time() + STALE_SPRINT_MINUTES * 60

        while True:
            if time.time() > sprint_deadline:
                print(f"[orchestrator] Sprint {sprint_num} exceeded deadline — force-killing.", flush=True)
                self._kill_session(session_id)
                return "forced", tokens_used

            time.sleep(POLL_INTERVAL_SEC)

            status = self._get_session_status(session_id)
            if status is None:
                errors += 1
                if errors >= MAX_POLL_RETRIES:
                    print(f"[orchestrator] Lost contact with session {session_id}.", flush=True)
                    return "forced", tokens_used
                continue

            errors = 0
            tokens_used = status.get("tokens_consumed", 0)  # SOURCE: session status API
            is_done = status.get("done", False) or status.get("status") == "complete"

            if tokens_used > hard:
                print(f"[orchestrator] Token hard limit hit ({tokens_used} > {hard}). Killing.", flush=True)
                self._kill_session(session_id)
                return "forced", tokens_used

            if is_done:
                # Check if worker reported budget_exhausted
                handoff = status.get("handoff_type", "clean")
                return handoff, tokens_used

    def _get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session status via openclaw CLI.
        Returns dict or None on error.
        SOURCE: openclaw sessions status API
        """
        cmd = [OPENCLAW_CLI, "sessions", "status", session_id, "--output-json"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                return None
            return json.loads(result.stdout.strip())
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            return None

    def _kill_session(self, session_id: str) -> None:
        """Kill a worker session."""
        cmd = [OPENCLAW_CLI, "sessions", "kill", session_id]
        try:
            subprocess.run(cmd, capture_output=True, timeout=10)
        except (subprocess.TimeoutExpired, OSError):
            pass

    def _wait_for_running_sprint(self, sprint_num: int,
                                  worker_session_id: str) -> bool:
        """
        Wait for an already-running sprint to complete (orchestrator crash recovery).
        Returns True if sprint completed, False if timed out.
        """
        deadline = time.time() + STALE_SPRINT_MINUTES * 60
        print(f"[orchestrator] Waiting for sprint {sprint_num} (session={worker_session_id})...", flush=True)

        while time.time() < deadline:
            time.sleep(POLL_INTERVAL_SEC)

            # Check DB for sprint completion
            row = self.cm.conn.execute(
                "SELECT status FROM sprints WHERE job_id = ? AND sprint_num = ?",
                (self.job_id, sprint_num)
            ).fetchone()
            if row and row[0] in ("complete", "budget_exhausted", "forced"):
                return True

            # Also check session directly
            if worker_session_id:
                status = self._get_session_status(worker_session_id)
                if status and (status.get("done") or status.get("status") == "complete"):
                    return True

        return False

    def _maybe_summarize(self, sprint_num: int, baton_json: str) -> str:
        """
        Run progressive summarization every K sprints (starting at sprint 10).
        Uses gpt-oss:20b via LiteLLM. Updates digest in DB and baton.
        """
        if sprint_num < SUMMARIZE_START_SPRINT:
            return baton_json
        if sprint_num % SUMMARIZE_EVERY_K != 0:
            return baton_json

        print(f"[orchestrator] Running summarization at sprint {sprint_num}...", flush=True)

        range_start = max(1, sprint_num - SUMMARIZE_EVERY_K + 1)
        sprint_nums = list(range(range_start, sprint_num + 1))
        findings = self.cm.get_findings(self.job_id, sprint_nums=sprint_nums)

        if not findings:
            print(f"[orchestrator] No findings in sprint range {sprint_nums} — skipping summarization.", flush=True)
            return baton_json

        baton = Baton.from_json(baton_json)
        existing_digest = baton.digest.text if baton.digest else ""

        findings_text = "\n\n".join(
            f"[Sprint {f['sprint_num']}][{f.get('source', 'unknown')}] {f['content']}"
            for f in findings[:50]  # cap at 50 to stay under 16k
        )

        prompt = (
            "You are a research summarizer. Compress these sprint findings into a single paragraph "
            "(max 400 words) that preserves all key claims with their sources. "
            "If there is an existing digest, EXTEND it rather than replacing it. "
            "Be specific — include actual claims, not vague themes.\n\n"
        )
        if existing_digest:
            prompt += f"EXISTING DIGEST:\n{existing_digest}\n\n"

        prompt += f"NEW FINDINGS (sprints {range_start}-{sprint_num}):\n{findings_text}\n\nUPDATED DIGEST:"

        summarize_model = self.config.get("summarize_model", "gpt-oss:20b")
        digest_text = _call_litellm(summarize_model, prompt, timeout=120)

        if digest_text is None:
            print(f"[orchestrator] Summarizer unreachable — keeping existing digest.", flush=True)
            return baton_json

        # Score the digest
        from baton import _score_digest
        key_findings = [f["content"][:200] for f in findings[:10]]
        quality_score = _score_digest(digest_text, key_findings, summarize_model)

        print(f"[orchestrator] Digest quality score: {quality_score:.2f}", flush=True)

        # If quality degraded, keep old digest and extend instead of replacing
        if baton.digest and quality_score < 0.70:
            print(f"[orchestrator] Digest quality below 0.70 — keeping previous digest.", flush=True)
            return baton_json

        # Store digest
        self.cm.store_digest(
            job_id=self.job_id,
            sprint_num=sprint_num,
            content=digest_text,
            model=summarize_model,
            sprint_range=(range_start, sprint_num),
            quality_score=quality_score,
        )

        # Rebuild baton with new digest
        updated_baton = self.cm.get_baton(self.job_id)
        return updated_baton if updated_baton else baton_json

    def _estimate_cost(self, tokens: int) -> float:
        """
        Rough cost estimate. Uses known pricing for common models.
        SOURCE: hardcoded rate table (Anthropic/OpenAI published pricing as of 2026-03-01)
        This is an ESTIMATE — real cost tracked via API invoices.
        """
        rates = {
            "anthropic/claude-sonnet-4-6": 3.0 / 1_000_000,  # $3/Mtok blended approx
            "anthropic/claude-opus-4": 15.0 / 1_000_000,
            "gpt-oss:20b": 0.2 / 1_000_000,
            "qwen3-coder": 0.5 / 1_000_000,
        }
        rate = rates.get(self.model, 3.0 / 1_000_000)
        return tokens * rate


# ─── Entry point ──────────────────────────────────────────────────────────────

def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Loop Relay Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 orchestrator.py --config research_job.json
  python3 orchestrator.py --resume abc12345-job-id
  python3 orchestrator.py --config job.json --db /path/to/swarm.db
        """,
    )
    parser.add_argument("--config", help="Path to job config JSON file")
    parser.add_argument("--resume", help="Resume existing job by ID")
    parser.add_argument("--db", help="Path to swarm.db (overrides default)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print first worker prompt and exit")
    args = parser.parse_args()

    if args.resume and not args.config:
        # Resuming existing job — load config from DB
        cm = CheckpointManager(args.db)
        job = cm.get_job(args.resume)
        if job is None:
            print(f"Error: Job {args.resume} not found in DB.", file=sys.stderr)
            sys.exit(1)
        config = json.loads(job["config_json"])
        config["job_id"] = args.resume
    elif args.config:
        with open(args.config) as f:
            config = json.load(f)
        if args.resume:
            config["job_id"] = args.resume
    else:
        parser.print_help()
        sys.exit(1)

    orch = Orchestrator(config, db_path=args.db)

    if args.dry_run:
        baton = Baton.initial(orch.job_id, orch.domain, config)
        prompt = render_worker_prompt(
            domain=orch.domain,
            baton_json=baton.to_json(),
            sprint_num=1,
            time_remaining_seconds=config.get("time_budget_seconds", 14400),
            token_budget=config.get("token_budget", 80000),
            job_id=orch.job_id,
            extra_instructions=get_domain_extras(orch.domain),
        )
        print(prompt)
        return

    try:
        orch.run()
    except KeyboardInterrupt:
        print("\n[orchestrator] Interrupted by user. State is in DB — resume with:", flush=True)
        print(f"  python3 orchestrator.py --resume {orch.job_id}", flush=True)
        sys.exit(0)
    finally:
        orch.cm.close()


if __name__ == "__main__":
    main()
