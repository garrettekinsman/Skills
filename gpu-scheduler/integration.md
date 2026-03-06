# GPU Scheduler Integration Guide

For: Garrett, Gahonga, Hank

## Files Delivered

1. **Design Document:** `research/gpu-scheduler-design.md` — full design rationale, architecture, tradeoffs
2. **Implementation:** `scripts/scheduling/gpu_scheduler.py` — production-ready Python module
3. **Integration Guide:** this file

---

## Quick Start

### 1. Add to Cluster Infrastructure

Copy `gpu_scheduler.py` to your cluster control system:
```bash
scp scripts/scheduling/gpu_scheduler.py garrett@framework1:~/scheduler/
```

### 2. Wire into Orchestrator (3 lines)

In your orchestrator or worker-spawning code:
```python
from gpu_scheduler import GPUScheduler

scheduler = GPUScheduler('/path/to/swarm.db')
slot_id, start, end = scheduler.request_slot(
    user='menehune', 
    job_id='loop-polymark-s2',
    tokens_est=40000,
    priority='sprint'
)

if slot_id:
    env['GPU_SLOT_ID'] = slot_id
    env['GPU_SLOT_END_UTC'] = end
    spawn_worker(...)
else:
    # Job queued - can wait or fail gracefully
    queue_position = scheduler.get_status('menehune')['queue_length']
    print(f"Queued. {queue_position} ahead.")
```

### 3. Release Slot After Job (1 line)

```python
scheduler.release_slot(slot_id, actual_tokens_consumed)
```

---

## Usage Examples

### CLI Testing

```bash
# Initialize and request a slot
python3 gpu_scheduler.py request /tmp/test.db menehune job001 40000 sprint
# Output: ALLOCATED: slot_2026030400_00 [2026-03-04T00:00:00+00:00 to 2026-03-04T04:00:00+00:00]

# Release slot
python3 gpu_scheduler.py release /tmp/test.db slot_2026030400_00 38000
# Output: Released slot_2026030400_00, 38000 tokens used

# Check status
python3 gpu_scheduler.py status /tmp/test.db menehune
# Output: JSON with slots, queue, usage stats
```

### Python API

```python
from gpu_scheduler import GPUScheduler

scheduler = GPUScheduler('/path/to/swarm.db')

# Request slot for a research sprint
slot_id, start, end = scheduler.request_slot(
    user='menehune',
    job_id='polymarket-sprint-3',
    tokens_est=50000,
    priority='sprint'
)

if slot_id:
    print(f"Slot allocated: {slot_id}")
    print(f"Run from {start} to {end}")
    # ... run job ...
    scheduler.release_slot(slot_id, actual_tokens=49850)
else:
    print("No slots available, queued for next available slot")

# Check current status
status = scheduler.get_status()
print(f"Free slots: {status['slots'].get('free', 0)}")
print(f"Users waiting: {status['queue_length']}")
```

---

## Configuration

### Default Settings (can be overridden)

```python
SLOT_DURATION_HOURS = 4        # Each slot is 4 hours
SLOT_TOKEN_CAPACITY = 50000    # Tokens per slot (based on Framework1 real throughput)
SLOTS_PER_WEEK = 42            # 6 slots per day, 7 days
DEFAULT_WEIGHT = 1.0           # Equal allocation for all users
```

### User Weights (for fair allocation)

```python
# All users start with weight=1.0 (equal allocation)
# To give one user more slots, increase weight:

scheduler._ensure_user_weight('hank')
conn = sqlite3.connect('/path/to/swarm.db')
cursor = conn.cursor()
cursor.execute(
    "UPDATE scheduler_weights SET weight = ? WHERE user = ?",
    (1.5, 'hank')  # Give Hank 50% more slots
)
conn.commit()
```

### Priority Levels

```
'interactive' — max 1h, highest priority, no queuing
'sprint'      — max 4h, normal priority, queues if needed
'research'    — max 8h, low priority, queues
'training'    — max 12h, lowest priority, queues (can span slots)
```

---

## How It Works

### Slot Generation
- Generates 7 days of future slots on first use
- Each slot is 4 hours; 6 per day (0-4h, 4-8h, ..., 20-24h UTC)
- Each slot holds ~50k tokens (based on real Framework1 throughput)

