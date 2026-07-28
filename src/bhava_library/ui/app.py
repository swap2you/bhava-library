"""Minimal local-only search UI scaffold."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from bhava_library.config import Settings
from bhava_library.infrastructure.database import Database

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


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


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(
        title="Bhāva Library Local Search",
        docs_url="/docs",
        redoc_url=None,
    )
    db = Database(settings.catalog_db)
    db.migrate()

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, q: str = Query("")) -> HTMLResponse:
        counts = db.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM resources WHERE removed_at IS NULL) AS resources,
              (SELECT COUNT(*) FROM local_files) AS local_files,
              (SELECT COUNT(*) FROM resource_classifications) AS classifications,
              (SELECT COUNT(*) FROM resource_names) AS display_names
            """
        )[0]
        rows = []
        if q.strip():
            with db.session() as conn:
                rows = list(
                    conn.execute(
                        """
                        SELECT r.resource_id,
                               COALESCE(rn.display_title, r.title_original) AS display_title,
                               r.title_original, r.media_type, r.media_format,
                               r.theme, r.source_label, r.status,
                               lf.relative_path
                        FROM resources r
                        LEFT JOIN resource_names rn ON rn.resource_id = r.resource_id
                        LEFT JOIN local_files lf ON lf.resource_id = r.resource_id
                        WHERE r.removed_at IS NULL
                          AND (
                            COALESCE(rn.display_title, r.title_original) LIKE ?
                            OR r.title_original LIKE ?
                            OR rn.slug LIKE ?
                          )
                        LIMIT 50
                        """,
                        (f"%{q}%", f"%{q}%", f"%{q}%"),
                    )
                )
        safe_rows = []
        for row in rows:
            rel = row["relative_path"]
            if rel and not is_allowed_original_path(settings, rel):
                continue
            safe_rows.append(dict(row))
        return TEMPLATES.TemplateResponse(
            request=request,
            name="search.html",
            context={
                "q": q,
                "rows": safe_rows,
                "project": settings.project.name,
                "counts": dict(counts),
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
