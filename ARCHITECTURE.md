# Loop Farm — Architecture & Database Design

## Overview

The Loop Farm tracks, previews, and manages research loops. Modeled after the DML 3D Print Farm pattern: preview before launch, monitor while running, review when complete.

## Database

**Location:** `skills/research-loops/state/loops.json`
**Format:** JSON (flat file, upgradeable to SQLite at scale)

### Schema

```json
{
  "models": { ... },      // Model registry with cost rates
  "energy": { ... },      // Energy consumption constants
  "budgets": { ... },     // Per-provider monthly budgets & spend
  "loops": [ ... ],       // Array of loop records
  "next_id": 6            // Auto-increment counter
}
```

### Model Registry

Each model entry tracks:
- `name` — human-readable name
- `provider` — `anthropic`, `xai`, or `local`
- `cost_per_1k_input` / `cost_per_1k_output` — USD per 1K tokens
- `type` — `cloud` or `local`

### Energy Constants

```json
{
  "local_watts_idle": 40,       // Mac Studio M4 Max idle draw
  "local_watts_load": 120,      // Mac Studio M4 Max under inference load
  "cloud_wh_per_100k_tokens": 5.0,  // Rough A100 estimate (300W GPU, ~100K tok/min, PUE 1.2)
  "electricity_rate_kwh": 0.30  // California residential rate
}
```

### Energy Estimation (Per-Model)

Energy varies by model because different models run on different hardware at different throughputs.

**Per-model energy rates (Wh per 100K tokens):**

| Model | Wh/100K tok | Assumption |
|-------|-------------|------------|
| Claude Opus | 8.0 | Larger model, H100/A100, ~400W/GPU, slower throughput (~50K tok/min) |
| Claude Sonnet | 4.0 | Smaller model, same hardware, faster throughput (~150K tok/min) |
| Grok 4 Fast | 5.0 | Similar to Sonnet-class on xAI Colossus cluster |
| Local (any) | 0.0* | Tracked separately via wall_time × watts |

*Local energy is NOT per-token. It's `wall_time_hours × 120W` — much more accurate since we know the hardware.

**Cloud energy calculation (per loop):**
```
For each model used in loop:
  model_energy_wh = (model_tokens / 100,000) × model_wh_rate
total_energy_wh = sum of all model energies
```

Example: Multi-model loop (150K Grok + 50K Sonnet):
```
Grok:   150K × 5.0/100K = 7.5 Wh
Sonnet:  50K × 4.0/100K = 2.0 Wh
Total:                     9.5 Wh
```

vs. same loop all-Opus (200K tokens):
```
Opus:   200K × 8.0/100K = 16.0 Wh  (68% more energy!)
```

**Local loops (Mac Studio M4 Max 64GB):**
```
energy_wh = wall_time_hours × 120W (under load)
energy_kwh = energy_wh / 1000
cost_electricity = energy_kwh × $0.30
```

**Comparison (10 min research loop, ~200K tokens):**

| Metric | Opus (cloud) | Sonnet (cloud) | Grok (cloud) | Local (Mac Studio) |
|--------|-------------|----------------|-------------|-------------------|
| API cost | ~$3.00 | ~$0.60 | ~$0.60 | $0.00 |
| Energy | 16.0 Wh | 8.0 Wh | 10.0 Wh | 20.0 Wh |
| Electricity | n/a (in API) | n/a (in API) | n/a (in API) | $0.006 |
| Total cost | ~$3.00 | ~$0.60 | ~$0.60 | $0.006 |

**Key insight:** Local inference is ~100-500x cheaper per loop. The Mac Studio pays for itself after ~2,000-4,000 loops ($2,650 / $0.60-$1.50 per cloud loop).

### Assumptions — Fact Check This!

All energy estimates are approximations. The assumptions live in `state/loops.json` under `energy.assumptions`. Key uncertainties:

