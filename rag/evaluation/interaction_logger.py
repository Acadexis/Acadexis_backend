"""
Acadexis — Interaction Logger (Sprint 7)
========================================
Async SQLite store for chat interaction logs and RAGAS scores.

Design (Kaizen/JIT):
  - aiosqlite for non-blocking DB access (consistent with the async stack)
  - Default DB path: backend/data/acadexis.db (gitignored directory)
  - In-memory DB for tests: inject db_path=":memory:" via fixture
  - No ORM — raw SQL is clear, fast, and has zero dependencies
  - Migration path to Postgres is one connection-string swap away

Table: interactions
  id               INTEGER PRIMARY KEY AUTOINCREMENT
  session_id       TEXT NOT NULL
  course_id        TEXT NOT NULL
  query            TEXT NOT NULL
  response         TEXT NOT NULL
  context_count    INTEGER DEFAULT 0
  bloom_level      TEXT DEFAULT 'understand'
  cache_used       INTEGER DEFAULT 0   (SQLite bool: 0/1)
  verifier_passed  INTEGER DEFAULT 1   (SQLite bool: 0/1)
  ragas_json       TEXT                (JSON-serialised RagasScores or NULL)
  timestamp        TEXT                (ISO-8601 UTC)

Usage:
  await init_db()                                 # once at startup
  await log_interaction(state, session_id, db_path)
  rows = await get_interactions(course_id, limit, offset, db_path)
  heatmap = await get_heatmap(course_id, db_path)
  summary = await get_ragas_summary(course_id, db_path)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite

from rag.schemas.analytics import (
    HeatmapEntry,
    HeatmapResponse,
    InteractionListResponse,
    InteractionRecord,
    RagasScores,
    RagasSummaryResponse,
)

logger = logging.getLogger(__name__)

# Default DB path — resolved at import time so it's easy to override in tests
_DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),  # backend/
    "data",
    "acadexis.db",
)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS interactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT    NOT NULL,
    course_id       TEXT    NOT NULL,
    query           TEXT    NOT NULL,
    response        TEXT    NOT NULL,
    context_count   INTEGER NOT NULL DEFAULT 0,
    bloom_level     TEXT    NOT NULL DEFAULT 'understand',
    cache_used      INTEGER NOT NULL DEFAULT 0,
    verifier_passed INTEGER NOT NULL DEFAULT 1,
    ragas_json      TEXT,
    timestamp       TEXT    NOT NULL
);
"""

_CREATE_WIKI_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS wikis (
    course_id       TEXT PRIMARY KEY,
    markdown_content TEXT NOT NULL,
    last_updated    TEXT NOT NULL
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_interactions_course
ON interactions (course_id, timestamp DESC);
"""


# ─────────────────────────────────────────────────────────────────────────────
# DB Lifecycle
# ─────────────────────────────────────────────────────────────────────────────

async def init_db(db_path: str = _DEFAULT_DB_PATH) -> None:
    """
    Create the interactions and wikis tables if they don't exist.
    Call once at application startup (in main.py lifespan).

    Poka-Yoke: Creates the data/ directory automatically so the app
    never fails at startup due to a missing directory.
    """
    if db_path != ":memory:":
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        await db.execute(_CREATE_TABLE_SQL)
        await db.execute(_CREATE_WIKI_TABLE_SQL)
        await db.execute(_CREATE_INDEX_SQL)
        await db.commit()

    logger.info("Interaction & Wiki DB initialised: %s", db_path)


# ─────────────────────────────────────────────────────────────────────────────
# Wiki Operations (Sprint 9)
# ─────────────────────────────────────────────────────────────────────────────

async def upsert_wiki(
    course_id: str,
    markdown_content: str,
    db_path: str = _DEFAULT_DB_PATH,
) -> None:
    """
    Save or update a compiled Markdown Wiki for a course.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """
                INSERT INTO wikis (course_id, markdown_content, last_updated)
                VALUES (?, ?, ?)
                ON CONFLICT(course_id) DO UPDATE SET
                    markdown_content = excluded.markdown_content,
                    last_updated = excluded.last_updated
                """,
                (course_id, markdown_content, timestamp),
            )
            await db.commit()
        logger.info("Upserted Wiki for course %s", course_id)
    except Exception as exc:
        logger.error("upsert_wiki failed: %s", exc)