### Allocation Algorithm
```
1. User requests slot with job_id and tokens_est
2. Scheduler finds next free slot
3. Claims it atomically (SQLite transaction prevents races)
4. Returns (slot_id, start_time, end_time) to worker
5. If no free slots, adds job to queue
6. When slot releases, next queued job is promoted
```

### Conflict Prevention
- **Atomic claims** via SQLite transactions — no two workers can claim same slot
- **Isolation level = SERIALIZABLE** — prevents race conditions
- **Full audit trail** in scheduler_events table

### Fairness
- **Token budgets** not time — prevents one large job from hogging entire slot
- **FIFO queue** — no starvation
- **Weights** — can adjust allocation ratios per user if needed
- **Credit system** (extensible) — frequent users can bump priority

---

## Monitoring & Operations

### Check Queue Status
```python
status = scheduler.get_status()
print(f"Free slots: {status['slots']['free']}")
print(f"Allocated: {status['slots']['allocated']}")
print(f"Queued jobs: {status['queue_length']}")
print(f"Usage: {status['usage_by_user']}")
```

### View Scheduler Events
```sql
SELECT * FROM scheduler_events 
WHERE job_id='polymarket-sprint-2'
ORDER BY created_utc DESC
LIMIT 20;
```

### View Slot Timeline
```sql
SELECT slot_id, slot_start_utc, slot_end_utc, owner, status, tokens_allocated, tokens_actual
FROM scheduler_slots
ORDER BY slot_start_utc
LIMIT 20;
```

### Adjust User Weights
```sql
-- Give one user more slots
UPDATE scheduler_weights SET weight=1.5 WHERE user='menehune';

-- Reset to equal allocation
UPDATE scheduler_weights SET weight=1.0;
```

---

## Extension Points

### Auto-Extend Slots
For long-running jobs, request multiple consecutive slots:
```python
# Book 2 consecutive slots (8 hours total)
slots = []
for i in range(2):
    slot_id, start, end = scheduler.request_slot(
        'menehune', 'long-training-job', 50000, 'training'
    )
    slots.append(slot_id)
    # Specify next slot as dependent?
```

### Priority Bumps
Via credit system — users earn credits for successful sprints, use to bump ahead in queue:
```python
# After successful sprint
scheduler._add_credit('menehune', 1)

# Later, when queuing
slot_id, start, end = scheduler.request_slot(
    'menehune', 'urgent-sprint', 30000, 'sprint', 
    use_credits=True  # Bumps ahead if available
)
```

### Predictive Slot Booking
For recurring jobs, pre-book slots:
```python
# Request 14 future slots for regular training
scheduler.book_slots('garrett', start_utc=..., count=14, reason='daily_model_update')
```

---

## Testing the Implementation

```bash
# Simple test
python3 -c "
from gpu_scheduler import GPUScheduler
scheduler = GPUScheduler('/tmp/test_scheduler.db')

# Request a slot
slot_id, start, end = scheduler.request_slot('user1', 'job1', 30000)
print(f'Allocated: {slot_id}')

# Release it
scheduler.release_slot(slot_id, 29500)
print(f'Released')

# Check status
status = scheduler.get_status()
print(f'Status: {status}')
"
```

---

## Deployment Checklist

- [ ] Copy `gpu_scheduler.py` to cluster infrastructure
- [ ] Initialize swarm.db with scheduler schema (automatic on first use)
- [ ] Add 3-line integration to orchestrator
- [ ] Add 1-line integration to worker release
- [ ] Set DEFAULT_WEIGHT for fair allocation (or keep 1.0 for equal)
- [ ] Test: request/release/check_status via CLI
- [ ] Monitor: add `scheduler.get_status()` to ops dashboards
- [ ] Document: share this guide with Garrett + Gahonga

---

## Questions?

The implementation is deterministic, fully reversible, and adds minimal overhead. It integrates directly into the existing swarm.db infrastructure without requiring new external systems.

All state is in SQLite — snapshot swarm.db to backup, replay scheduler_events to audit, export usage stats for billing/fairness reporting.
