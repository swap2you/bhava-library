"""SQLite catalog and migrations."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bhava_library.domain.enums import ResourceStatus, validate_transition
from bhava_library.domain.errors import InvalidStateTransition

SCHEMA_VERSION = 1

MIGRATION_001 = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
  source_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  base_url TEXT NOT NULL,
  adapter TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  last_scan_at TEXT
);

CREATE TABLE IF NOT EXISTS source_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES sources(source_id),
  retrieved_at TEXT NOT NULL,
  html_path TEXT NOT NULL,
  html_sha256 TEXT NOT NULL,
  http_status INTEGER,
  final_url TEXT,
  parser_version TEXT NOT NULL,
  row_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS resources (
  resource_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES sources(source_id),
  source_row_key TEXT NOT NULL,
  title_original TEXT NOT NULL,
  title_normalized TEXT,
  level TEXT,
  media_type TEXT,
  media_format TEXT,
  theme TEXT,
  source_label TEXT,
  language TEXT,
  original_url TEXT NOT NULL,
  resolved_url TEXT,
  source_domain TEXT,
  resolution_method TEXT,
  resolution_confidence REAL,
  profile TEXT,
  priority INTEGER NOT NULL DEFAULT 100,
  status TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  removed_at TEXT,
  UNIQUE(source_id, source_row_key)
);

CREATE TABLE IF NOT EXISTS remote_objects (
  remote_object_id TEXT PRIMARY KEY,
  resource_id TEXT NOT NULL REFERENCES resources(resource_id),
  url TEXT NOT NULL,
  final_url TEXT,
  http_status INTEGER,
  mime_type TEXT,
  content_length INTEGER,
  accept_ranges INTEGER,
  etag TEXT,
  last_modified TEXT,
  probed_at TEXT
);

CREATE TABLE IF NOT EXISTS download_jobs (
  job_id TEXT PRIMARY KEY,
  resource_id TEXT NOT NULL REFERENCES resources(resource_id),
  batch_id TEXT NOT NULL,
  state TEXT NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  bytes_downloaded INTEGER NOT NULL DEFAULT 0,
  expected_bytes INTEGER,
  part_path TEXT,
  started_at TEXT,
  updated_at TEXT,
  completed_at TEXT,
  last_error_code TEXT,
  last_error_message TEXT
);

CREATE TABLE IF NOT EXISTS local_files (
  file_id TEXT PRIMARY KEY,
  resource_id TEXT NOT NULL REFERENCES resources(resource_id),
  relative_path TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  detected_type TEXT,
  verified_at TEXT,
  read_only INTEGER NOT NULL DEFAULT 0,
  duplicate_of_file_id TEXT,
  quarantine_reason TEXT
);

CREATE TABLE IF NOT EXISTS taxonomy_terms (
  term_id TEXT PRIMARY KEY,
  dimension TEXT NOT NULL,
  value TEXT NOT NULL,
  slug TEXT,
  UNIQUE(dimension, value)
);

CREATE TABLE IF NOT EXISTS resource_terms (
  resource_id TEXT NOT NULL REFERENCES resources(resource_id),
  term_id TEXT NOT NULL REFERENCES taxonomy_terms(term_id),
  PRIMARY KEY (resource_id, term_id)
);

CREATE TABLE IF NOT EXISTS events (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  kind TEXT NOT NULL,
  resource_id TEXT,
  payload_json TEXT
);

CREATE TABLE IF NOT EXISTS backups (
  backup_id TEXT PRIMARY KEY,
  target_path TEXT NOT NULL,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  file_count INTEGER,
  byte_count INTEGER,
  verification_ok INTEGER,
  restore_sample_ok INTEGER,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS original_works (
  work_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  version TEXT,
  status TEXT,
  work_type TEXT,
  project TEXT NOT NULL,
  publisher TEXT NOT NULL,
  copyright_owner TEXT NOT NULL,
  contact_email TEXT,
  location TEXT,
  created_at TEXT,
  first_published_at TEXT,
  publication_status TEXT NOT NULL,
  manifest_path TEXT,
  deposit_sha256 TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS resources_fts USING fts5(
  resource_id UNINDEXED,
  title,
  source_label,
  theme,
  media_type,
  media_format,
  level,
  language,
  description,
  extracted_text,
  notes
);
"""


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def migrate(self) -> None:
        with self.session() as conn:
            conn.executescript(MIGRATION_001)
            row = conn.execute(
                "SELECT version FROM schema_migrations WHERE version = ?",
                (SCHEMA_VERSION,),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, utc_now()),
                )

    def integrity_check(self) -> str:
        with self.session() as conn:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            return str(row[0]) if row else "unknown"

    def ensure_source(
        self,
        source_id: str,
        name: str,
        base_url: str,
        adapter: str,
    ) -> None:
        with self.session() as conn:
            existing = conn.execute(
                "SELECT source_id FROM sources WHERE source_id = ?", (source_id,)
            ).fetchone()
            if existing:
                return
            conn.execute(
                """
                INSERT INTO sources(source_id, name, base_url, adapter, enabled, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (source_id, name, base_url, adapter, utc_now()),
            )

    def set_resource_status(
        self,
        conn: sqlite3.Connection,
        resource_id: str,
        new_status: ResourceStatus,
    ) -> None:
        row = conn.execute(
            "SELECT status FROM resources WHERE resource_id = ?", (resource_id,)
        ).fetchone()
        if row is None:
            raise KeyError(resource_id)
        current = ResourceStatus(row["status"])
        if not validate_transition(current, new_status):
            raise InvalidStateTransition(f"{current} -> {new_status} for {resource_id}")
        conn.execute(
            "UPDATE resources SET status = ?, last_seen_at = ? WHERE resource_id = ?",
            (new_status.value, utc_now(), resource_id),
        )

    def add_event(
        self,
        kind: str,
        resource_id: str | None = None,
        payload_json: str | None = None,
    ) -> None:
        with self.session() as conn:
            conn.execute(
                "INSERT INTO events(ts, kind, resource_id, payload_json) VALUES (?, ?, ?, ?)",
                (utc_now(), kind, resource_id, payload_json),
            )

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self.session() as conn:
            return list(conn.execute(sql, params).fetchall())