1. **We don't know Anthropic/xAI's actual GPU hardware** — H100 vs A100 vs custom silicon changes Wh significantly
2. **Throughput varies by load** — batch processing is more efficient than real-time
3. **PUE varies by datacenter** — Google claims 1.1, others are 1.3+. We assume 1.2.
4. **Token counting approximation** — we estimate 60% input / 40% output split
5. **Local wattage is peak inference** — actual may be lower for MoE models (less GPU utilization)

**To validate:** Compare against published sustainability reports from Anthropic, Google (Gemini), and xAI when available. Update `per_model_wh_per_100k_tokens` in the database when better numbers are available.

### Budget Tracking

Per-provider budgets:
- `monthly_budget_usd` — spending cap for the billing cycle
- `cycle_start` / `cycle_end` — billing period
- `spent_this_cycle_usd` — manual spend additions (main session chat, etc.)
- Loop costs auto-calculated from loop history

Status thresholds: 🟢 < 70%, 🟡 70-90%, 🔴 > 90%

### Loop Record

Each loop tracks:

```json
{
  "id": "L0001",                    // Auto-increment ID
  "topic": "Research topic",         // Human-readable description
  "model": "xai/grok-4-fast",       // Model ID (matches model registry)
  "min_sprints": 12,                 // Minimum sprints before convergence
  "max_sprints": 20,                 // Hard cap on sprints
  "timeout_minutes": 15,             // Wall clock timeout
  "token_budget": 400000,            // Max tokens to consume
  "theses": ["T1", "T2"],           // Starting theses to test
  "data_sources": ["your_data_api"],       // Data APIs to use
  "output_dir": "ops/research/...",  // Where output files go
  
  "status": "completed",             // Lifecycle state
  "created_at": "ISO-8601",
  "started_at": "ISO-8601",
  "completed_at": "ISO-8601",
  "session_key": "agent:main:...",   // OpenClaw session reference
  "run_id": "uuid",                  // Spawn run ID
  
  "sprints_completed": 12,
  "tokens_used": 200000,
  "theses_tested": 7,
  "theses_killed": 2,
  "findings": 14,
  "cost_usd": 0.60,
  "wall_time_min": 4.0,
  "energy_wh": 10.0,                // Estimated energy consumption
  
  "events": [...],                   // Event log (timestamped)
  "briefing_path": "ops/.../brief.md",
  "state_path": "ops/.../state.json"
}
```

### Lifecycle

```
preview → queued → running → completed
                          → failed
                          → killed
```

- **preview** — Config loaded, shown to user, awaiting LAUNCH
- **queued** — Approved, waiting to start (future: queue management)
- **running** — sessions_spawn active, sprints executing
- **completed** — All sprints done or converged, briefing generated
- **failed** — Error or timeout
- **killed** — User or system cancelled

## CLI Commands

| Command | Description |
|---------|-------------|
| `loops.py status` | Dashboard: credits, loops, totals |
| `loops.py preview <config.json>` | Preview before launch |
| `loops.py list` | All loops ever |
| `loops.py history [n]` | Last N completed |
| `loops.py detail <id>` | Full detail + event log |
| `loops.py log <id> <event>` | Append event |
| `loops.py spend <provider> <amount>` | Log manual spend |
| `loops.py budget <provider> <amount>` | Set monthly budget |

## File Structure

```
skills/research-loops/
├── SKILL.md              # How to run research loops
├── ARCHITECTURE.md       # This file — database design & energy model
├── loops.py              # CLI tool & database manager
├── configs/              # Loop config templates
│   └── example.json
└── state/
    └── loops.json        # Database (gitignored in production)
```

## Future Enhancements

- [ ] SQLite backend when loop count exceeds ~100
- [ ] Real-time energy monitoring via `powermetrics` on Mac Studio
- [ ] Auto-calculate energy from wall_time on loop completion
- [ ] Carbon offset tracking (optional)
- [ ] Loop queue with priority scheduling
- [ ] Ohdowas (security agent) auditing of loop actions
- [ ] Cost alerts when approaching budget thresholds
- [ ] Dashboard web UI via OpenClaw canvas
