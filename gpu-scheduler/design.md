# Production GPU Scheduler for Shared Cluster
**Date:** March 3, 2026  
**Audience:** Garrett, Gahonga, Hank, Menehune  
**Status:** Design for review  

## Problem Statement

Three users/agents will compete for GPU time on the shared cluster (Framework1 + Mac mini):
- **Garrett** — personal research, model training
- **Gahonga** — research loop experiments, QwQ-32B pulls
- **Hank/Menehune** — trading signal research, market analysis

**Current state:** No coordination → collision when multiple agents spawn workers simultaneously → wasted compute, timeouts, frustration.

**Goal:** Deterministic scheduling that:
1. Ensures fair allocation without starvation
2. Minimizes context switches (better utilization)
3. Integrates transparently with existing research loop framework
4. Requires no manual intervention per-sprint
5. Handles variable job sizes (quick inference vs. long training runs)

---

## Design: Weighted Fair Queuing with Reservation Slots

### Core Idea
Divide GPU time into **hourly reservation slots** (~6 per day, 4 hours each). Each user gets a fair share based on **weight** (default: equal), with options to:
- Book slots in advance (deterministic)
- Drop into queue when slot opens (opportunistic)
- Reserve multiple consecutive slots for longer jobs

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ GPU Scheduler (SQLite backend in swarm.db)                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. SLOTS TABLE (hourly reservations)                       │
│     slot_id | start_time | end_time | owner | status       │
│     ────────────────────────────────────────────────────    │
│     s001    | 2026-03-04 00:00 UTC | ... | garrett | locked │
│     s002    | 2026-03-04 04:00 UTC | ... | menehune | free  │
│     s003    | 2026-03-04 08:00 UTC | ... | queued | free    │
│                                                              │
│  2. QUEUE TABLE (FIFO within each hour)                     │
│     job_id | user | request_time | priority | tokens_est   │
│     ──────────────────────────────────────────────────────  │
│     j123   | menehune | 2026-03-03 23:15 | sprint | 40k     │
│     j124   | gahonga  | 2026-03-03 23:20 | research | 80k   │
│                                                              │
│  3. WEIGHTS TABLE (fair share allocation)                   │
│     user | weight | slots_per_day | priority_level          │
│     ────────────────────────────────────────────────────    │
│     garrett | 1.0 | 2 | normal                              │
│     menehune | 1.0 | 2 | high (research ops)               │
│     gahonga | 1.0 | 2 | normal                              │
│                                                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Worker Agent (OpenClaw / Research Loop)                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ When spawning a worker sprint:                              │
│   1. Call: scheduler.request_slot(user, job_id, tokens_est) │
│   2. Returns: (slot_id, start_time, end_time) or QUEUED    │
│   3. Worker checks: if queued, wait or fail gracefully      │
│   4. Worker runs during allocated slot                      │
│   5. Call: scheduler.release_slot(slot_id, actual_tokens)   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Algorithm: Slot Allocation

**Input:** user, job_id, estimated_tokens, priority (sprint|training|research|interactive)

**Output:** (slot_id, start_utc, end_utc) or "QUEUED"

**Logic:**

```
1. Check next 7 days for available slots
2. Calculate user's "allocation budget"
   = sum of weights for slots where (owner == NULL) in next 7 days
3. Allocate min(user.slots_requested, user.allocation_budget)
4. If insufficient: add to queue for next available slot
5. If priority="sprint": bump to front of queue, but only if user has
   credit (previous sprint completed <= soft_budget)
6. Return earliest available slot or QUEUED with position
```

### Fairness via Token Estimation

Instead of time-based slots (unfair: a quick model inference vs. a 1-hour training run), use **token budget** to pack multiple jobs into one slot:

```
Slot capacity: 50k tokens (based on Framework1 real throughput)
User budget per slot: 50k tokens
Job estimation: user provides tokens_est (or defaults to 40k)

If job.tokens_est > slot.remaining_capacity:
  → refuse (job too big for remaining slot)
  → suggest: split into multiple sprints OR
  → suggest: book multiple consecutive slots
```

### Priority Levels
```
interactive:   max 1h, highest priority, no queuing (immediate)
sprint:        max 4h, normal priority, bumps ahead if credits exist
research:      max 8h, low priority, queues
training:      max 12h, lowest priority, queues (can span multiple slots)
```

**Credit system:** User gets 1 "priority bump" per successful sprint completion. Usable once, then refreshed.

---

## Integration with Research Loop

### Worker Prompt Injection
Add to `worker_prompt_template.py`:

```python
# Scheduler integration (injected into every worker)
SCHEDULER_SLOT_ID = os.environ.get('GPU_SLOT_ID')
SCHEDULER_END_TIME = os.environ.get('GPU_SLOT_END_UTC')

if SCHEDULER_SLOT_ID:
    print(f"[Scheduler] Allocated slot {SCHEDULER_SLOT_ID}, expires {SCHEDULER_END_TIME}")
    # Worker can monitor and self-terminate if approaching deadline
```

### Orchestrator Integration
In `orchestrator.py`, before spawning worker:

