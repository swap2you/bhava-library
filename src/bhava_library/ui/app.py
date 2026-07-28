"""Minimal local-only search UI scaffold."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from bhava_library.config import Settings
from bhava_library.infrastructure.database import Database

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Bhāva Library Local Search", docs_url=None, redoc_url=None)
    db = Database(settings.catalog_db)
    db.migrate()

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, q: str = Query("")) -> HTMLResponse:
        rows = []
        if q.strip():
            with db.session() as conn:
                rows = list(
                    conn.execute(
                        """
                        SELECT r.resource_id, r.title_original, r.media_type, r.media_format,
                               r.theme, r.source_label, r.status
                        FROM resources_fts f
                        JOIN resources r ON r.resource_id = f.resource_id
                        WHERE resources_fts MATCH ?
                        LIMIT 50
                        """,
                        (q,),
                    )
                )
        return TEMPLATES.TemplateResponse(
            request=request,
            name="search.html",
            context={"q": q, "rows": rows, "project": settings.project.name},
        )

    return app
