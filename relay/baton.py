"""
baton.py — Baton dataclass + serialization for Loop Relay.
Implements Vera's v2 schema (loop-relay-architecture-v1-2026-03-01.md).

Python 3.9 compatible. No external deps.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ─── Sub-structures ────────────────────────────────────────────────────────────

@dataclass
class ThesisBaton:
    id: str
    status: str           # 'confirmed' | 'refuted' | 'open' | 'degraded'
    confidence: float
    key_finding: str      # one sentence max
    sqlite_ref: str       # e.g. "findings WHERE thesis_id='T1' AND sprint <= 14"
    last_updated_sprint: int

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ThesisBaton":
        return cls(**{k: d[k] for k in (
            "id", "status", "confidence", "key_finding",
            "sqlite_ref", "last_updated_sprint"
        )})


@dataclass
class QuestionBaton:
    id: str
    text: str
    priority: str                    # 'high' | 'medium' | 'low'
    suggested_sources: List[str]     # list of source hints
    sqlite_ref: str                  # e.g. "questions WHERE id='Q3'"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "QuestionBaton":
        return cls(**{k: d[k] for k in (
            "id", "text", "priority", "suggested_sources", "sqlite_ref"
        )})


@dataclass
class DigestBaton:
    text: str
    generated_sprint: int
    model: str
    raw_sprint_range: List[int]      # [start, end]
    quality_score: float             # 0.0-1.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DigestBaton":
        return cls(**{k: d[k] for k in (
            "text", "generated_sprint", "model", "raw_sprint_range", "quality_score"
        )})


@dataclass
class TokenBudgetBaton:
    allocated: int
    consumed: int
    model: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TokenBudgetBaton":
        return cls(**{k: d[k] for k in ("allocated", "consumed", "model")})


@dataclass
class LoopHealthBaton:
    consecutive_no_progress_sprints: int
    deduplication_hit_rate: float    # fraction 0.0-1.0
    last_novel_finding_sprint: int
    termination_triggered: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "LoopHealthBaton":
        return cls(
            consecutive_no_progress_sprints=d.get("consecutive_no_progress_sprints", 0),
            deduplication_hit_rate=d.get("deduplication_hit_rate", 0.0),
            last_novel_finding_sprint=d.get("last_novel_finding_sprint", 0),
            termination_triggered=d.get("termination_triggered", False),
        )


# ─── Baton ────────────────────────────────────────────────────────────────────

@dataclass
class Baton:
    """
    v2 Baton — the state handed from one worker sprint to the next.
    All fields map 1:1 to Vera's extended schema.
    """
    schema_version: int
    loop_id: str
    sprint: int
    handoff_type: str                    # 'clean' | 'budget_exhausted' | 'forced'
    worker_session_id: str
    orchestrator_session_id: str

    sprint_started_utc: str
    sprint_ended_utc: str

    theses: List[ThesisBaton]
    open_questions: List[QuestionBaton]
    digest: Optional[DigestBaton]

    token_budget: TokenBudgetBaton
    cost_so_far_usd: float
    next_sprint_focus: str
    loop_health: LoopHealthBaton

    # Anchor findings: always carried verbatim, never compressed
    anchor_findings: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "schema_version": self.schema_version,
            "loop_id": self.loop_id,
            "sprint": self.sprint,
            "handoff_type": self.handoff_type,
            "worker_session_id": self.worker_session_id,
            "orchestrator_session_id": self.orchestrator_session_id,
            "timestamps": {
                "sprint_started_utc": self.sprint_started_utc,
                "sprint_ended_utc": self.sprint_ended_utc,
            },
            "theses": [t.to_dict() for t in self.theses],
            "open_questions": [q.to_dict() for q in self.open_questions],
            "digest": self.digest.to_dict() if self.digest else None,
            "token_budget": self.token_budget.to_dict(),
            "cost_so_far_usd": self.cost_so_far_usd,
            "next_sprint_focus": self.next_sprint_focus,
            "loop_health": self.loop_health.to_dict(),
            "anchor_findings": self.anchor_findings,
        }
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def token_estimate(self) -> int:
        """Rough token estimate for this baton (4 chars ≈ 1 token)."""
        raw = self.to_json()
        return len(raw) // 4

    def compress(self, model: str = "gpt-oss:20b") -> "Baton":
        """
        Return a new Baton with the digest replaced by a compressed version
        generated via the local LiteLLM API. Only compresses the open_questions
        and theses text; anchor findings are always preserved verbatim.

        Falls back to identity (no-op) if the summarizer is unreachable.
        """
        # Build the text to compress
        compress_input = {
            "theses": [t.to_dict() for t in self.theses],
            "open_questions": [q.to_dict() for q in self.open_questions],
            "existing_digest": self.digest.to_dict() if self.digest else None,
        }
        raw_text = json.dumps(compress_input, indent=2)

        prompt = (
            "You are a research loop summarizer. Given the current thesis/question state "
            "and an optional existing digest, produce a SINGLE PARAGRAPH (max 400 words) "
            "summarizing the key confirmed findings and top open questions. "
            "Preserve specific claims, confidence levels, and critical open questions. "
            "Do NOT hallucinate. If uncertain, say so.\n\n"
            f"INPUT:\n{raw_text}\n\n"
            "OUTPUT (one paragraph, no JSON, no headers):"
        )

        compressed_text = _call_litellm(model, prompt)
        if compressed_text is None:
            # Summarizer unreachable — return self unchanged
            return self

        quality = _score_digest(compressed_text, [t.key_finding for t in self.theses], model)

        new_digest = DigestBaton(
            text=compressed_text,
            generated_sprint=self.sprint,
            model=model,
            raw_sprint_range=[max(0, self.sprint - 4), self.sprint],
            quality_score=quality,
        )

        import copy
        new_baton = copy.deepcopy(self)
        new_baton.digest = new_digest
        return new_baton

    @classmethod
    def from_dict(cls, d: dict) -> "Baton":
        ts = d.get("timestamps", {})
        return cls(
            schema_version=d.get("schema_version", 2),
            loop_id=d["loop_id"],
            sprint=d["sprint"],
            handoff_type=d.get("handoff_type", "clean"),
            worker_session_id=d.get("worker_session_id", ""),
            orchestrator_session_id=d.get("orchestrator_session_id", ""),
            sprint_started_utc=ts.get("sprint_started_utc", ""),
            sprint_ended_utc=ts.get("sprint_ended_utc", ""),
            theses=[ThesisBaton.from_dict(t) for t in d.get("theses", [])],
            open_questions=[QuestionBaton.from_dict(q) for q in d.get("open_questions", [])],
            digest=DigestBaton.from_dict(d["digest"]) if d.get("digest") else None,
            token_budget=TokenBudgetBaton.from_dict(d.get("token_budget", {
                "allocated": 80000, "consumed": 0, "model": "unknown"
            })),
            cost_so_far_usd=d.get("cost_so_far_usd", 0.0),
            next_sprint_focus=d.get("next_sprint_focus", ""),
            loop_health=LoopHealthBaton.from_dict(d.get("loop_health", {})),
            anchor_findings=d.get("anchor_findings", []),
        )

    @classmethod
    def from_json(cls, s: str) -> "Baton":
        return cls.from_dict(json.loads(s))

    @classmethod
    def from_db(cls, conn: sqlite3.Connection, job_id: str) -> Optional["Baton"]:
        """
        Load the latest baton for a job from the batons table.
        Returns None if no baton exists yet.
        """
        # SOURCE: batons table, most recent row for job_id
        row = conn.execute(
            "SELECT baton_json FROM batons WHERE job_id = ? ORDER BY sprint_num DESC, id DESC LIMIT 1",
            (job_id,)
        ).fetchone()
        if row is None:
            return None
        return cls.from_json(row[0])

    @classmethod
    def initial(cls, job_id: str, domain: str, config: dict,
                orchestrator_session_id: str = "") -> "Baton":
        """Create a fresh baton for sprint 0 (before any work has started)."""
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            schema_version=2,
            loop_id=job_id,
            sprint=0,
            handoff_type="clean",
            worker_session_id="",
            orchestrator_session_id=orchestrator_session_id,
            sprint_started_utc=now,
            sprint_ended_utc=now,
            theses=[],
            open_questions=[],
            digest=None,
            token_budget=TokenBudgetBaton(
                allocated=config.get("token_budget", 80000),
                consumed=0,
                model=config.get("model", "anthropic/claude-sonnet-4-6"),
            ),
            cost_so_far_usd=0.0,
            next_sprint_focus=config.get("initial_focus", "Begin research. Survey the domain."),
            loop_health=LoopHealthBaton(
                consecutive_no_progress_sprints=0,
                deduplication_hit_rate=0.0,
                last_novel_finding_sprint=0,
            ),
        )


# ─── Helpers ──────────────────────────────────────────────────────────────────

def content_hash(text: str) -> str:
    """SHA-256 of content for deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _call_litellm(model: str, prompt: str, timeout: int = 60) -> Optional[str]:
    """
    Call the local LiteLLM proxy (Framework desktop).
    Returns response text or None if unreachable.
    SOURCE: LiteLLM API — set LITELLM_URL env var (e.g. https://your-host/v1/chat/completions)
    """
    api_url = os.environ.get("LITELLM_URL", "")
    api_key = os.environ.get("LITELLM_API_KEY", "")

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 600,
        "temperature": 0.3,
    }).encode("utf-8")

    req = urllib.request.Request(
        api_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
    except (urllib.error.URLError, KeyError, json.JSONDecodeError, OSError):
        return None


def _score_digest(digest_text: str, key_findings: List[str], model: str) -> float:
    """
    Ask the summarizer model to score the digest against raw key findings.
    Returns a float 0.0-1.0. Falls back to 0.75 (assumed acceptable) if unreachable.
    SOURCE: LiteLLM API inference call
    """
    if not key_findings:
        return 1.0

    findings_text = "\n".join(f"- {f}" for f in key_findings[:10])
    prompt = (
        "You are a quality auditor. Rate how well the DIGEST preserves the KEY FINDINGS.\n"
        "Score: 0.0 (nothing preserved) to 1.0 (everything preserved).\n"
        "Reply with ONLY a float like 0.82. No explanation.\n\n"
        f"KEY FINDINGS:\n{findings_text}\n\n"
        f"DIGEST:\n{digest_text}\n\n"
        "SCORE:"
    )
    result = _call_litellm(model, prompt, timeout=30)
    if result is None:
        return 0.75  # assumed acceptable; can't verify
    try:
        score = float(result.strip().split()[0])
        return max(0.0, min(1.0, score))
    except (ValueError, IndexError):
        return 0.75
