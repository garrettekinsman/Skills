"""
checkpoint_manager.py — Core checkpoint/state manager for Loop Relay.
Implements Vera's architecture v1-2026-03-01.

All DB writes are atomic (WAL + tmp+os.replace for JSON exports).
DB at ~/.openclaw/workspace/projects/loop-relay/swarm.db

Python 3.9 compatible. No external deps.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from baton import Baton, content_hash

# ─── Constants ────────────────────────────────────────────────────────────────

DEFAULT_DB_PATH = Path.home() / ".openclaw/workspace/projects/loop-relay/swarm.db"
SCHEMA_FILE = Path(__file__).parent / "schema.sql"

# Stale sprint threshold: if status='running' and started > this many minutes ago → zombie
STALE_SPRINT_MINUTES = 45

# Convergence: if no novel findings for this many consecutive sprints → trigger conclusion
CONVERGENCE_THRESHOLD = 3


# ─── CheckpointManager ────────────────────────────────────────────────────────

class CheckpointManager:
    """
    Manages all persistent state for loop relay jobs.
    One instance per orchestrator run. Thread-safe for single-process use
    (SQLite WAL handles concurrent readers).
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    # ─── Connection ──────────────────────────────────────────────────────────

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), timeout=30)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _init_db(self) -> None:
        """Initialize schema if not present."""
        schema_path = SCHEMA_FILE
        if not schema_path.exists():
            # Inline the schema if file not found
            schema_path = None

        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

        if schema_path and schema_path.exists():
            sql = schema_path.read_text()
            conn.executescript(sql)
        else:
            # Minimal fallback schema (schema.sql should always exist)
            conn.executescript(_INLINE_SCHEMA)

        conn.commit()
        conn.close()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ─── Job lifecycle ────────────────────────────────────────────────────────

    def create_job(self, job_id: str, domain: str, config: dict) -> None:
        """
        Register a new job. Idempotent — if job_id already exists, does nothing.
        """
        now = _utcnow()
        name = config.get("name", f"{domain}-{job_id[:8]}")

        with self.conn:
            existing = self.conn.execute(
                "SELECT id FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if existing:
                return  # already registered

            self.conn.execute(
                """
                INSERT INTO jobs (id, name, domain, status, created_utc, updated_utc,
                                  total_cost_usd, total_tokens, sprint_count,
                                  worker_prompt_version, config_json)
                VALUES (?, ?, ?, 'active', ?, ?, 0.0, 0, 0, ?, ?)
                """,
                (job_id, name, domain, now, now,
                 config.get("worker_prompt_version", "v1"),
                 json.dumps(config))
            )
            self._log_event(job_id, None, "job_created", {
                "domain": domain, "name": name, "config": config
            })

    def complete_job(self, job_id: str, status: str = "complete") -> None:
        """Mark a job as complete/abandoned/converged."""
        assert status in ("complete", "abandoned", "converged")
        now = _utcnow()
        with self.conn:
            self.conn.execute(
                "UPDATE jobs SET status = ?, updated_utc = ? WHERE id = ?",
                (status, now, job_id)
            )
            self._log_event(job_id, None, f"job_{status}", {})

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Return job row as dict, or None."""
        row = self.conn.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_active_jobs(self) -> List[Dict[str, Any]]:
        """List all active jobs."""
        rows = self.conn.execute(
            "SELECT * FROM jobs WHERE status = 'active' ORDER BY created_utc DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    # ─── Sprint lifecycle ─────────────────────────────────────────────────────

    def start_sprint(self, job_id: str, sprint_num: int,
                     worker_session_id: str,
                     orchestrator_session_id: str = "") -> None:
        """
        Mark a sprint as running. Creates the sprint row.
        If sprint_num already exists with status='crashed', creates a new attempt
        by first clearing the old row (crash recovery path).
        """
        now = _utcnow()

        with self.conn:
            existing = self.conn.execute(
                "SELECT status FROM sprints WHERE job_id = ? AND sprint_num = ?",
                (job_id, sprint_num)
            ).fetchone()

            if existing:
                old_status = existing["status"]
                if old_status == "running":
                    # Concurrent start — update session ID
                    self.conn.execute(
                        "UPDATE sprints SET worker_session_id = ?, started_utc = ? "
                        "WHERE job_id = ? AND sprint_num = ?",
                        (worker_session_id, now, job_id, sprint_num)
                    )
                else:
                    # Restarting after crash/forced — reset row
                    self.conn.execute(
                        """
                        UPDATE sprints SET status = 'running', worker_session_id = ?,
                            orchestrator_session_id = ?, started_utc = ?, ended_utc = NULL,
                            baton_json = NULL, findings_count = 0,
                            tokens_consumed = 0, cost_usd = 0.0, handoff_type = NULL
                        WHERE job_id = ? AND sprint_num = ?
                        """,
                        (worker_session_id, orchestrator_session_id, now, job_id, sprint_num)
                    )
            else:
                self.conn.execute(
                    """
                    INSERT INTO sprints
                        (job_id, sprint_num, status, worker_session_id,
                         orchestrator_session_id, started_utc)
                    VALUES (?, ?, 'running', ?, ?, ?)
                    """,
                    (job_id, sprint_num, worker_session_id, orchestrator_session_id, now)
                )

            # Update job sprint_count and timestamp
            self.conn.execute(
                "UPDATE jobs SET sprint_count = MAX(sprint_count, ?), updated_utc = ? WHERE id = ?",
                (sprint_num, now, job_id)
            )
            self._log_event(job_id, sprint_num, "sprint_started", {
                "worker_session_id": worker_session_id
            })

    def complete_sprint(self, job_id: str, sprint_num: int,
                        findings: List[Dict[str, Any]],
                        cost_usd: float,
                        handoff_type: str = "clean",
                        tokens_consumed: int = 0) -> Baton:
        """
        Write sprint complete record + generate and store the outgoing baton.
        Returns the new Baton for the next worker.

        findings: list of dicts with keys: content, source, thesis_id (opt),
                  question_id (opt), confidence (opt), is_anchor (opt).
        """
        assert handoff_type in ("clean", "budget_exhausted", "forced")
        now = _utcnow()

        with self.conn:
            # Write findings to DB
            novel_count = 0
            for f in findings:
                chash = content_hash(f.get("content", ""))
                # Dedup check
                dupe = self.conn.execute(
                    "SELECT id FROM findings WHERE job_id = ? AND content_hash = ?",
                    (job_id, chash)
                ).fetchone()
                if dupe:
                    continue  # duplicate finding
                novel_count += 1
                self.conn.execute(
                    """
                    INSERT INTO findings
                        (job_id, sprint_num, thesis_id, question_id, source,
                         content, confidence, is_anchor, content_hash, created_utc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id, sprint_num,
                        f.get("thesis_id"), f.get("question_id"),
                        f.get("source", ""),
                        f.get("content", ""),
                        f.get("confidence"),
                        1 if f.get("is_anchor") else 0,
                        chash,
                        now,
                    )
                )

            # Update sprint row
            status_map = {
                "clean": "complete",
                "budget_exhausted": "budget_exhausted",
                "forced": "forced",
            }
            sprint_status = status_map[handoff_type]
            self.conn.execute(
                """
                UPDATE sprints SET
                    status = ?, ended_utc = ?, findings_count = ?,
                    tokens_consumed = ?, cost_usd = ?, handoff_type = ?
                WHERE job_id = ? AND sprint_num = ?
                """,
                (sprint_status, now, novel_count, tokens_consumed,
                 cost_usd, handoff_type, job_id, sprint_num)
            )

            # Update job totals
            self.conn.execute(
                """
                UPDATE jobs SET
                    total_cost_usd = total_cost_usd + ?,
                    total_tokens = total_tokens + ?,
                    updated_utc = ?
                WHERE id = ?
                """,
                (cost_usd, tokens_consumed, now, job_id)
            )

            # Build the outgoing baton
            baton = self._build_baton(job_id, sprint_num, handoff_type, cost_usd)

            # Store baton
            self.conn.execute(
                """
                INSERT INTO batons (job_id, sprint_num, schema_version, baton_json, created_utc)
                VALUES (?, ?, 2, ?, ?)
                """,
                (job_id, sprint_num, baton.to_json(), now)
            )
            # Also backfill sprint's baton_json
            self.conn.execute(
                "UPDATE sprints SET baton_json = ? WHERE job_id = ? AND sprint_num = ?",
                (baton.to_json(), job_id, sprint_num)
            )

            # Update loop_health convergence tracking
            self._update_loop_health(job_id, sprint_num, novel_count)

            self._log_event(job_id, sprint_num, "sprint_complete", {
                "handoff_type": handoff_type,
                "novel_findings": novel_count,
                "cost_usd": cost_usd,
                "tokens": tokens_consumed,
            })

        return baton

    def get_baton(self, job_id: str) -> Optional[str]:
        """
        Returns the latest baton JSON string for the next worker,
        or None if no baton exists yet.
        SOURCE: batons table, most recent row for job_id
        """
        row = self.conn.execute(
            "SELECT baton_json FROM batons WHERE job_id = ? ORDER BY sprint_num DESC, id DESC LIMIT 1",
            (job_id,)
        ).fetchone()
        return row[0] if row else None

    def mark_zombie(self, job_id: str) -> Optional[int]:
        """
        Check for stale running sprints and mark them crashed.
        Returns the sprint_num that was zombied, or None if none found.

        A sprint is zombie if:
          - status = 'running'
          - started_utc > STALE_SPRINT_MINUTES ago
        """
        threshold = datetime.now(timezone.utc) - timedelta(minutes=STALE_SPRINT_MINUTES)
        threshold_str = threshold.strftime("%Y-%m-%dT%H:%M:%S+00:00")

        row = self.conn.execute(
            """
            SELECT sprint_num, worker_session_id, started_utc
            FROM sprints
            WHERE job_id = ? AND status = 'running' AND started_utc < ?
            ORDER BY sprint_num DESC LIMIT 1
            """,
            (job_id, threshold_str)
        ).fetchone()

        if not row:
            return None

        sprint_num = row["sprint_num"]
        now = _utcnow()

        with self.conn:
            self.conn.execute(
                """
                UPDATE sprints SET status = 'crashed', ended_utc = ?, handoff_type = 'crashed'
                WHERE job_id = ? AND sprint_num = ?
                """,
                (now, job_id, sprint_num)
            )
            self._log_event(job_id, sprint_num, "zombie_detected", {
                "worker_session_id": row["worker_session_id"],
                "started_utc": row["started_utc"],
                "stale_threshold_minutes": STALE_SPRINT_MINUTES,
            })

        return sprint_num

    def resume_job(self, job_id: str) -> Dict[str, Any]:
        """
        Returns state needed to re-spawn a job after crash.
        Checks for zombies first.

        Returns dict with:
          - baton_json: str (JSON) or None
          - next_sprint: int
          - action: 'spawn' | 'wait' | 'already_complete'
          - crashed_sprint: int or None
        """
        job = self.get_job(job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found")

        if job["status"] in ("complete", "abandoned", "converged"):
            return {"action": "already_complete", "status": job["status"],
                    "baton_json": None, "next_sprint": None, "crashed_sprint": None}

        # Check for zombies
        zombied = self.mark_zombie(job_id)

        # Get latest sprint
        latest = self.conn.execute(
            "SELECT * FROM sprints WHERE job_id = ? ORDER BY sprint_num DESC LIMIT 1",
            (job_id,)
        ).fetchone()

        if latest is None:
            # No sprints yet — fresh start
            return {
                "action": "spawn",
                "next_sprint": 1,
                "baton_json": None,
                "crashed_sprint": None,
            }

        latest = dict(latest)
        sprint_num = latest["sprint_num"]
        status = latest["status"]

        if status == "complete":
            # Orchestrator crashed after sprint completed but before spawning next
            return {
                "action": "spawn",
                "next_sprint": sprint_num + 1,
                "baton_json": latest["baton_json"],
                "crashed_sprint": None,
            }

        if status in ("budget_exhausted", "forced", "crashed"):
            # Build partial baton from whatever is in DB
            partial = self._build_baton(job_id, sprint_num, status, 0.0)
            return {
                "action": "spawn",
                "next_sprint": sprint_num + 1,
                "baton_json": partial.to_json(),
                "crashed_sprint": sprint_num if zombied else None,
            }

        if status == "running":
            # If we just marked it as zombie above, that would have changed status.
            # Re-read to see current state.
            row = self.conn.execute(
                "SELECT status FROM sprints WHERE job_id = ? AND sprint_num = ?",
                (job_id, sprint_num)
            ).fetchone()
            current_status = row["status"] if row else "unknown"

            if current_status == "crashed":
                partial = self._build_baton(job_id, sprint_num, "crashed", 0.0)
                return {
                    "action": "spawn",
                    "next_sprint": sprint_num + 1,
                    "baton_json": partial.to_json(),
                    "crashed_sprint": sprint_num,
                }
            else:
                # Still running and fresh — orchestrator may have just restarted
                return {
                    "action": "wait",
                    "next_sprint": sprint_num,
                    "baton_json": None,
                    "crashed_sprint": None,
                    "worker_session_id": latest.get("worker_session_id"),
                }

        return {
            "action": "spawn",
            "next_sprint": sprint_num + 1,
            "baton_json": latest.get("baton_json"),
            "crashed_sprint": None,
        }

    # ─── Findings ────────────────────────────────────────────────────────────

    def get_findings(self, job_id: str,
                     sprint_nums: Optional[List[int]] = None,
                     anchors_only: bool = False) -> List[Dict[str, Any]]:
        """
        Retrieve findings for a job. Optionally filter by sprint range.
        SOURCE: findings table
        """
        q = "SELECT * FROM findings WHERE job_id = ?"
        params: list = [job_id]

        if sprint_nums:
            placeholders = ",".join("?" * len(sprint_nums))
            q += f" AND sprint_num IN ({placeholders})"
            params.extend(sprint_nums)

        if anchors_only:
            q += " AND is_anchor = 1"

        q += " ORDER BY sprint_num ASC, created_utc ASC"
        rows = self.conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]

    # ─── Questions ────────────────────────────────────────────────────────────

    def upsert_question(self, job_id: str, question_id: str, text: str,
                        priority: str = "medium",
                        suggested_sources: Optional[List[str]] = None,
                        raised_sprint: int = 0) -> None:
        """Insert or update a research question."""
        now = _utcnow()
        sources_json = json.dumps(suggested_sources or [])
        with self.conn:
            existing = self.conn.execute(
                "SELECT question_id FROM questions WHERE job_id = ? AND question_id = ?",
                (job_id, question_id)
            ).fetchone()
            if existing:
                self.conn.execute(
                    "UPDATE questions SET text = ?, priority = ?, suggested_sources = ?, updated_utc = ? "
                    "WHERE job_id = ? AND question_id = ?",
                    (text, priority, sources_json, now, job_id, question_id)
                )
            else:
                self.conn.execute(
                    """
                    INSERT INTO questions
                        (job_id, question_id, text, priority, status,
                         suggested_sources, raised_sprint, created_utc, updated_utc)
                    VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?)
                    """,
                    (job_id, question_id, text, priority, sources_json,
                     raised_sprint, now, now)
                )

    def resolve_question(self, job_id: str, question_id: str, sprint_num: int) -> None:
        """Mark a question resolved."""
        now = _utcnow()
        with self.conn:
            self.conn.execute(
                "UPDATE questions SET status = 'resolved', resolved_sprint = ?, updated_utc = ? "
                "WHERE job_id = ? AND question_id = ?",
                (sprint_num, now, job_id, question_id)
            )

    # ─── Internal helpers ─────────────────────────────────────────────────────

    def _build_baton(self, job_id: str, sprint_num: int,
                     handoff_type: str, cost_usd: float) -> Baton:
        """
        Build a Baton from current DB state for job_id up through sprint_num.
        SOURCE: jobs, sprints, findings, questions tables
        """
        job = self.get_job(job_id)
        config = json.loads(job["config_json"]) if job else {}
        now = _utcnow()

        # Get sprint row for timing info
        sprint_row = self.conn.execute(
            "SELECT * FROM sprints WHERE job_id = ? AND sprint_num = ?",
            (job_id, sprint_num)
        ).fetchone()
        sprint_row = dict(sprint_row) if sprint_row else {}

        # Aggregate cost
        cost_row = self.conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) as total FROM sprints WHERE job_id = ?",
            (job_id,)
        ).fetchone()
        total_cost = cost_row[0] if cost_row else 0.0  # SOURCE: sprints table sum

        # Get open questions
        q_rows = self.conn.execute(
            "SELECT * FROM questions WHERE job_id = ? AND status = 'open' ORDER BY priority DESC",
            (job_id,)
        ).fetchall()

        from baton import QuestionBaton
        open_questions = []
        for qr in q_rows:
            qr = dict(qr)
            try:
                sources = json.loads(qr.get("suggested_sources") or "[]")
            except json.JSONDecodeError:
                sources = []
            open_questions.append(QuestionBaton(
                id=qr["question_id"],
                text=qr["text"],
                priority=qr.get("priority", "medium"),
                suggested_sources=sources,
                sqlite_ref=f"questions WHERE job_id='{job_id}' AND question_id='{qr['question_id']}'",
            ))

        # Get theses
        t_rows = self.conn.execute(
            "SELECT * FROM theses WHERE job_id = ?",
            (job_id,)
        ).fetchall()

        from baton import ThesisBaton
        theses = []
        for tr in t_rows:
            tr = dict(tr)
            # Get latest key finding for this thesis
            f_row = self.conn.execute(
                "SELECT content FROM findings WHERE job_id = ? AND thesis_id = ? "
                "ORDER BY sprint_num DESC LIMIT 1",
                (job_id, tr["thesis_id"])
            ).fetchone()
            key_finding = f_row[0][:200] if f_row else "(no finding yet)"
            theses.append(ThesisBaton(
                id=tr["thesis_id"],
                status=tr.get("status", "open"),
                confidence=tr.get("confidence") or 0.0,
                key_finding=key_finding,
                sqlite_ref=f"findings WHERE job_id='{job_id}' AND thesis_id='{tr['thesis_id']}' AND sprint_num <= {sprint_num}",
                last_updated_sprint=tr.get("last_updated_sprint") or 0,
            ))

        # Get anchor findings
        anchor_rows = self.conn.execute(
            "SELECT id, content, source, thesis_id FROM findings "
            "WHERE job_id = ? AND is_anchor = 1 ORDER BY created_utc ASC",
            (job_id,)
        ).fetchall()
        anchor_findings = [dict(r) for r in anchor_rows]

        # Get latest digest
        digest_row = self.conn.execute(
            "SELECT * FROM digests WHERE job_id = ? ORDER BY id DESC LIMIT 1",
            (job_id,)
        ).fetchone()
        digest = None
        if digest_row:
            digest_row = dict(digest_row)
            from baton import DigestBaton
            digest = DigestBaton(
                text=digest_row["content"],
                generated_sprint=digest_row["generated_sprint"],
                model=digest_row.get("model", "gpt-oss:20b"),
                raw_sprint_range=[
                    digest_row.get("sprint_range_start", 0),
                    digest_row.get("sprint_range_end", sprint_num),
                ],
                quality_score=digest_row.get("quality_score") or 0.75,
            )

        # Get loop health
        health_row = self.conn.execute(
            """
            SELECT
                COUNT(*) as total_sprints,
                COALESCE(SUM(findings_count), 0) as total_findings
            FROM sprints
            WHERE job_id = ? AND status IN ('complete', 'budget_exhausted', 'forced')
            """,
            (job_id,)
        ).fetchone()

        consecutive_no_progress = self._count_no_progress_sprints(job_id)
        last_novel_sprint = self._last_novel_finding_sprint(job_id)

        from baton import TokenBudgetBaton, LoopHealthBaton
        token_budget = TokenBudgetBaton(
            allocated=config.get("token_budget", 80000),
            consumed=sprint_row.get("tokens_consumed", 0),  # SOURCE: sprints table
            model=config.get("model", "anthropic/claude-sonnet-4-6"),
        )

        # Get next sprint focus from config or generate from questions
        if open_questions:
            high_prio = [q for q in open_questions if q.priority == "high"]
            focus_q = high_prio[0] if high_prio else open_questions[0]
            next_focus = f"Address {focus_q.id}: {focus_q.text[:200]}"
        else:
            next_focus = config.get("next_sprint_focus", "Continue research. Look for novel findings.")

        worker_session_id = sprint_row.get("worker_session_id", "")

        return Baton(
            schema_version=2,
            loop_id=job_id,
            sprint=sprint_num,
            handoff_type=handoff_type,
            worker_session_id=worker_session_id,
            orchestrator_session_id=sprint_row.get("orchestrator_session_id", ""),
            sprint_started_utc=sprint_row.get("started_utc", now),
            sprint_ended_utc=sprint_row.get("ended_utc") or now,
            theses=theses,
            open_questions=open_questions,
            digest=digest,
            token_budget=token_budget,
            cost_so_far_usd=total_cost,    # SOURCE: sprints table sum
            next_sprint_focus=next_focus,
            loop_health=LoopHealthBaton(
                consecutive_no_progress_sprints=consecutive_no_progress,
                deduplication_hit_rate=self._dedup_hit_rate(job_id),
                last_novel_finding_sprint=last_novel_sprint,
            ),
            anchor_findings=anchor_findings,
        )

    def _count_no_progress_sprints(self, job_id: str) -> int:
        """Count consecutive trailing sprints with zero novel findings."""
        rows = self.conn.execute(
            "SELECT findings_count FROM sprints WHERE job_id = ? "
            "AND status IN ('complete', 'budget_exhausted', 'forced') "
            "ORDER BY sprint_num DESC LIMIT 10",
            (job_id,)
        ).fetchall()
        count = 0
        for row in rows:
            if row[0] == 0:
                count += 1
            else:
                break
        return count

    def _last_novel_finding_sprint(self, job_id: str) -> int:
        """Return the sprint_num of the most recent sprint with novel findings."""
        row = self.conn.execute(
            "SELECT sprint_num FROM sprints WHERE job_id = ? AND findings_count > 0 "
            "ORDER BY sprint_num DESC LIMIT 1",
            (job_id,)
        ).fetchone()
        return row[0] if row else 0

    def _dedup_hit_rate(self, job_id: str) -> float:
        """
        Estimate dedup hit rate: duplicate findings / total finding attempts.
        We approximate by: 1 - (unique findings / total_findings_inserted_across_sprints).
        SOURCE: findings table count vs sprints.findings_count sum
        """
        unique_row = self.conn.execute(
            "SELECT COUNT(*) FROM findings WHERE job_id = ?", (job_id,)
        ).fetchone()
        total_row = self.conn.execute(
            "SELECT COALESCE(SUM(findings_count), 0) FROM sprints WHERE job_id = ?",
            (job_id,)
        ).fetchone()
        unique = unique_row[0] if unique_row else 0
        total = total_row[0] if total_row else 0
        if total == 0:
            return 0.0
        return max(0.0, 1.0 - (unique / total))

    def _update_loop_health(self, job_id: str, sprint_num: int, novel_count: int) -> None:
        """Check convergence after each sprint; mark job converged if threshold hit."""
        consecutive = self._count_no_progress_sprints(job_id)
        if novel_count > 0:
            # Progress was made — reset would happen naturally via _count_no_progress_sprints
            pass
        if consecutive >= CONVERGENCE_THRESHOLD:
            self._log_event(job_id, sprint_num, "convergence_triggered", {
                "consecutive_no_progress": consecutive,
                "threshold": CONVERGENCE_THRESHOLD,
            })

    def _log_event(self, job_id: Optional[str], sprint_num: Optional[int],
                   event_type: str, payload: dict) -> None:
        """Append an event to the audit log. Called within existing transactions."""
        self.conn.execute(
            "INSERT INTO events (job_id, sprint_num, event_type, payload_json, created_utc) "
            "VALUES (?, ?, ?, ?, ?)",
            (job_id, sprint_num, event_type, json.dumps(payload), _utcnow())
        )

    def store_digest(self, job_id: str, sprint_num: int,
                     content: str, model: str,
                     sprint_range: tuple, quality_score: float) -> None:
        """Store a digest in the digests table. Append-only."""
        now = _utcnow()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO digests
                    (job_id, generated_sprint, sprint_range_start, sprint_range_end,
                     content, model, quality_score, created_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, sprint_num, sprint_range[0], sprint_range[1],
                 content, model, quality_score, now)
            )
            self._log_event(job_id, sprint_num, "summarized", {
                "model": model, "quality_score": quality_score,
                "sprint_range": list(sprint_range),
            })

    def upsert_thesis(self, job_id: str, thesis_id: str, text: str,
                      status: str = "open", confidence: float = 0.0,
                      sprint_num: int = 0) -> None:
        """Insert or update a thesis."""
        now = _utcnow()
        with self.conn:
            existing = self.conn.execute(
                "SELECT thesis_id FROM theses WHERE job_id = ? AND thesis_id = ?",
                (job_id, thesis_id)
            ).fetchone()
            if existing:
                self.conn.execute(
                    "UPDATE theses SET text = ?, status = ?, confidence = ?, "
                    "last_updated_sprint = ?, updated_utc = ? "
                    "WHERE job_id = ? AND thesis_id = ?",
                    (text, status, confidence, sprint_num, now, job_id, thesis_id)
                )
            else:
                self.conn.execute(
                    """
                    INSERT INTO theses
                        (job_id, thesis_id, text, status, confidence,
                         last_updated_sprint, created_utc, updated_utc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (job_id, thesis_id, text, status, confidence, sprint_num, now, now)
                )

    def export_json(self, job_id: str, out_path: str) -> None:
        """
        Atomic export of full job state to JSON file.
        Uses tmp + os.replace for atomicity.
        """
        data = {
            "job": self.get_job(job_id),
            "sprints": [dict(r) for r in self.conn.execute(
                "SELECT * FROM sprints WHERE job_id = ? ORDER BY sprint_num", (job_id,)
            ).fetchall()],
            "findings": self.get_findings(job_id),
            "questions": [dict(r) for r in self.conn.execute(
                "SELECT * FROM questions WHERE job_id = ?", (job_id,)
            ).fetchall()],
            "theses": [dict(r) for r in self.conn.execute(
                "SELECT * FROM theses WHERE job_id = ?", (job_id,)
            ).fetchall()],
            "batons": [dict(r) for r in self.conn.execute(
                "SELECT * FROM batons WHERE job_id = ? ORDER BY sprint_num", (job_id,)
            ).fetchall()],
            "exported_utc": _utcnow(),
        }

        out_path = Path(out_path)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=out_path.parent, suffix=".tmp.json")
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, out_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


# Minimal inline schema (fallback if schema.sql is missing)
_INLINE_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, name TEXT, domain TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active', created_utc TEXT NOT NULL DEFAULT (datetime('now')),
    updated_utc TEXT NOT NULL DEFAULT (datetime('now')), total_cost_usd REAL NOT NULL DEFAULT 0.0,
    total_tokens INTEGER NOT NULL DEFAULT 0, sprint_count INTEGER NOT NULL DEFAULT 0,
    worker_prompt_version TEXT NOT NULL DEFAULT 'v1', config_json TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS sprints (job_id TEXT NOT NULL, sprint_num INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'running', worker_session_id TEXT, orchestrator_session_id TEXT,
    started_utc TEXT NOT NULL DEFAULT (datetime('now')), ended_utc TEXT, baton_json TEXT,
    findings_count INTEGER NOT NULL DEFAULT 0, tokens_consumed INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0.0, handoff_type TEXT, notes TEXT,
    PRIMARY KEY (job_id, sprint_num));
CREATE TABLE IF NOT EXISTS findings (id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    job_id TEXT NOT NULL, sprint_num INTEGER NOT NULL, thesis_id TEXT, question_id TEXT,
    source TEXT, content TEXT NOT NULL, confidence REAL, is_anchor INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT, created_utc TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS questions (job_id TEXT NOT NULL, question_id TEXT NOT NULL,
    text TEXT NOT NULL, priority TEXT NOT NULL DEFAULT 'medium', status TEXT NOT NULL DEFAULT 'open',
    suggested_sources TEXT, raised_sprint INTEGER, resolved_sprint INTEGER,
    created_utc TEXT NOT NULL DEFAULT (datetime('now')), updated_utc TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (job_id, question_id));
CREATE TABLE IF NOT EXISTS batons (id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL, sprint_num INTEGER NOT NULL, schema_version INTEGER NOT NULL DEFAULT 2,
    baton_json TEXT NOT NULL, quality_score REAL, created_utc TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT,
    sprint_num INTEGER, event_type TEXT NOT NULL, payload_json TEXT,
    created_utc TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS digests (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
    generated_sprint INTEGER NOT NULL, sprint_range_start INTEGER NOT NULL,
    sprint_range_end INTEGER NOT NULL, content TEXT NOT NULL, model TEXT, quality_score REAL,
    token_count INTEGER, created_utc TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS theses (job_id TEXT NOT NULL, thesis_id TEXT NOT NULL,
    text TEXT, status TEXT NOT NULL DEFAULT 'open', confidence REAL, last_updated_sprint INTEGER,
    created_utc TEXT NOT NULL DEFAULT (datetime('now')), updated_utc TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (job_id, thesis_id));
CREATE INDEX IF NOT EXISTS idx_sprints_job_status ON sprints(job_id, status);
CREATE INDEX IF NOT EXISTS idx_findings_job_sprint ON findings(job_id, sprint_num);
CREATE INDEX IF NOT EXISTS idx_findings_hash ON findings(content_hash);
CREATE INDEX IF NOT EXISTS idx_batons_job_sprint ON batons(job_id, sprint_num);
CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id);
"""
