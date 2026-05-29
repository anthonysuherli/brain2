"""SQLiteStore — the free/local-tier Store over SQLite + sqlite-vec.

    SQLiteStore(db_path) ──► sqlite3 conn (+ vec0 virtual table) ──► local file

This is the single-user, no-auth counterpart to SupabaseStore. It mirrors the
Postgres tables minus the tenancy machinery: there is one synthetic org
(``org_id = "local"``), find-or-create resolves projects/KBs by name, and vector
search is sqlite-vec's brute-force ``vec_distance_cosine`` over a join (the
reliable path — no ANN index needed at local scale).

**Return-shape parity is load-bearing.** Every method returns the same dict /
list-of-dicts shape SupabaseStore returns (same keys, same JSON-decoded values)
so the engine cannot tell the two backends apart. In particular:
  * findings expose ``id, title, content, category, confidence, tags,
    provenance, created_at`` (list view drops ``content``/``provenance``);
  * ``match_findings`` rows additionally carry ``similarity`` (= 1 - cosine
    distance), filtered by ``min_similarity`` and ordered desc;
  * the synopsis row uses ``finding_count_at_build`` (NOT ``finding_count``) —
    the key ``agent/synopsis.should_rebuild`` and ``load_synopsis`` read.

**Connection / threading.** One long-lived connection opened with
``check_same_thread=False`` and ``row_factory = sqlite3.Row``. FastAPI background
tasks and the async methods may touch the store from different threads; SQLite
serializes writes internally and our ops are short, so a single shared
connection is simplest and correct here. ``tags``/``provenance``/``content``/
``finding_ids`` are stored as JSON text and decoded on read.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import sqlite_vec
from sqlite_vec import serialize_float32

# Synthetic single-tenant org for the local tier.
_ORG = "local"

# Column lists kept in lockstep with findings/service.py + the match RPC.
_FINDING_COLS = ("id", "title", "content", "category", "confidence", "tags", "provenance", "created_at")
_FINDING_LIST_COLS = ("id", "title", "category", "confidence", "tags", "created_at")
# match_findings returns the full finding minus created_at, plus a computed similarity.
_FINDING_MATCH_COLS = ("id", "title", "content", "category", "confidence", "tags", "provenance")

LIST_DEFAULT_LIMIT = 20
LIST_MAX_LIMIT = 100

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, name TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS kbs (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, project_id TEXT NOT NULL, name TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS findings (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, kb_id TEXT NOT NULL,
  title TEXT, content TEXT, category TEXT, confidence REAL,
  tags TEXT, provenance TEXT, created_at TEXT NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS vec_findings USING vec0(finding_id TEXT, embedding float[1536]);
CREATE TABLE IF NOT EXISTS kb_synopsis (
  kb_id TEXT PRIMARY KEY, org_id TEXT, content TEXT,
  finding_count_at_build INTEGER, model TEXT, built_at TEXT);
CREATE TABLE IF NOT EXISTS explorations (
  id TEXT PRIMARY KEY, org_id TEXT, kb_id TEXT NOT NULL, prompt TEXT,
  status TEXT, error TEXT, finding_ids TEXT, started_at TEXT, completed_at TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_findings_kb ON findings(kb_id);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_db_path() -> str:
    """``BRAIN2_DB_PATH`` if set, else ``~/.brain2/brain.db`` (dir created)."""
    env = os.environ.get("BRAIN2_DB_PATH")
    if env:
        return env
    home = Path.home() / ".brain2"
    home.mkdir(parents=True, exist_ok=True)
    return str(home / "brain.db")


class SQLiteStore:
    """Store backed by SQLite + sqlite-vec. Single synthetic org ``"local"``."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or _default_db_path()
        self._conn = self._connect(self.db_path)
        self._ensure_schema()

    @staticmethod
    def _connect(db_path: str) -> sqlite3.Connection:
        """Open a connection with sqlite-vec loaded and Row factory.

        File-backed DBs use WAL + a 5s ``busy_timeout`` so a background
        ``explore`` write and a foreground ``capture``/``insert_findings`` write
        block-and-retry instead of raising ``database is locked``. WAL is skipped
        for ``:memory:`` (where it is unsupported/pointless); ``busy_timeout`` is
        harmless everywhere."""
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        conn.execute("PRAGMA busy_timeout=5000")
        if db_path != ":memory:":
            conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def close(self) -> None:
        """Close the underlying connection. Explicit — no atexit/__del__ magic."""
        self._conn.close()

    def __enter__(self) -> "SQLiteStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _ensure_schema(self) -> None:
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # --- findings — hot path -------------------------------------------------

    async def match_findings(
        self,
        kb_id: str,
        query_embedding: list[float],
        match_count: int,
        min_similarity: float,
    ) -> list[dict]:
        """Cosine KNN over vec_findings joined to findings; rows carry `similarity`.

        Mirrors the Postgres ``match_findings`` RPC: returns ``id, title,
        content, category, confidence, tags, provenance, similarity`` ordered by
        descending similarity (= 1 - cosine distance), dropping rows below
        ``min_similarity``. JSON columns are decoded."""
        q = serialize_float32(query_embedding)
        select_cols = ", ".join(f"f.{c}" for c in _FINDING_MATCH_COLS)
        rows = self._conn.execute(
            f"""
            SELECT {select_cols},
                   vec_distance_cosine(v.embedding, ?) AS dist
            FROM vec_findings v JOIN findings f ON f.id = v.finding_id
            WHERE f.kb_id = ?
            ORDER BY dist LIMIT ?;
            """,
            (q, kb_id, match_count),
        ).fetchall()
        out: list[dict] = []
        for r in rows:
            similarity = 1.0 - float(r["dist"])
            if similarity < min_similarity:
                continue
            out.append(
                {
                    "id": r["id"],
                    "title": r["title"],
                    "content": r["content"],
                    "category": r["category"],
                    "confidence": r["confidence"],
                    "tags": _json_load(r["tags"], []),
                    "provenance": _json_load(r["provenance"], []),
                    "similarity": similarity,
                }
            )
        return out

    async def insert_findings(self, rows: list[dict]) -> list[str]:
        """Insert pre-embedded finding rows; return new ids in input order.

        Each row carries ``title, content, category, confidence, tags,
        provenance, embedding`` (and an ignored ``org_id``/``kb_id``). ``tags``/
        ``provenance`` are JSON-encoded into ``findings``; ``embedding`` goes into
        ``vec_findings`` via ``serialize_float32``. ``org_id`` is forced to
        ``"local"``; ids are generated when absent."""
        if not rows:
            return []
        ids: list[str] = []
        for row in rows:
            fid = row.get("id") or uuid.uuid4().hex
            ids.append(fid)
            self._conn.execute(
                """
                INSERT INTO findings
                  (id, org_id, kb_id, title, content, category, confidence, tags, provenance, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    fid,
                    _ORG,
                    row.get("kb_id"),
                    row.get("title"),
                    row.get("content"),
                    row.get("category"),
                    row.get("confidence"),
                    json.dumps(list(row.get("tags") or [])),
                    json.dumps(list(row.get("provenance") or [])),
                    row.get("created_at") or _now_iso(),
                ),
            )
            embedding = row.get("embedding")
            if embedding is not None:
                self._conn.execute(
                    "INSERT INTO vec_findings (finding_id, embedding) VALUES (?, ?);",
                    (fid, serialize_float32(list(embedding))),
                )
        self._conn.commit()
        return ids

    def get_finding(self, kb_id: str, finding_id: str) -> dict:
        """One finding scoped to `kb_id`. Raises if absent. JSON cols decoded."""
        r = self._conn.execute(
            f"SELECT {', '.join(_FINDING_COLS)} "
            "FROM findings WHERE kb_id = ? AND id = ? LIMIT 1;",
            (kb_id, finding_id),
        ).fetchone()
        if r is None:
            raise RuntimeError("finding not found")
        return {
            "id": r["id"],
            "title": r["title"],
            "content": r["content"],
            "category": r["category"],
            "confidence": r["confidence"],
            "tags": _json_load(r["tags"], []),
            "provenance": _json_load(r["provenance"], []),
            "created_at": r["created_at"],
        }

    def list_findings(
        self, kb_id: str, category: str | None = None, limit: int | None = None
    ) -> dict:
        """Most-recent findings in `kb_id`. Returns {"count", "findings"}.

        List view omits ``content``/``provenance`` (matching SupabaseStore);
        optional category filter; default/max limits mirror findings/service."""
        n = min(limit or LIST_DEFAULT_LIMIT, LIST_MAX_LIMIT)
        sql = (
            f"SELECT {', '.join(_FINDING_LIST_COLS)} "
            "FROM findings WHERE kb_id = ?"
        )
        params: list[object] = [kb_id]
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY created_at DESC LIMIT ?;"
        params.append(n)
        rows = self._conn.execute(sql, params).fetchall()
        findings = [
            {
                "id": r["id"],
                "title": r["title"],
                "category": r["category"],
                "confidence": r["confidence"],
                "tags": _json_load(r["tags"], []),
                "created_at": r["created_at"],
            }
            for r in rows
        ]
        return {"count": len(findings), "findings": findings}

    def delete_finding(self, kb_id: str, finding_id: str) -> dict:
        """Delete one finding from `kb_id` (and its vec row). Returns {"deleted"}."""
        self._conn.execute(
            "DELETE FROM findings WHERE kb_id = ? AND id = ?;", (kb_id, finding_id)
        )
        self._conn.execute(
            "DELETE FROM vec_findings WHERE finding_id = ?;", (finding_id,)
        )
        self._conn.commit()
        return {"deleted": finding_id}

    # --- synopsis spine ------------------------------------------------------

    def load_synopsis(self, kb_id: str) -> dict | None:
        """Current synopsis row for `kb_id`, or None.

        Keys match ``agent/synopsis.load_synopsis``: ``content`` (JSON-decoded),
        ``finding_count_at_build``, ``built_at``, ``model`` — the keys
        ``should_rebuild`` and the preamble read."""
        r = self._conn.execute(
            "SELECT content, finding_count_at_build, built_at, model "
            "FROM kb_synopsis WHERE kb_id = ? LIMIT 1;",
            (kb_id,),
        ).fetchone()
        if r is None:
            return None
        return {
            "content": _json_load(r["content"], []),
            "finding_count_at_build": r["finding_count_at_build"],
            "built_at": r["built_at"],
            "model": r["model"],
        }

    def upsert_synopsis(
        self, kb_id: str, content: list[dict], finding_count: int, model: str
    ) -> None:
        """Write the KB's synopsis spine (one current row per KB, conflict on kb_id)."""
        self._conn.execute(
            """
            INSERT INTO kb_synopsis (kb_id, org_id, content, finding_count_at_build, model, built_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(kb_id) DO UPDATE SET
              org_id = excluded.org_id,
              content = excluded.content,
              finding_count_at_build = excluded.finding_count_at_build,
              model = excluded.model,
              built_at = excluded.built_at;
            """,
            (kb_id, _ORG, json.dumps(content), finding_count, model, _now_iso()),
        )
        self._conn.commit()

    # --- exploration row lifecycle -------------------------------------------

    def create_exploration(self, org_id: str, kb_id: str, prompt: str) -> str:
        """Insert a pending exploration row; return its id. org_id forced local."""
        eid = uuid.uuid4().hex
        now = _now_iso()
        self._conn.execute(
            """
            INSERT INTO explorations (id, org_id, kb_id, prompt, status, started_at, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?);
            """,
            (eid, _ORG, kb_id, prompt, now, now),
        )
        self._conn.commit()
        return eid

    def update_exploration(self, exploration_id: str, **patch) -> None:
        """Patch exploration columns (status / completed_at / finding_ids / error).

        ``finding_ids`` is JSON-encoded; unknown keys are ignored to stay aligned
        with the explorations schema."""
        if not patch:
            return
        allowed = {"status", "error", "finding_ids", "started_at", "completed_at", "prompt"}
        cols: list[str] = []
        vals: list[object] = []
        for k, v in patch.items():
            if k not in allowed:
                continue
            cols.append(f"{k} = ?")
            vals.append(json.dumps(v) if k == "finding_ids" else v)
        if not cols:
            return
        vals.append(exploration_id)
        self._conn.execute(
            f"UPDATE explorations SET {', '.join(cols)} WHERE id = ?;", vals
        )
        self._conn.commit()

    def get_exploration(self, exploration_id: str) -> dict | None:
        """Read an exploration row, or None. `finding_ids` decoded from JSON.

        Returns the same keys SupabaseStore selects: ``id, status, finding_ids,
        completed_at, error``."""
        r = self._conn.execute(
            "SELECT id, status, finding_ids, completed_at, error "
            "FROM explorations WHERE id = ? LIMIT 1;",
            (exploration_id,),
        ).fetchone()
        if r is None:
            return None
        return {
            "id": r["id"],
            "status": r["status"],
            "finding_ids": _json_load(r["finding_ids"], []),
            "completed_at": r["completed_at"],
            "error": r["error"],
        }

    # --- tenancy — find-or-create by name ------------------------------------

    def resolve_project(self, name: str, *, create: bool) -> tuple[str, str]:
        """Resolve the named project → ("local", project_id). Find-or-create."""
        pid = self._find_or_create(
            "projects",
            {"org_id": _ORG, "name": name},
            {"id": uuid.uuid4().hex, "org_id": _ORG, "name": name, "created_at": _now_iso()},
            create,
        )
        return _ORG, pid

    def resolve_kb(self, org_id: str, project_id: str, name: str, *, create: bool) -> str:
        """Resolve the named KB within (org_id, project_id) → kb_id. Find-or-create."""
        return self._find_or_create(
            "kbs",
            {"org_id": org_id, "project_id": project_id, "name": name},
            {
                "id": uuid.uuid4().hex,
                "org_id": org_id,
                "project_id": project_id,
                "name": name,
                "created_at": _now_iso(),
            },
            create,
        )

    def _find_or_create(
        self, table: str, match: dict[str, str], insert: dict[str, object], create: bool
    ) -> str:
        """Find row by `match`; insert `insert` if absent and `create`, else raise."""
        where = " AND ".join(f"{k} = ?" for k in match)
        existing = self._conn.execute(
            f"SELECT id FROM {table} WHERE {where} LIMIT 1;", list(match.values())
        ).fetchone()
        if existing is not None:
            return existing["id"]
        if not create:
            raise RuntimeError(f"{table} {match!r} not found")
        cols = ", ".join(insert)
        placeholders = ", ".join("?" for _ in insert)
        self._conn.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({placeholders});", list(insert.values())
        )
        self._conn.commit()
        return str(insert["id"])

    # --- monitoring — best-effort --------------------------------------------

    async def record_access(
        self,
        *,
        org_id: str,
        kb_id: str,
        surface: str,
        targets,
        query_text: str | None = None,
    ) -> None:
        """No-op locally — access monitoring is a cloud-tier (billing) concern."""
        return None


def _json_load(value, default):
    """Decode a JSON text column; tolerate NULL / already-decoded values."""
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default
