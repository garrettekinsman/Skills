# Research Loops — Collaborator Guide

**Universal multi-agent research framework for any problem domain.**
Financial markets, technical architecture, OSINT, scientific investigation — if it can be researched, loops can do it.

---

## Design Goals

### Built for Local AI Infrastructure

This framework is designed to **maximize the use of local AI compute** — running as much work as possible on self-hosted models (Ollama, LiteLLM, custom endpoints) before falling back to cloud APIs.

- **Researcher and Adversary roles** run on local models (e.g. `qwen3-coder`, `gpt-oss`) — the heavy, repetitive work that would burn cloud budget fast
- **Synthesizer role** uses cloud Claude for final judgment and coherent output — the step where model quality matters most
- **Cost reduction target**: 80-90% fewer cloud tokens vs. a naive all-cloud loop
- **Configure your local endpoint** in `configs/example.json` under `"local_model"`

This means a 400K token research loop that would cost ~$12 on Claude alone runs for under $1 with local infrastructure handling the bulk of the work.

### Hardened Against Prompt Injection

Research loops are a high-value attack surface — they fetch untrusted content from the internet and route it through multiple agent turns. Significant effort has gone into reducing injection risk at every seam.

**What we did:**

1. **Tool-level sanitization** — external content is sanitized *before* the agent ever sees it. The web_fetch intercept strips injection patterns, homoglyphs, markdown image exfiltration vectors (CVE-2025-32711), and known LLM trigger phrases before content enters the agent context.

2. **Session nonce continuity** — each loop session gets a unique nonce embedded in the system prompt. All external content arrives wrapped in nonce-tagged XML (`<LOOP_EXTERNAL_{nonce}>...`). Anything claiming to be instructions *outside* that wrapper is structurally wrong — the model treats it as injected content regardless of what it says. The nonce doesn't need to be secret; the protection comes from the structure.

3. **Cross-turn accumulation detection** — single-fetch sanitization isn't enough. An attacker can fragment a payload across multiple pages (page 1 plants a partial phrase, page 5 completes it). The accumulated sprint summary is re-scanned before being written to state.

4. **State file chain-of-custody** — the session nonce is written into every state file. On re-read, the nonce is verified. A compromised state file can't silently re-enter the pipeline next sprint.

5. **Mandatory local model sanitization** — when a local model processes content and hands off to Claude, the output goes through `model_output_sanitizer.py`. This is mandatory, not optional — local models are treated as untrusted.

These aren't guarantees — prompt injection in agentic pipelines is a structurally hard problem. But these layers mean an attacker needs to simultaneously bypass sanitization, forge the session nonce, and survive cross-turn detection. That's meaningfully harder than a naive loop.

## What It Does

Research loops run structured, adversarial, multi-sprint investigations:

1. **Explorer** gathers data and forms competing hypotheses
2. **Adversary** attacks every thesis, finds failure modes
3. **Validator** cross-checks sources and verifies claims
4. **Synthesizer** consolidates findings that survive all layers

Loops run in isolated sub-agent sessions, write findings to files, and deliver
briefs to Discord. The orchestrator (Claude in the main session) never ingests
raw loop output — all content passes through the security pipeline first.

---

## Quick Start

### 1. Pick or create a config

```bash
# Use an existing template
cp configs/examples/ai-compute-architecture.json configs/my-research.json
# Edit to your question
```

### 2. Preview before launch

```bash
python3 loops.py preview configs/my-research.json
```

### 3. Launch

```bash
python3 loops.py launch configs/my-research.json
```

### 4. Monitor

```bash
python3 loops.py status
python3 loops.py detail L0042
```

Briefs are delivered to Discord automatically when complete.

---

## Config Format

```json
{
  "domain": "financial|technical|product|scientific|intelligence",
  "mode": "streaming|batch|hybrid",
  "problem_statement": "What question are we trying to answer?",
  "success_criteria": ["Specific", "Measurable", "Actionable"],
  "resources": {
    "time_budget_minutes": 60,
    "token_budget": 50000,
    "cost_budget_usd": 5.00
  },
  "output": {
    "format": "brief|detailed|dashboard",
    "delivery": ["file", "discord"]
  }
}
```

See `configs/examples/` for full domain templates.

---

## Security Model

**Research loops fetch untrusted content from the internet and route it through
local models. This is a high-value injection attack surface. The pipeline has
mandatory defenses at every seam.**

