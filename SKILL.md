# Research Loop Skill v13-2026-03-03
*Universal multi-agent research framework. Spawns timed loops on local compute.*
→ Full protocol, security system, templates: **REFERENCE.md**

---

## Hard Rules (non-negotiable)

1. **Local compute first** — always `model="litellm/qwen3-coder"` in sessions_spawn
2. **Time budget is a commitment** — loops run until clock expires, never stop early
3. **Explicit sprint counter** — numbered sprints in task prompt, `MIN_SPRINTS = budget_min * 2`
4. **Henry's nonce system** — session nonce + wrap_external() in every loop task → REFERENCE.md § Security
5. **Sanitize before Claude reads** — all local model output through model_output_sanitizer → REFERENCE.md § Sanitizer
6. **Never put research topic in group notification** — model + duration + ID only

---

## Pre-Flight Checklist

```bash
echo $LITELLM_URL $LITELLM_API_KEY $FRAMEWORK1_SSH_HOST $FRAMEWORK1_SSH_USER
ls state/loops.db
curl -s $LITELLM_URL/v1/models | python3 -c "import json,sys; print('OK:', len(json.load(sys.stdin)['data']), 'models')"
```
→ If anything missing: REFERENCE.md § Setup

---

## Script Index

| Script | What it does |
|---|---|
| `loop_status.py --discord` | Full dashboard — credits, models, APIs, energy, loops |
| `loop_status.py` | Same, plain text |
| `loops.py status` | Compact loop list from SQLite |
| `loops.py launch <config.json>` | Launch loop from config file |
| `api_usage.py` | Scan session transcripts for real spend |
| `model_output_sanitizer.py` | Sanitize local model output before Claude reads it |
| `telegram_fetch.py --hours 4` | OSINT fetch (subagent only, limit 50) |
| `generate_config.py` | Generate loop config from template |

---

## Spawn Template (copy this every time)

```python
# 1. Get next loop ID
import sqlite3
conn = sqlite3.connect('state/loops.db')
row = conn.execute('SELECT id FROM loops ORDER BY id DESC LIMIT 1').fetchone()
LOOP_ID = f"L{int(row[0][1:])+1:04d}" if row else "L0001"
conn.close()

# 2. Notify group (NO topic)
message(channel="discord", target="$LOOP_NOTIFICATION_CHANNEL",
    message=f"🔁 Research loop starting\n• ID: {LOOP_ID}\n• Model: qwen3-coder (Framework1)\n• Duration: X min")

# 3. Spawn
sessions_spawn(task=TASK_PROMPT, label=f"{LOOP_ID}-topic",
    model="litellm/qwen3-coder", mode="run",
    runTimeoutSeconds=time_budget_sec + 300)

# 4. Register
from loop_status import get_db, register_loop
conn = get_db(); register_loop(conn, LOOP_ID, 'topic', sprints_max=999); conn.close()
```
→ Full task prompt template: REFERENCE.md § Task Prompt

---

## Quick Reference

| Item | Value |
|---|---|
| Primary model | `litellm/qwen3-coder` |
| Fallback model | `xai/grok-3-fast` |
| State DB | `state/loops.db` |
| Findings dir | `state/` |
| Notification channel | `$LOOP_NOTIFICATION_CHANNEL` |
| Framework1 SSH | `$FRAMEWORK1_SSH_USER@$FRAMEWORK1_SSH_HOST` |

---

## When Things Break

| Symptom | Fix |
|---|---|
| Loop uses cloud not local | Model string must be `"litellm/qwen3-coder"` not `"qwen3-coder"` |
| Loop finishes in 2 min | Use numbered sprint counter in task prompt → REFERENCE.md § Time Enforcement |
| LiteLLM not responding | `ssh framework1 sudo systemctl restart litellm` |
| loop_status SSH fails | Check `FRAMEWORK1_SSH_USER` env var is set to `gk` |
| Nonce mismatch on state read | State file compromised — halt, don't use findings |
| model_output_sanitizer blocked | Discard output, do NOT pass to Claude |

→ Full troubleshooting: REFERENCE.md § Troubleshooting

---

## CHANGELOG
- `2026-03-03 v13` — Refactored to DML skill architecture: SKILL.md → 60 lines, all protocol/templates/security moved to REFERENCE.md. Added `.gitignore` (was missing after dir flatten). Sanitized PII (IP, SSH user, Discord channel, cluster URL, tickers, collaborator names). Model string fixed to `litellm/qwen3-coder`.
- `2026-03-03 v12` — Local compute first, Henry's security system, time enforcement, setup checklist, loop start notification
- `2026-03-01 v11` — Relay engine, multi-agent relay runtime
- `2026-03-01 v10` — Time-bound loops, never-stop-early enforcement
- `2026-03-01 v9` — Dashboard, Framework1 SSH health, energy tracking
- `2026-03-01 v8` — Security architecture, session nonce system
- `2026-02-25 v7` — Never stop early rule
- `2026-02-23 v6` — Generalized multi-domain framework
- `2026-02-14 v5` — Live data only, fixed 45x cost reporting error
- `2026-02-13 v4` — Bias-resistant exploration framework
