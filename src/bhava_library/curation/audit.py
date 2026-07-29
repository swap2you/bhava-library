"""Machine-generated audit records for actual curation command runs."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from functools import wraps
from typing import Concatenate, ParamSpec, TypeVar

from bhava_library.config import Settings
from bhava_library.infrastructure.database import Database, utc_now

P = ParamSpec("P")
R = TypeVar("R")


def _start_run(db: Database, kind: str) -> str:
    run_id = f"{kind}-{uuid.uuid4()}"
    started_at = utc_now()
    with db.session() as conn:
        conn.execute(
            """
            INSERT INTO curation_runs(run_id, kind, started_at)
            VALUES (?, ?, ?)
            """,
            (run_id, kind, started_at),
        )
        conn.execute(
            """
            INSERT INTO curation_events(ts, run_id, kind, payload_json)
            VALUES (?, ?, 'started', ?)
            """,
            (started_at, run_id, json.dumps({"command": kind}, sort_keys=True)),
        )
    return run_id


def _finish_run(
    db: Database,
    run_id: str,
    *,
    state: str,
    stats: object,
) -> None:
    completed_at = utc_now()
    payload = json.dumps(stats, default=str, sort_keys=True)
    with db.session() as conn:
        conn.execute(
            """
            UPDATE curation_runs
            SET completed_at = ?, stats_json = ?
            WHERE run_id = ?
            """,
            (completed_at, payload, run_id),
        )
        conn.execute(
            """
            INSERT INTO curation_events(ts, run_id, kind, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (completed_at, run_id, state, payload),
        )


def audited_curation_command(
    kind: str,
) -> Callable[
    [Callable[Concatenate[Settings, P], R]],
    Callable[Concatenate[Settings, P], R],
]:
    """Record command start/completion/failure without implying human review."""

    def decorate(
        function: Callable[Concatenate[Settings, P], R],
    ) -> Callable[Concatenate[Settings, P], R]:
        @wraps(function)
        def wrapped(settings: Settings, *args: P.args, **kwargs: P.kwargs) -> R:
            db = Database(settings.catalog_db)
            db.migrate()
            run_id = _start_run(db, kind)
            try:
                result = function(settings, *args, **kwargs)
            except Exception as exc:
                _finish_run(
                    db,
                    run_id,
                    state="failed",
                    stats={"error_type": type(exc).__name__, "error": str(exc)},
                )
                raise
            _finish_run(db, run_id, state="completed", stats=result)
            return result

        return wrapped

    return decorate
