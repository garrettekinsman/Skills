#!/usr/bin/env python3
"""
GPU Scheduler for Shared Cluster
Deterministic, fair-share allocation with token budgets.

Usage:
    scheduler = GPUScheduler('/path/to/swarm.db')
    slot_id, start, end = scheduler.request_slot('menehune', 'job123', 40000, 'sprint')
    # ... worker runs during [start, end) ...
    scheduler.release_slot(slot_id, actual_tokens_used=38000)
"""

import sqlite3
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Tuple, Optional, List, Dict
from dataclasses import dataclass


@dataclass
class SlotAllocation:
    """Response from request_slot()"""
    slot_id: str
    start_utc: str
    end_utc: str
    tokens_capacity: int
    status: str  # 'allocated' | 'queued'


class GPUScheduler:
    """Manages GPU slot allocation for shared cluster."""

    # Configuration
    SLOT_DURATION_HOURS = 4
    SLOT_TOKEN_CAPACITY = 50000  # tokens per 4-hour slot
    SLOTS_PER_WEEK = 42  # 7 days * 6 slots/day
    DEFAULT_WEIGHT = 1.0

    def __init__(self, db_path: str):
        """Initialize scheduler with swarm.db."""
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self):
        """Create scheduler tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scheduler_slots (
                slot_id TEXT PRIMARY KEY,
                slot_start_utc TEXT NOT NULL,
                slot_end_utc TEXT NOT NULL,
                owner TEXT,
                job_id TEXT,
                status TEXT DEFAULT 'free',
                tokens_allocated INTEGER,
                tokens_actual INTEGER,
                priority TEXT,
                created_utc TEXT NOT NULL,
                started_utc TEXT,
                ended_utc TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scheduler_queue (
                queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT UNIQUE NOT NULL,
                user TEXT NOT NULL,
                priority TEXT NOT NULL,
                tokens_est INTEGER,
                request_time_utc TEXT NOT NULL,
                queue_position INTEGER,
                status TEXT DEFAULT 'queued',
                created_utc TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scheduler_weights (
                user TEXT PRIMARY KEY,
                weight REAL DEFAULT 1.0,
                slots_per_week INTEGER DEFAULT 6,
                priority_level TEXT DEFAULT 'normal',
                credits INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scheduler_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                slot_id TEXT,
                job_id TEXT,
                event_type TEXT,
                user TEXT,
                payload_json TEXT,
                created_utc TEXT
            )
        """)

        # Create indices
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_scheduler_slots_status "
            "ON scheduler_slots(status, slot_start_utc)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_scheduler_queue_user "
            "ON scheduler_queue(user, status)"
        )

        conn.commit()
        conn.close()

    def _now_utc(self) -> datetime:
        """Current UTC time."""
        return datetime.now(timezone.utc)

    def _now_utc_str(self) -> str:
        """Current UTC time as ISO string."""
        return self._now_utc().isoformat()

    def _generate_slots(self, days_ahead: int = 7):
        """Generate future slot reservations."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = self._now_utc()
        cursor.execute("SELECT COUNT(*) FROM scheduler_slots")
        existing_count = cursor.fetchone()[0]

        # If slots already exist, don't regenerate
        if existing_count > 0:
            conn.close()
            return

        for day_offset in range(days_ahead):
            for slot_num in range(6):  # 6 slots per day (4 hours each)
                slot_start = now.replace(hour=0, minute=0, second=0, microsecond=0) + \
                             timedelta(days=day_offset, hours=slot_num * 4)
                slot_end = slot_start + timedelta(hours=self.SLOT_DURATION_HOURS)

                slot_id = f"slot_{slot_start.strftime('%Y%m%d_%H%M')}"

                cursor.execute(
                    "INSERT OR IGNORE INTO scheduler_slots "
                    "(slot_id, slot_start_utc, slot_end_utc, status, created_utc) "
                    "VALUES (?, ?, ?, 'free', ?)",
                    (slot_id, slot_start.isoformat(), slot_end.isoformat(),
                     self._now_utc_str())
                )

        conn.commit()
        conn.close()

    def _ensure_user_weight(self, user: str):
        """Ensure user has a weight entry."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO scheduler_weights (user, weight) VALUES (?, ?)",
            (user, self.DEFAULT_WEIGHT)
        )
        conn.commit()
        conn.close()

    def request_slot(
        self, user: str, job_id: str, tokens_est: int, priority: str = 'sprint'
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Request a GPU slot for a job.

        Returns:
            (slot_id, start_utc, end_utc) if allocated immediately
            (None, None, None) if queued (check position later)
        """
        self._generate_slots()
        self._ensure_user_weight(user)

        conn = sqlite3.connect(self.db_path)
        conn.isolation_level = None  # Autocommit mode for transaction control

        try:
            # Start transaction
            conn.execute("BEGIN IMMEDIATE")

            cursor = conn.cursor()

            # Find next free slot
            cursor.execute(
                "SELECT slot_id, slot_start_utc, slot_end_utc FROM scheduler_slots "
                "WHERE status = 'free' ORDER BY slot_start_utc LIMIT 1"
            )
            row = cursor.fetchone()

            if not row:
                # No free slots, add to queue
                cursor.execute(
                    "INSERT INTO scheduler_queue "
                    "(job_id, user, priority, tokens_est, request_time_utc, created_utc) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (job_id, user, priority, tokens_est, self._now_utc_str(), self._now_utc_str())
                )
                self._log_event(conn, None, job_id, 'queued', user, {'priority': priority})
                conn.commit()
                return None, None, None

            slot_id, start_utc, end_utc = row

            # Atomically claim the slot
            cursor.execute(
                "UPDATE scheduler_slots SET owner = ?, job_id = ?, status = 'allocated', "
                "priority = ?, tokens_allocated = ?, started_utc = ? "
                "WHERE slot_id = ? AND status = 'free'",
                (user, job_id, priority, tokens_est, self._now_utc_str(), slot_id)
            )

            if cursor.rowcount != 1:
                # Lost race, try again (tail-recursion via loop)
                conn.rollback()
                conn.close()
                return self.request_slot(user, job_id, tokens_est, priority)

            # Log allocation
            self._log_event(
                conn, slot_id, job_id, 'allocated', user,
                {'tokens_est': tokens_est, 'priority': priority}
            )

            conn.commit()
            return slot_id, start_utc, end_utc

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def release_slot(self, slot_id: str, actual_tokens: int):
        """Release a slot after job completion."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE scheduler_slots SET status = 'complete', tokens_actual = ?, "
            "ended_utc = ? WHERE slot_id = ?",
            (actual_tokens, self._now_utc_str(), slot_id)
        )

        # Get job info for logging
        cursor.execute("SELECT job_id, owner, priority, tokens_allocated FROM scheduler_slots WHERE slot_id = ?", (slot_id,))
        row = cursor.fetchone()
        if row:
            job_id, user, priority, tokens_est = row
            self._log_event(conn, slot_id, job_id, 'released', user, {
                'tokens_est': tokens_est,
                'tokens_actual': actual_tokens
            })

        # Check queue for next job
        self._promote_from_queue_impl(conn)

        conn.commit()
        conn.close()

    def _promote_from_queue_impl(self, conn):
        """Promote next job from queue to allocated slot (uses provided connection)."""
        cursor = conn.cursor()

        cursor.execute(
            "SELECT job_id, user, priority, tokens_est FROM scheduler_queue "
            "WHERE status = 'queued' ORDER BY request_time_utc LIMIT 1"
        )
        row = cursor.fetchone()

        if not row:
            return

        job_id, user, priority, tokens_est = row

        # Try to find a free slot for this job
        cursor.execute(
            "SELECT slot_id FROM scheduler_slots WHERE status = 'free' LIMIT 1"
        )
        slot_row = cursor.fetchone()

        if slot_row:
            slot_id = slot_row[0]
            # Claim it
            cursor.execute(
                "UPDATE scheduler_slots SET owner = ?, job_id = ?, status = 'allocated', "
                "priority = ?, tokens_allocated = ?, started_utc = ? WHERE slot_id = ?",
                (user, job_id, priority, tokens_est, self._now_utc_str(), slot_id)
            )
            cursor.execute(
                "UPDATE scheduler_queue SET status = 'allocated' WHERE job_id = ?",
                (job_id,)
            )
            self._log_event(conn, slot_id, job_id, 'promoted_from_queue', user, {})

    def _promote_from_queue(self):
        """Promote next job from queue (creates own connection)."""
        conn = sqlite3.connect(self.db_path)
        self._promote_from_queue_impl(conn)
        conn.commit()
        conn.close()

    def get_status(self, user: Optional[str] = None) -> Dict:
        """Get scheduler status."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Slots by status
        cursor.execute(
            "SELECT status, COUNT(*) FROM scheduler_slots GROUP BY status"
        )
        slot_summary = {row[0]: row[1] for row in cursor.fetchall()}

        # Queue length
        if user:
            cursor.execute(
                "SELECT COUNT(*) FROM scheduler_queue WHERE user = ? AND status = 'queued'",
                (user,)
            )
        else:
            cursor.execute("SELECT COUNT(*) FROM scheduler_queue WHERE status = 'queued'")
        queue_length = cursor.fetchone()[0]

        # Usage stats
        cursor.execute(
            "SELECT owner, COUNT(*) as slots_used, SUM(tokens_actual) as tokens_consumed "
            "FROM scheduler_slots WHERE status = 'complete' GROUP BY owner"
        )
        usage = {row[0]: {'slots': row[1], 'tokens': row[2]} for row in cursor.fetchall()}

        conn.close()

        return {
            'slots': slot_summary,
            'queue_length': queue_length,
            'usage_by_user': usage,
            'timestamp': self._now_utc_str()
        }

    def _log_event(self, conn, slot_id: Optional[str], job_id: str, event_type: str,
                   user: str, payload: Dict):
        """Log a scheduler event (uses provided connection)."""
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO scheduler_events "
            "(slot_id, job_id, event_type, user, payload_json, created_utc) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (slot_id, job_id, event_type, user, json.dumps(payload), self._now_utc_str())
        )


# CLI for testing and administration
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print(__doc__)
        print("\nCommands:")
        print("  request <db> <user> <job_id> <tokens> [priority]")
        print("  release <db> <slot_id> <actual_tokens>")
        print("  status <db> [user]")
        sys.exit(1)

    cmd = sys.argv[1]
    db_path = sys.argv[2]
    scheduler = GPUScheduler(db_path)

    if cmd == 'request':
        user, job_id, tokens = sys.argv[3], sys.argv[4], int(sys.argv[5])
        priority = sys.argv[6] if len(sys.argv) > 6 else 'sprint'
        slot_id, start, end = scheduler.request_slot(user, job_id, tokens, priority)
        if slot_id:
            print(f"ALLOCATED: {slot_id} [{start} to {end}]")
        else:
            print("QUEUED: waiting for next available slot")

    elif cmd == 'release':
        slot_id, actual_tokens = sys.argv[3], int(sys.argv[4])
        scheduler.release_slot(slot_id, actual_tokens)
        print(f"Released {slot_id}, {actual_tokens} tokens used")

    elif cmd == 'status':
        user = sys.argv[3] if len(sys.argv) > 3 else None
        status = scheduler.get_status(user)
        print(json.dumps(status, indent=2))
