"""Local-only faceted search UI. Does not serve originals as static files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from bhava_library.config import Settings
from bhava_library.infrastructure.catalog_queries import (
    PREFERRED_LOCAL_FILE_JOIN,
    RESOURCE_REVIEW_STATE_SQL,
)
from bhava_library.infrastructure.database import Database

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

FILTER_DIMENSIONS = (
    "content-form",
    "audience",
    "program-use",
    "topic",
    "festival",
    "language",
    "production-opportunity",
)


def is_allowed_original_path(settings: Settings, relative_path: str) -> bool:
    """Reject paths outside data/originals and data/quarantine."""
    norm = relative_path.replace("\\", "/").lstrip("/")
    if not norm or ".." in Path(norm).parts:
        return False
    if not (norm.startswith("data/originals/") or norm.startswith("data/quarantine/")):
        return False
    originals = settings.data_dir.joinpath("originals").resolve()
    quarantine = settings.quarantine_dir.resolve()
    candidates = [(settings.repo_root / norm).resolve()]
    if norm.startswith("data/"):
        candidates.append((settings.data_dir / norm.removeprefix("data/").lstrip("/")).resolve())
    for full in candidates:
        try:
            if full.is_relative_to(originals) or full.is_relative_to(quarantine):
                return True
        except (OSError, ValueError):
            continue
    return False


def _facet_options(db: Database, dimension: str) -> list[str]:
    rows = db.execute(
        """
        SELECT DISTINCT term
        FROM resource_classifications
        WHERE dimension = ?
        ORDER BY term
        """,
        (dimension,),
    )
    return [str(row["term"]) for row in rows]


def _program_options(db: Database) -> list[str]:
    rows = db.execute(
        """
        SELECT value FROM (
          SELECT term AS value FROM resource_classifications WHERE dimension = 'program-use'
          UNION SELECT program AS value FROM program_mappings
          UNION SELECT collection AS value FROM program_mappings WHERE collection IS NOT NULL
        )
        ORDER BY value
        """
    )
    return [str(row["value"]) for row in rows]


def _search_rows(
    db: Database,
    *,
    q: str,
    content_form: str,
    audience: str,
    age: int | None,
    program: str,
    topic: str,
    festival: str,
    language: str,
    production_opportunity: str,
    review_state: str,
    quarantine: str,
    duplicates: str,
) -> list[dict[str, Any]]:
    clauses = ["r.removed_at IS NULL"]
    params: list[object] = []

    if q.strip():
        clauses.append(
            "("
            "COALESCE(rn.display_title, r.title_original) LIKE ? "
            "OR r.title_original LIKE ? "
            "OR COALESCE(rn.slug, '') LIKE ?"
            ")"
        )
        like = f"%{q.strip()}%"
        params.extend([like, like, like])

    dimension_filters = {
        "content-form": content_form,
        "audience": audience,
        "topic": topic,
        "festival": festival,
        "language": language,
        "production-opportunity": production_opportunity,
    }
    for dimension, value in dimension_filters.items():
        if not value:
            continue
        clauses.append(
            "EXISTS ("
            "SELECT 1 FROM resource_classifications rc "
            "WHERE rc.resource_id = r.resource_id AND rc.dimension = ? AND rc.term = ?"
            ")"
        )
        params.extend([dimension, value])

    if age is not None:
        clauses.append(
            "EXISTS ("
            "SELECT 1 FROM educational_profiles ep "
            "WHERE ep.resource_id = r.resource_id "
            "AND (ep.age_min IS NULL OR ep.age_min <= ?) "
            "AND (ep.age_max IS NULL OR ep.age_max >= ?)"
            ")"
        )
        params.extend([age, age])

    if program:
        clauses.append(
            "("
            "EXISTS (SELECT 1 FROM resource_classifications rc "
            "WHERE rc.resource_id = r.resource_id "
            "AND rc.dimension = 'program-use' AND rc.term = ?) "
            "OR EXISTS (SELECT 1 FROM program_mappings pm "
            "WHERE pm.resource_id = r.resource_id "
            "AND (pm.program = ? OR pm.collection = ?))"
            ")"
        )
        params.extend([program, program, program])

    if review_state:
        clauses.append(f"({RESOURCE_REVIEW_STATE_SQL}) = ?")
        params.append(review_state)

    if quarantine == "yes":
        clauses.append(
            "EXISTS (SELECT 1 FROM local_files qf WHERE qf.resource_id = r.resource_id "
            "AND (qf.quarantine_reason IS NOT NULL "
            "OR qf.relative_path LIKE 'data/quarantine/%'))"
        )
    elif quarantine == "no":
        clauses.append(
            "NOT EXISTS (SELECT 1 FROM local_files qf WHERE qf.resource_id = r.resource_id "
            "AND (qf.quarantine_reason IS NOT NULL "
            "OR qf.relative_path LIKE 'data/quarantine/%'))"
        )

    if duplicates == "yes":
        clauses.append(
            "EXISTS (SELECT 1 FROM local_files df WHERE df.resource_id = r.resource_id "
            "AND df.duplicate_of_file_id IS NOT NULL)"
        )
    elif duplicates == "no":
        clauses.append(
            "NOT EXISTS (SELECT 1 FROM local_files df WHERE df.resource_id = r.resource_id "
            "AND df.duplicate_of_file_id IS NOT NULL)"
        )

    sql = f"""
        SELECT r.resource_id,
               COALESCE(rn.display_title, r.title_original) AS display_title,
               r.title_original, r.media_type, r.media_format,
               r.theme, r.source_label, r.status,
               lf.relative_path, lf.quarantine_reason, lf.duplicate_of_file_id,
               (
                 SELECT GROUP_CONCAT(rc.term, ', ')
                 FROM resource_classifications rc
                 WHERE rc.resource_id = r.resource_id AND rc.dimension = 'content-form'
               ) AS content_forms,
               ({RESOURCE_REVIEW_STATE_SQL}) AS review_state
        FROM resources r
        LEFT JOIN resource_names rn ON rn.resource_id = r.resource_id
        {PREFERRED_LOCAL_FILE_JOIN}
        WHERE {" AND ".join(clauses)}
        ORDER BY COALESCE(rn.display_title, r.title_original)
        LIMIT 100
    """  # nosec B608 — clauses are fixed SQL fragments; values are bound params
    with db.session() as conn:
        return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(
        title="Bhāva Library Local Search",
        docs_url="/docs",
        redoc_url=None,
    )
    db = Database(settings.catalog_db)
    db.migrate()

    @app.get("/", response_class=HTMLResponse)
    def home(
        request: Request,
        q: str = Query(""),
        content_form: str = Query(""),
        audience: str = Query(""),
        age: int | None = Query(None, ge=0, le=120),
        program: str = Query(""),
        topic: str = Query(""),
        festival: str = Query(""),
        language: str = Query(""),
        production_opportunity: str = Query(""),
        review_state: str = Query(""),
        quarantine: str = Query(""),
        duplicates: str = Query(""),
    ) -> HTMLResponse:
        counts = db.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM resources WHERE removed_at IS NULL) AS resources,
              (SELECT COUNT(*) FROM local_files) AS local_files,
              (SELECT COUNT(*) FROM resource_classifications) AS classifications,
              (SELECT COUNT(*) FROM resource_names) AS display_names,
              (SELECT COUNT(*) FROM local_files
               WHERE quarantine_reason IS NOT NULL
                  OR relative_path LIKE 'data/quarantine/%') AS quarantined,
              (SELECT COUNT(*) FROM local_files WHERE duplicate_of_file_id IS NOT NULL) AS duplicates
            """
        )[0]
        rows = _search_rows(
            db,
            q=q,
            content_form=content_form,
            audience=audience,
            age=age,
            program=program,
            topic=topic,
            festival=festival,
            language=language,
            production_opportunity=production_opportunity,
            review_state=review_state,
            quarantine=quarantine,
            duplicates=duplicates,
        )
        safe_rows = []
        for row in rows:
            rel = row.get("relative_path")
            if rel and not is_allowed_original_path(settings, str(rel)):
                row = {**row, "relative_path": None, "path_blocked": True}
            safe_rows.append(row)
        return TEMPLATES.TemplateResponse(
            request=request,
            name="search.html",
            context={
                "q": q,
                "rows": safe_rows,
                "project": settings.project.name,
                "counts": dict(counts),
                "filters": {
                    "content_form": content_form,
                    "audience": audience,
                    "age": age,
                    "program": program,
                    "topic": topic,
                    "festival": festival,
                    "language": language,
                    "production_opportunity": production_opportunity,
                    "review_state": review_state,
                    "quarantine": quarantine,
                    "duplicates": duplicates,
                },
                "options": {
                    "content_form": _facet_options(db, "content-form"),
                    "audience": _facet_options(db, "audience"),
                    "program": _program_options(db),
                    "topic": _facet_options(db, "topic"),
                    "festival": _facet_options(db, "festival"),
                    "language": _facet_options(db, "language"),
                    "production_opportunity": _facet_options(db, "production-opportunity"),
                    "review_state": ["auto_accepted", "needs_review"],
                },
                "bind_note": "127.0.0.1 localhost only — originals are not served as static files.",
            },
        )

    @app.get("/resource/{resource_id}", response_class=HTMLResponse)
    def resource_detail(request: Request, resource_id: str) -> HTMLResponse:
        rows = db.execute(
            f"""
            SELECT r.resource_id,
                   COALESCE(rn.display_title, r.title_original) AS display_title,
                   rn.display_filename, rn.slug, rn.ascii_aliases_json,
                   r.title_original, r.media_type, r.media_format, r.theme,
                   r.source_label, r.language, r.status, r.original_url, r.resolved_url,
                   lf.relative_path, lf.size_bytes, lf.sha256, lf.quarantine_reason,
                   lf.duplicate_of_file_id, tm.payload_json AS technical_json
            FROM resources r
            LEFT JOIN resource_names rn ON rn.resource_id = r.resource_id
            {PREFERRED_LOCAL_FILE_JOIN}
            LEFT JOIN technical_metadata tm ON tm.resource_id = r.resource_id
            WHERE r.resource_id = ?
            """,  # nosec B608 — fixed reusable SQL fragment
            (resource_id,),
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Resource not found")
        resource = dict(rows[0])
        rel = resource.get("relative_path")
        if rel and not is_allowed_original_path(settings, str(rel)):
            resource["relative_path"] = None
            resource["path_blocked"] = True

        classifications = [
            dict(row)
            for row in db.execute(
                """
                SELECT dimension, term, confidence, source, rule_version, review_state
                FROM resource_classifications
                WHERE resource_id = ?
                ORDER BY dimension, term
                """,
                (resource_id,),
            )
        ]
        evidence = [
            dict(row)
            for row in db.execute(
                """
                SELECT dimension, term, classifier, excerpt, confidence, rule_version
                FROM classification_evidence
                WHERE resource_id = ?
                ORDER BY dimension, term, classifier
                """,
                (resource_id,),
            )
        ]
        candidates = [
            dict(row)
            for row in db.execute(
                """
                SELECT pc.candidate_id, pc.product_type, pc.score, pc.status,
                       sd.review_state AS dossier_state,
                       ic.similarity_status
                FROM production_candidates pc
                LEFT JOIN source_dossiers sd ON sd.candidate_id = pc.candidate_id
                LEFT JOIN independent_creation_records ic ON ic.candidate_id = pc.candidate_id
                WHERE pc.resource_id = ?
                ORDER BY pc.candidate_id
                """,
                (resource_id,),
            )
        ]
        return TEMPLATES.TemplateResponse(
            request=request,
            name="detail.html",
            context={
                "project": settings.project.name,
                "resource": resource,
                "classifications": classifications,
                "evidence": evidence,
                "candidates": candidates,
                "bind_note": "127.0.0.1 localhost only — originals are not served as static files.",
            },
        )

    @app.get("/path-check")
    def path_check(path: str = Query("")) -> dict[str, bool]:
        allowed = is_allowed_original_path(settings, path)
        if not allowed:
            raise HTTPException(status_code=403, detail="Path outside allowed originals/quarantine")
        return {"allowed": True}

    return app