### Defense Layers (execution order)

| Layer | What | Where |
|-------|------|--------|
| 1 | Per-fetch sanitization — strip injection patterns before agent sees content | Tool intercept |
| 2 | Session nonce wrap — XML envelope marks all external content | Loop harness |
| 3 | Cross-turn detection — accumulated summary re-scanned before state write | Sprint finalize |
| 4 | Local model handoff — `model_output_sanitizer` mandatory at every local→Claude seam | Orchestrator |
| 5 | State file chain-of-custody — nonce verified on every state re-read | State I/O |

### Session Nonce Continuity

Each loop session gets a unique nonce at start. It's embedded in the system prompt.
All fetched content arrives wrapped in nonce-tagged XML. Anything claiming to be
instructions *outside* that wrapper is treated as injected and discarded.

### Henry's Contributions (Menehune Research)

Henry built the tool-level sanitization layer — intercepting web_fetch output
**before** it reaches the agent, not after. This is the correct place to sanitize:
the agent should never see raw external content at all.

He also established `model_output_sanitizer.py` as the canonical sanitizer for
local model output. It is **mandatory** at every local→Claude handoff:

```python
from model_output_sanitizer import sanitize_model_output

result = sanitize_model_output(raw, source_model="qwen3-coder", task="synthesis")
if result["blocked"]:
    raise SecurityError("Local model output blocked — do not pass to Claude")
feed_to_claude(result["text"])  # XML-wrapped, safe
```

### Three Known Attack Gaps (now closed)

1. **Cross-turn accumulation** — attacker fragments injection across multiple pages.
   Closed by re-scanning the accumulated sprint summary before state write.

2. **State file re-read bypass** — compromised summary written to state, re-read
   next sprint without sanitization. Closed by nonce chain-of-custody on every write/read.

3. **Local model handoff gap** — qwen3/gpt-oss output goes to Claude without
   sanitization. Closed by making `model_output_sanitizer` mandatory (not optional)
   at every handoff.

### Financial Loop Hardening

Financial loops default to LLM-based injection detection (not just regex patterns).
Cost ~$0.001/page. A $50 loop triggering a bad trade costs far more.

---

## Configuration — Per Collaborator

**Each collaborator gets their own config files, not their own copy of the skill.**

```
skills/research-loops/
├── SKILL.md              # The skill (shared, versioned)
├── model_output_sanitizer.py  # Sanitizer (shared, versioned)
├── configs/
│   ├── examples/         # Generic templates (committed to git)
│   ├── example.json      # Generic example (committed)
│   └── henry-*.json      # Henry's configs (gitignored if they contain API keys)
└── COLLABORATORS.md      # Who's collaborating and their config locations
```

Configs with embedded API keys are gitignored. Use `example.json` as your template
and keep your API keys in a separate credentials file or environment variable.

---

## Dependencies

```bash
# Python stdlib only for core sanitizer
# For loop management:
pip install rich  # dashboard display

# For Telegram OSINT (optional):
pip install telethon

# For web research:
# Uses OpenClaw's built-in web_fetch / web_search tools
```

---

## Files Reference

| File | Purpose |
|------|---------|
| `SKILL.md` | Full skill documentation for Gahonga/Claude |
| `ARCHITECTURE.md` | Database schema, energy model, loop farm design |
| `model_output_sanitizer.py` | Mandatory sanitizer for local model output |
| `loops.py` | CLI: launch, monitor, status, history |
| `telegram_fetch.py` | Telegram OSINT fetcher (subagent use only) |
| `configs/examples/` | Domain templates (safe to share) |

**Gitignored (never committed):**
- `telegram_config.json` — Telegram API credentials
- `*.session` — Telegram session files
- `state/` — runtime state, loop database
- `*.db` — SQLite databases
- `research_state.json` — runtime state
- `configs/*.json` with API keys — check before staging

---

## COLLABORATORS.md

See `COLLABORATORS.md` for the list of contributors and their config file naming
conventions. If you're joining the project:

1. Copy `configs/example.json` → `configs/yourname-topic.json`
2. Add your config to the `.gitignore` if it contains API keys
3. Add yourself to `COLLABORATORS.md`
4. Do NOT copy the skill itself — work from the shared version

---

*Research Loops v8 — Secure by design. Any problem, any domain, any timescale.*
