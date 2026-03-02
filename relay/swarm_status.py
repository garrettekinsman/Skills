"""
swarm_status.py — CLI status display for swarm.db.
Mirrors loop_status.py format but for swarm/relay jobs.

Shows: active jobs, sprint progress, baton quality scores, cost.
--discord flag outputs code-block format for Discord.

Python 3.9 compatible. No external deps.

Usage:
    python3 swarm_status.py
    python3 swarm_status.py --discord
    python3 swarm_status.py --job JOB_ID
    python3 swarm_status.py --all
    python3 swarm_status.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_DB_PATH = Path.home() / ".openclaw/workspace/projects/loop-relay/swarm.db"


# ─── Data loading ─────────────────────────────────────────────────────────────

class SwarmDB:
    def __init__(self, db_path: Path):
        if not db_path.exists():
            raise FileNotFoundError(f"swarm.db not found at {db_path}")
        self.conn = sqlite3.connect(str(db_path), timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA query_only=ON")

    def close(self) -> None:
        self.conn.close()

    def get_jobs(self, status_filter: Optional[str] = None) -> List[Dict]:
        """SOURCE: jobs table"""
        if status_filter:
            rows = self.conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY created_utc DESC",
                (status_filter,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM jobs ORDER BY created_utc DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_job(self, job_id: str) -> Optional[Dict]:
        """SOURCE: jobs table"""
        row = self.conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def get_sprints(self, job_id: str) -> List[Dict]:
        """SOURCE: sprints table"""
        rows = self.conn.execute(
            "SELECT * FROM sprints WHERE job_id = ? ORDER BY sprint_num",
            (job_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_latest_sprint(self, job_id: str) -> Optional[Dict]:
        """SOURCE: sprints table"""
        row = self.conn.execute(
            "SELECT * FROM sprints WHERE job_id = ? ORDER BY sprint_num DESC LIMIT 1",
            (job_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_latest_baton(self, job_id: str) -> Optional[Dict]:
        """SOURCE: batons table"""
        row = self.conn.execute(
            "SELECT * FROM batons WHERE job_id = ? ORDER BY sprint_num DESC, id DESC LIMIT 1",
            (job_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["_parsed"] = json.loads(d["baton_json"])
        except (json.JSONDecodeError, KeyError):
            d["_parsed"] = {}
        return d

    def get_findings_count(self, job_id: str) -> int:
        """SOURCE: findings table"""
        row = self.conn.execute(
            "SELECT COUNT(*) FROM findings WHERE job_id = ?", (job_id,)
        ).fetchone()
        return row[0] if row else 0

    def get_questions_count(self, job_id: str) -> Dict[str, int]:
        """SOURCE: questions table"""
        rows = self.conn.execute(
            "SELECT status, COUNT(*) FROM questions WHERE job_id = ? GROUP BY status",
            (job_id,)
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    def get_recent_events(self, job_id: str, limit: int = 5) -> List[Dict]:
        """SOURCE: events table"""
        rows = self.conn.execute(
            "SELECT * FROM events WHERE job_id = ? ORDER BY id DESC LIMIT ?",
            (job_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_cost_by_sprint(self, job_id: str) -> List[Dict]:
        """SOURCE: sprints table"""
        rows = self.conn.execute(
            "SELECT sprint_num, cost_usd, tokens_consumed, findings_count, status "
            "FROM sprints WHERE job_id = ? ORDER BY sprint_num",
            (job_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_db_size_bytes(self) -> int:
        """SOURCE: filesystem stat on swarm.db"""
        try:
            return DEFAULT_DB_PATH.stat().st_size
        except OSError:
            return 0


# ─── Formatting ───────────────────────────────────────────────────────────────

def _format_duration(iso_start: str, iso_end: Optional[str] = None) -> str:
    """Calculate duration between two ISO timestamps. SOURCE: timestamp arithmetic."""
    try:
        start = datetime.fromisoformat(iso_start.replace("Z", "+00:00"))
        end = (datetime.fromisoformat(iso_end.replace("Z", "+00:00"))
               if iso_end else datetime.now(timezone.utc))
        secs = int((end - start).total_seconds())
        if secs < 60:
            return f"{secs}s"
        elif secs < 3600:
            return f"{secs // 60}m{secs % 60:02d}s"
        else:
            return f"{secs // 3600}h{(secs % 3600) // 60:02d}m"
    except (ValueError, AttributeError):
        return "?"


def _status_icon(status: str) -> str:
    return {
        "active": "🔄",
        "complete": "✅",
        "converged": "🎯",
        "abandoned": "❌",
        "running": "⚡",
        "budget_exhausted": "⚠️",
        "forced": "🔴",
        "crashed": "💥",
        "summarizing": "📝",
    }.get(status, "❓")


def _progress_bar(done: int, total: int, width: int = 20) -> str:
    """Render an ASCII progress bar. SOURCE: done/total counters."""
    if total == 0:
        return "[" + "─" * width + "]"
    filled = int((done / total) * width)
    return "[" + "█" * filled + "░" * (width - filled) + f"] {done}/{total}"


def _baton_quality(baton: Optional[Dict]) -> str:
    """Extract digest quality score from baton. SOURCE: batons.baton_json field."""
    if not baton:
        return "N/A"
    parsed = baton.get("_parsed", {})
    digest = parsed.get("digest")
    if not digest:
        return "no digest"
    score = digest.get("quality_score")
    if score is None:
        return "?"
    icon = "🟢" if score >= 0.8 else ("🟡" if score >= 0.6 else "🔴")
    return f"{icon} {score:.2f}"


def _format_cost(usd: float) -> str:
    """SOURCE: total_cost_usd from jobs/sprints table."""
    if usd < 0.01:
        return f"${usd:.5f}"
    return f"${usd:.4f}"


# ─── Display builders ─────────────────────────────────────────────────────────

def build_summary_table(db: SwarmDB, jobs: List[Dict]) -> List[str]:
    """
    Build a summary table of jobs.
    All numbers sourced from DB queries.
    """
    lines = []
    lines.append("┌─ LOOP RELAY STATUS ──────────────────────────────────────────────────────┐")

    if not jobs:
        lines.append("│  No jobs found.                                                          │")
        lines.append("└──────────────────────────────────────────────────────────────────────────┘")
        return lines

    for job in jobs:
        job_id = job["id"]
        status = job["status"]
        icon = _status_icon(status)
        name = job.get("name") or job_id[:16]
        domain = job.get("domain", "?")

        latest_sprint = db.get_latest_sprint(job_id)
        sprint_num = latest_sprint["sprint_num"] if latest_sprint else 0
        max_sprints = json.loads(job.get("config_json") or "{}").get("max_sprints", "?")

        findings_count = db.get_findings_count(job_id)  # SOURCE: findings table
        cost = job.get("total_cost_usd", 0.0)           # SOURCE: jobs.total_cost_usd

        age = _format_duration(job["created_utc"])

        latest_baton = db.get_latest_baton(job_id)
        baton_qual = _baton_quality(latest_baton)

        lines.append(f"├─────────────────────────────────────────────────────────────────────────")
        lines.append(f"│ {icon} {name[:30]:<30} [{domain}]  {status}")
        lines.append(f"│   ID: {job_id}")
        lines.append(f"│   Sprint: {sprint_num}/{max_sprints}  │  Findings: {findings_count}  │  Cost: {_format_cost(cost)}  │  Age: {age}")
        lines.append(f"│   Baton quality: {baton_qual}")

        if latest_sprint and latest_sprint["status"] == "running":
            elapsed = _format_duration(latest_sprint["started_utc"])
            worker = latest_sprint.get("worker_session_id") or "?"
            lines.append(f"│   ⚡ Sprint {sprint_num} running for {elapsed}  (worker: {worker[:40]})")

        # Loop health
        if latest_baton:
            parsed = latest_baton.get("_parsed", {})
            health = parsed.get("loop_health", {})
            no_progress = health.get("consecutive_no_progress_sprints", 0)
            if no_progress >= 2:
                lines.append(f"│   ⚠️  No-progress streak: {no_progress} sprints")

    db_size = db.get_db_size_bytes()  # SOURCE: filesystem stat
    lines.append(f"├─────────────────────────────────────────────────────────────────────────")
    lines.append(f"│  DB size: {db_size / 1024:.1f} KB  │  Jobs shown: {len(jobs)}")
    lines.append("└──────────────────────────────────────────────────────────────────────────┘")
    return lines


def build_job_detail(db: SwarmDB, job_id: str) -> List[str]:
    """
    Build detailed view for a single job.
    All numbers from DB queries.
    """
    job = db.get_job(job_id)
    if not job:
        return [f"Job {job_id} not found."]

    lines = []
    status = job["status"]
    icon = _status_icon(status)
    config = json.loads(job.get("config_json") or "{}")

    lines.append(f"╔═ JOB DETAIL: {job.get('name', job_id[:16])} ══════════════════════════════════")
    lines.append(f"║  ID:      {job_id}")
    lines.append(f"║  Status:  {icon} {status}")
    lines.append(f"║  Domain:  {job.get('domain', '?')}")
    lines.append(f"║  Created: {job['created_utc']}  (age: {_format_duration(job['created_utc'])})")
    lines.append(f"║  Cost:    {_format_cost(job.get('total_cost_usd', 0.0))}  (SOURCE: sprints sum)")
    lines.append(f"║  Tokens:  {job.get('total_tokens', 0):,}  (SOURCE: sprints sum)")
    lines.append(f"║  Sprints: {job.get('sprint_count', 0)} / {config.get('max_sprints', '?')}")

    # Sprint breakdown
    sprints = db.get_sprints(job_id)  # SOURCE: sprints table
    if sprints:
        lines.append("╠═ SPRINTS ═════════════════════════════════════════════════════════════════")
        lines.append("║  #   Status              Findings  Tokens    Cost       Duration")
        lines.append("║  ─── ──────────────────  ────────  ────────  ─────────  ────────")
        for s in sprints:
            snum = str(s["sprint_num"]).rjust(3)
            sstatus = s["status"][:18].ljust(18)
            finds = str(s.get("findings_count", 0)).rjust(8)
            toks = str(s.get("tokens_consumed", 0)).rjust(8)
            cost = f"${s.get('cost_usd', 0):.5f}".rjust(9)
            dur = _format_duration(s["started_utc"], s.get("ended_utc"))
            icon_s = _status_icon(s["status"])
            lines.append(f"║  {snum} {icon_s}{sstatus}  {finds}  {toks}  {cost}  {dur}")

    # Findings summary
    findings_count = db.get_findings_count(job_id)  # SOURCE: findings table
    lines.append(f"╠═ FINDINGS ════════════════════════════════════════════════════════════════")
    lines.append(f"║  Total novel findings: {findings_count}  (SOURCE: findings table COUNT)")

    # Questions
    q_counts = db.get_questions_count(job_id)  # SOURCE: questions table
    if q_counts:
        q_str = "  ".join(f"{k}:{v}" for k, v in sorted(q_counts.items()))
        lines.append(f"╠═ QUESTIONS ═══════════════════════════════════════════════════════════════")
        lines.append(f"║  {q_str}  (SOURCE: questions table)")

    # Latest baton
    baton = db.get_latest_baton(job_id)  # SOURCE: batons table
    if baton:
        parsed = baton.get("_parsed", {})
        lines.append(f"╠═ LATEST BATON (sprint {baton.get('sprint_num', '?')}) ══════════════════")
        lines.append(f"║  Schema version: {parsed.get('schema_version', '?')}")
        lines.append(f"║  Handoff type:   {parsed.get('handoff_type', '?')}")
        lines.append(f"║  Baton quality:  {_baton_quality(baton)}")
        focus = parsed.get("next_sprint_focus", "")
        if focus:
            lines.append(f"║  Next focus:     {focus[:80]}")

        health = parsed.get("loop_health", {})
        lines.append(f"║  Loop health:")
        lines.append(f"║    no-progress streak: {health.get('consecutive_no_progress_sprints', 0)}")
        lines.append(f"║    dedup hit rate:      {health.get('deduplication_hit_rate', 0):.1%}")
        lines.append(f"║    last novel sprint:   {health.get('last_novel_finding_sprint', '?')}")

    # Recent events
    events = db.get_recent_events(job_id, limit=5)  # SOURCE: events table
    if events:
        lines.append("╠═ RECENT EVENTS ═══════════════════════════════════════════════════════════")
        for ev in reversed(events):
            ts = ev.get("created_utc", "?")[:19]
            etype = ev.get("event_type", "?")
            snum = f"s{ev['sprint_num']}" if ev.get("sprint_num") else "   "
            payload = ev.get("payload_json", "{}")
            try:
                p = json.loads(payload)
                detail = " | ".join(f"{k}={v}" for k, v in list(p.items())[:3])
            except (json.JSONDecodeError, AttributeError):
                detail = payload[:60]
            lines.append(f"║  {ts} [{snum}] {etype}: {detail[:60]}")

    lines.append("╚═══════════════════════════════════════════════════════════════════════════")
    return lines


def build_discord_output(lines: List[str]) -> str:
    """Wrap output in Discord code block."""
    inner = "\n".join(lines)
    return f"```\n{inner}\n```"


# ─── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Loop Relay swarm.db status display",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--discord", action="store_true",
                        help="Output as Discord code block")
    parser.add_argument("--job", metavar="JOB_ID",
                        help="Show detailed view for a specific job")
    parser.add_argument("--all", action="store_true",
                        help="Show all jobs (including complete/abandoned)")
    parser.add_argument("--json", action="store_true", dest="output_json",
                        help="Output raw JSON")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH),
                        help=f"Path to swarm.db (default: {DEFAULT_DB_PATH})")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        msg = f"swarm.db not found at {db_path}\nRun an orchestrator job first."
        if args.discord:
            print(f"```\n{msg}\n```")
        else:
            print(msg, file=sys.stderr)
        sys.exit(1)

    db = SwarmDB(db_path)

    try:
        if args.output_json:
            if args.job:
                job = db.get_job(args.job)
                sprints = db.get_sprints(args.job)
                baton = db.get_latest_baton(args.job)
                print(json.dumps({
                    "job": job,
                    "sprints": sprints,
                    "latest_baton": baton,
                    "findings_count": db.get_findings_count(args.job),
                    "questions": db.get_questions_count(args.job),
                }, indent=2, default=str))
            else:
                status_filter = None if args.all else "active"
                jobs = db.get_jobs(status_filter)
                print(json.dumps(jobs, indent=2, default=str))
            return

        if args.job:
            lines = build_job_detail(db, args.job)
        else:
            status_filter = None if args.all else "active"
            jobs = db.get_jobs(status_filter)  # SOURCE: jobs table
            lines = build_summary_table(db, jobs)

        output = build_discord_output(lines) if args.discord else "\n".join(lines)
        print(output)

    finally:
        db.close()


if __name__ == "__main__":
    main()
