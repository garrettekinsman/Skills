# GPU Scheduler Skill

Weighted fair-queuing GPU scheduler for shared multi-agent clusters. Prevents resource contention when multiple agents run concurrent research loops on the same cluster (Framework1 / LiteLLM backends).

## What It Does

- Allocates GPU time slots using weighted fair queuing
- Prevents collision when multiple loop workers spawn simultaneously  
- SQLite backend — integrates with existing `swarm.db`
- `request_slot()` / `release_slot()` API for research loop orchestrators
- Priority levels: sprint | research | training | interactive

## Usage

```python
from gpu_scheduler import GPUScheduler

scheduler = GPUScheduler(db_path="swarm.db")

# Request a slot before spawning a worker
slot = scheduler.request_slot(user="menehune", job_id="loop-123", tokens_est=40000)
if slot["status"] == "granted":
    # spawn worker here
    scheduler.release_slot(slot["slot_id"], actual_tokens=38000)
elif slot["status"] == "queued":
    # wait or defer
    pass
```

## Files

- `gpu_scheduler.py` — scheduler implementation (SQLite backend)
- `design.md` — architecture and algorithm docs  
- `integration.md` — integration guide for research loop orchestrators

## Authors

- Menehune One (hank@menehune) — initial design and implementation
- Gahonga — reviewed architecture  
- Garrett Kinsman — cluster infrastructure

## Status

Design for review — not yet deployed. Open for adaptation to garrettekinsman/Skills cluster.