```python
slot_id, start, end = scheduler.request_slot(
    user=config['user'],
    job_id=self.job_id,
    tokens_est=soft_budget,
    priority='sprint'
)

if slot_id:
    # Slot allocated immediately
    env['GPU_SLOT_ID'] = slot_id
    env['GPU_SLOT_END_UTC'] = end
    fire_event(f"Slot {slot_id} allocated, starting worker")
else:
    # Queued - wait or fail
    if config.get('wait_for_slot'):
        fire_event(f"Queued {position}. Retrying in 60s...")
        sleep(60)
        # Retry or bail
    else:
        fire_event(f"No slot available, queuing or failing")
        return None
```

### Safety: Auto-Termination
Worker should periodically check:
```python
remaining_sec = (SCHEDULER_END_TIME - now).total_seconds()
if remaining_sec < 300:  # 5 min warning
    print("[Scheduler] 5 minutes remaining, wrapping up...")
    # Flush findings to DB, clean exit
if remaining_sec <= 0:
    print("[Scheduler] TIMEOUT - force terminating")
    # Emergency checkpoint
    sys.exit(0)
```

---

## API Endpoints

### `scheduler.request_slot(user, job_id, tokens_est, priority='sprint')`
Returns: `(slot_id, start_utc, end_utc)` or `("QUEUED", position, estimated_wait_minutes)`

### `scheduler.release_slot(slot_id, actual_tokens)`
Called by worker when done. Updates accounting, frees slot for next job in queue.

### `scheduler.get_status(user=None)`
Returns: table of slots, queue position, usage statistics.

### `scheduler.book_slots(user, start_utc, count=1, reason="")`
Proactively reserve N consecutive slots (for known long jobs).

### `scheduler.cancel_booking(job_id)`
Release unused slots back to the pool.

---

## SQL Schema

```sql
CREATE TABLE scheduler_slots (
    slot_id TEXT PRIMARY KEY,
    slot_start_utc TEXT NOT NULL,
    slot_end_utc TEXT NOT NULL,
    owner TEXT,
    job_id TEXT,
    status TEXT DEFAULT 'free',  -- free | allocated | locked | running | complete | failed
    tokens_allocated INTEGER,
    tokens_actual INTEGER,
    created_utc TEXT,
    started_utc TEXT,
    ended_utc TEXT
);

CREATE TABLE scheduler_queue (
    queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE NOT NULL,
    user TEXT NOT NULL,
    priority TEXT NOT NULL,
    tokens_est INTEGER,
    request_time_utc TEXT NOT NULL,
    position INTEGER,
    status TEXT DEFAULT 'queued',  -- queued | allocated | running | complete | failed
    created_utc TEXT
);

CREATE TABLE scheduler_weights (
    user TEXT PRIMARY KEY,
    weight REAL DEFAULT 1.0,
    slots_per_week INTEGER DEFAULT 14,
    priority_level TEXT DEFAULT 'normal',
    credits INTEGER DEFAULT 0
);

CREATE TABLE scheduler_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_id TEXT,
    job_id TEXT,
    event_type TEXT,  -- allocated | queued | released | timeout | conflict
    user TEXT,
    payload_json TEXT,
    created_utc TEXT
);
```

---

## Conflict Detection & Prevention

**Scenario:** Two agents try to spawn simultaneously, both see slot as "free"

**Solution:** SQLite TRANSACTION with SERIALIZABLE isolation
```python
with conn:
    # Atomic check + allocate
    cursor.execute(
        "UPDATE scheduler_slots SET owner=?, status='allocated' "
        "WHERE slot_id=? AND status='free' AND owner IS NULL",
        (user, slot_id)
    )
    if cursor.rowcount != 1:
        # Lost race, slot taken
        return None, None, None
    # Safe to proceed
```

---

## Deployment Checklist

- [ ] Add schema to swarm.db
- [ ] Deploy `gpu_scheduler.py` module
- [ ] Wire into orchestrator.py (3 lines)
- [ ] Wire into worker_prompt_template.py (2 lines)
- [ ] Set default weights (equal allocation)
- [ ] Test: simulate concurrent requests
- [ ] Docs: share with Garrett + Gahonga
- [ ] Monitor: add scheduler status to HEARTBEAT

---

## Advantages

✅ **Deterministic** — no surprise collisions, predictable allocation  
✅ **Fair** — token-based prevents one big job from hogging GPU  
✅ **Transparent** — workers see slot info, can adapt  
✅ **Integrated** — minimal changes to existing loop framework  
✅ **Extensible** — easy to add priority bumps, dynamic weights, etc.  
✅ **Observable** — full audit trail in swarm.db  

## Tradeoffs

⚠️ **Slot overhead** — if job is much smaller than 4h slot, wasted GPU time  
→ *Mitigation:* pack multiple small jobs into one slot via token budgets

⚠️ **Queuing wait** — user may need to wait hours for next available slot  
→ *Mitigation:* credit system lets frequent users bump priority

⚠️ **Estimation accuracy** — tokens_est may be wrong  
→ *Mitigation:* actual_tokens tracked, credits adjusted next time

---

## Success Criteria

1. No concurrent GPU usage conflicts (timeouts, collisions) ✓
2. Fair allocation: each user gets ~equal GPU time per week ✓
3. Deterministic: allocations are predictable and recorded ✓
4. Minimal disruption: <5 line changes to existing code ✓
5. Operational: human can check status, adjust weights, override if needed ✓