async def get_wiki(
    course_id: str,
    db_path: str = _DEFAULT_DB_PATH,
) -> str | None:
    """
    Retrieve the compiled Markdown Wiki for a course.
    Returns None if no Wiki exists.
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT markdown_content FROM wikis WHERE course_id = ?",
                (course_id,),
            )
            row = await cursor.fetchone()
            return row[0] if row else None
    except Exception as exc:
        logger.error("get_wiki failed: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Write
# ─────────────────────────────────────────────────────────────────────────────

async def log_interaction(
    *,
    session_id: str,
    course_id: str,
    query: str,
    response: str,
    context_count: int = 0,
    bloom_level: str = "understand",
    cache_used: bool = False,
    verifier_passed: bool = True,
    ragas_scores: Optional[dict[str, Any]] = None,
    db_path: str = _DEFAULT_DB_PATH,
) -> int:
    """
    Write one interaction to the DB.

    Returns the auto-generated row ID.
    Wraps all errors — never raises to caller (fire-and-forget safe).
    """
    ragas_json = json.dumps(ragas_scores) if ragas_scores else None
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO interactions
                    (session_id, course_id, query, response, context_count,
                     bloom_level, cache_used, verifier_passed, ragas_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    course_id,
                    query,
                    response,
                    context_count,
                    bloom_level,
                    int(cache_used),
                    int(verifier_passed),
                    ragas_json,
                    timestamp,
                ),
            )
            await db.commit()
            row_id: int = cursor.lastrowid  # type: ignore[assignment]

        logger.debug(
            "Logged interaction id=%d session=%s course=%s",
            row_id,
            session_id,
            course_id,
        )
        return row_id

    except Exception as exc:
        # Kaizen/Poka-Yoke: Logging must NEVER crash the chat endpoint.
        # Errors here are non-fatal — student gets their answer regardless.
        logger.error("log_interaction failed (non-fatal): %s", exc)
        return -1


# ─────────────────────────────────────────────────────────────────────────────
# Read — Interactions
# ─────────────────────────────────────────────────────────────────────────────

def _row_to_record(row: aiosqlite.Row) -> InteractionRecord:
    """Convert a DB row tuple to an InteractionRecord Pydantic model."""
    (
        row_id, session_id, course_id, query, response,
        context_count, bloom_level, cache_used, verifier_passed,
        ragas_json, timestamp,
    ) = row

    scores_dict = json.loads(ragas_json) if ragas_json else {}
    ragas = RagasScores(**scores_dict)

    return InteractionRecord(
        id=row_id,
        session_id=session_id,
        course_id=course_id,
        query=query,
        response=response,
        context_count=context_count,
        bloom_level=bloom_level,
        cache_used=bool(cache_used),
        verifier_passed=bool(verifier_passed),
        ragas_scores=ragas,
        timestamp=datetime.fromisoformat(timestamp),
    )


async def get_interactions(
    course_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
    db_path: str = _DEFAULT_DB_PATH,
) -> InteractionListResponse:
    """Return paginated interactions for a course, newest first."""
    limit = min(max(1, limit), 200)  # clamp: 1–200
    offset = max(0, offset)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row  # type: ignore[assignment]

        total_row = await db.execute(
            "SELECT COUNT(*) FROM interactions WHERE course_id = ?", (course_id,)
        )
        total: int = (await total_row.fetchone())[0]  # type: ignore[index]

        cursor = await db.execute(
            """
            SELECT id, session_id, course_id, query, response,
                   context_count, bloom_level, cache_used, verifier_passed,
                   ragas_json, timestamp
            FROM interactions
            WHERE course_id = ?
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
            """,
            (course_id, limit, offset),
        )
        rows = await cursor.fetchall()

    return InteractionListResponse(
        course_id=course_id,
        total=total,
        limit=limit,
        offset=offset,
        interactions=[_row_to_record(tuple(r)) for r in rows],  # type: ignore[arg-type]
    )


# ─────────────────────────────────────────────────────────────────────────────
# Read — Struggle Heatmap
# ─────────────────────────────────────────────────────────────────────────────

async def get_heatmap(
    course_id: str,
    *,
    db_path: str = _DEFAULT_DB_PATH,
) -> HeatmapResponse:
    """
    Aggregate topic failure rates for the Struggle Heatmap.

    'Failure' proxy in Sprint 7: faithfulness < 0.5 (hallucination risk).
    Full topic extraction with NLP comes in Sprint 8.

    SQL notes:
      - json_extract() is native in SQLite 3.38+ (Ubuntu 22.04 ships 3.39)
      - CAST(... AS REAL) needed because SQLite stores numbers as TEXT in JSON
      - failure_rate rounded to 2dp here; HeatmapEntry validates 0.0–1.0
    """
    async with aiosqlite.connect(db_path) as db:
        total_row = await db.execute(
            "SELECT COUNT(*) FROM interactions WHERE course_id = ?", (course_id,)
        )
        total: int = (await total_row.fetchone())[0]  # type: ignore[index]

        cursor = await db.execute(
            """
            SELECT
                bloom_level                                           AS topic,
                COUNT(*)                                              AS total_attempts,
                ROUND(AVG(
                    CASE
                        WHEN ragas_json IS NOT NULL
                         AND CAST(json_extract(ragas_json, '$.faithfulness') AS REAL) < 0.5
                        THEN 1
                        ELSE 0
                    END
                ), 4)                                                 AS failure_rate,
                COUNT(DISTINCT session_id)                            AS students_affected
            FROM interactions
            WHERE course_id = ?
            GROUP BY bloom_level
            ORDER BY failure_rate DESC
            """,
            (course_id,),
        )
        rows = await cursor.fetchall()

    entries = [
        HeatmapEntry(
            topic=row[0],
            total_attempts=row[1],
            failure_rate=float(row[2] or 0.0),
            students_affected=row[3],
        )
        for row in rows
    ]

    return HeatmapResponse(
        course_id=course_id,
        total_interactions=total,
        heatmap=entries,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Read — RAGAS Summary
# ─────────────────────────────────────────────────────────────────────────────

async def get_ragas_summary(
    course_id: str,
    *,
    db_path: str = _DEFAULT_DB_PATH,
) -> RagasSummaryResponse:
    """
    Compute mean RAGAS scores across all scored interactions for a course.
    Used by the lecturer's proof-of-quality dashboard.
    """
    async with aiosqlite.connect(db_path) as db:
        row = await db.execute(
            """
            SELECT
                COUNT(*)                                                         AS total,
                SUM(CASE WHEN ragas_json IS NOT NULL THEN 1 ELSE 0 END)         AS scored,
                AVG(CAST(json_extract(ragas_json,'$.context_precision') AS REAL)) AS cp,
                AVG(CAST(json_extract(ragas_json,'$.context_recall') AS REAL))    AS cr,
                AVG(CAST(json_extract(ragas_json,'$.faithfulness') AS REAL))      AS fa,
                AVG(CAST(json_extract(ragas_json,'$.answer_relevancy') AS REAL))  AS ar
            FROM interactions
            WHERE course_id = ?
            """,
            (course_id,),
        )
        r = await row.fetchone()

    if not r or r[0] == 0:
        return RagasSummaryResponse(
            course_id=course_id,
            interaction_count=0,
            scored_count=0,
        )

    total, scored, cp, cr, fa, ar = r

    # Compute hallucination_risk from mean faithfulness
    if fa is None:
        risk = "unknown"
    elif fa >= 0.85:
        risk = "low"
    elif fa >= 0.60:
        risk = "medium"
    else:
        risk = "high"

    return RagasSummaryResponse(
        course_id=course_id,
        interaction_count=int(total),
        scored_count=int(scored or 0),
        mean_context_precision=round(cp, 4) if cp is not None else None,
        mean_context_recall=round(cr, 4) if cr is not None else None,
        mean_faithfulness=round(fa, 4) if fa is not None else None,
        mean_answer_relevancy=round(ar, 4) if ar is not None else None,
        hallucination_risk=risk,
    )
