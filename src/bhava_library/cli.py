"""Typer CLI entry point."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from bhava_library import __version__
from bhava_library.config import Settings, load_settings
from bhava_library.constants import EXIT_CONFIG, EXIT_INTERNAL, EXIT_SUCCESS
from bhava_library.domain.errors import BhavaError
from bhava_library.infrastructure.database import Database
from bhava_library.infrastructure.filesystem import ensure_dirs
from bhava_library.logging import setup_logging
from bhava_library.services import backup as backup_svc
from bhava_library.services import copyright as copyright_svc
from bhava_library.services import deduplicate as dedupe_svc
from bhava_library.services import doctor as doctor_svc
from bhava_library.services import download as download_svc
from bhava_library.services import estimate as estimate_svc
from bhava_library.services import index as index_svc
from bhava_library.services import report as report_svc
from bhava_library.services import resolve as resolve_svc
from bhava_library.services import scan as scan_svc
from bhava_library.services import verify as verify_svc

app = typer.Typer(
    name="bhava-lib",
    help="Bhāva Library — private local-first educational reference archive",
    no_args_is_help=True,
    add_completion=False,
)
copyright_app = typer.Typer(help="Original Bhāva/Dauji publication records only")
app.add_typer(copyright_app, name="copyright")
console = Console(force_terminal=False, legacy_windows=False)


def _settings() -> Settings:
    settings = load_settings()
    setup_logging(settings.logs_dir)
    ensure_dirs(
        settings.data_dir,
        settings.data_dir / "catalog",
        settings.staging_dir,
        settings.quarantine_dir,
        settings.snapshots_dir,
        settings.originals_dir,
        settings.reports_dir,
        settings.logs_dir,
    )
    return settings


@app.command()
def version() -> None:
    """Print package version."""
    console.print(__version__)


@app.command()
def doctor() -> None:
    """Report environment health."""
    settings = _settings()
    report = doctor_svc.run_doctor(settings)
    table = Table(title="Bhava Library Doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    for check in report.checks:
        table.add_row(check["name"], check["status"], check["detail"])
    console.print(table)
    raise typer.Exit(EXIT_SUCCESS if report.ok else EXIT_CONFIG)


@app.command()
def scan() -> None:
    """Metadata-only source scan (no resource body downloads)."""
    settings = _settings()
    summary = scan_svc.run_scan(settings)
    console.print(summary.model_dump())
    raise typer.Exit(EXIT_SUCCESS)


@app.command()
def resolve(limit: int | None = typer.Option(None, help="Max resources to resolve")) -> None:
    """Resolve resource links to downloadable URLs."""
    settings = _settings()
    counts = resolve_svc.run_resolve(settings, limit=limit)
    console.print(counts)
    raise typer.Exit(EXIT_SUCCESS)


@app.command()
def estimate(
    profile: str = typer.Option("core", help="Acquisition profile"),
    no_probe: bool = typer.Option(False, help="Skip HEAD/range probes"),
) -> None:
    """Estimate sizes and plan safe batches."""
    settings = _settings()
    summary = estimate_svc.run_estimate(settings, profile=profile, probe=not no_probe)
    console.print(summary.model_dump())
    raise typer.Exit(EXIT_SUCCESS)


@app.command()
def acquire(profile: str = typer.Option("core", help="Acquisition profile")) -> None:
    """Download the current safe batch for the profile."""
    settings = _settings()
    # Ensure scan/resolve/estimate pipeline for core if queue empty
    db = Database(settings.catalog_db)
    db.migrate()
    pending = db.execute(
        "SELECT COUNT(*) AS n FROM download_jobs WHERE state IN ('pending','paused','retryable','active')"
    )
    if not pending or pending[0]["n"] == 0:
        console.print("No queued jobs; running scan → resolve → estimate first")
        scan_svc.run_scan(settings)
        resolve_svc.run_resolve(settings)
        estimate_svc.run_estimate(settings, profile=profile)
    code = download_svc.run_acquire(settings, profile=profile)
    raise typer.Exit(code)


@app.command()
def resume() -> None:
    """Resume pending/partial downloads."""
    settings = _settings()
    code = download_svc.run_resume(settings)
    raise typer.Exit(code)


@app.command()
def status() -> None:
    """Show catalog and job status."""
    settings = _settings()
    db = Database(settings.catalog_db)
    db.migrate()
    rows = db.execute(
        """
        SELECT status, COUNT(*) AS n FROM resources
        WHERE removed_at IS NULL GROUP BY status ORDER BY n DESC
        """
    )
    console.print({r["status"]: r["n"] for r in rows})
    jobs = db.execute("SELECT state, COUNT(*) AS n FROM download_jobs GROUP BY state")
    console.print({"jobs": {r["state"]: r["n"] for r in jobs}})
    raise typer.Exit(EXIT_SUCCESS)


@app.command()
def verify(full: bool = typer.Option(False, "--full", help="Re-verify all local files")) -> None:
    """Verify downloaded files."""
    settings = _settings()
    counts = verify_svc.run_verify(settings, full=full)
    dedupe_svc.run_deduplicate(settings)
    console.print(counts)
    raise typer.Exit(EXIT_SUCCESS)


@app.command("index")
def index_cmd() -> None:
    """Build/rebuild SQLite FTS5 index."""
    settings = _settings()
    result = index_svc.run_index(settings)
    console.print(result)
    raise typer.Exit(EXIT_SUCCESS)


@app.command()
def report() -> None:
    """Generate final Markdown/JSON reports."""
    settings = _settings()
    path = report_svc.run_report(settings)
    console.print(f"Wrote {path}")
    raise typer.Exit(EXIT_SUCCESS)


@app.command()
def backup(
    target: str | None = typer.Option(None, help="Backup destination root"),
) -> None:
    """Create a timestamped non-destructive backup."""
    settings = _settings()
    result = backup_svc.run_backup(settings, target=target)
    console.print(result)
    raise typer.Exit(EXIT_SUCCESS)


@app.command("restore-check")
def restore_check(
    target: str = typer.Option(..., help="Backup folder or parent directory"),
) -> None:
    """Verify a backup via sampled hash checks."""
    settings = _settings()
    result = backup_svc.run_restore_check(settings, target=target)
    console.print(result)
    raise typer.Exit(EXIT_SUCCESS)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Optional local-only search UI (requires ui extras)."""
    try:
        import uvicorn

        from bhava_library.ui.app import create_app
    except Exception as exc:  # noqa: BLE001
        console.print(f"UI unavailable: {exc}. Install with: uv sync --extra ui")
        raise typer.Exit(EXIT_CONFIG) from exc
    settings = _settings()
    uvicorn.run(create_app(settings), host=host, port=port, log_level="info")


@copyright_app.command("new-work")
def copyright_new_work(
    title: str = typer.Option(..., help="Work title"),
    work_type: str = typer.Option("story", help="Work type"),
    work_id: str | None = typer.Option(None, help="Optional work id"),
) -> None:
    settings = _settings()
    path = copyright_svc.new_work(settings, title=title, work_type=work_type, work_id=work_id)
    console.print(f"Created {path}")


@copyright_app.command("notice")
def copyright_notice(
    work_id: str = typer.Option(..., help="Work id"),
    kind: str = typer.Option("book", help="book|footer|audio|draft|preview"),
) -> None:
    settings = _settings()
    path = copyright_svc.generate_notice(settings, work_id, kind=kind)
    console.print(path.read_text(encoding="utf-8"))
    console.print(f"Wrote {path}")


@copyright_app.command("freeze")
def copyright_freeze(
    work_id: str = typer.Option(...),
    file: Path = typer.Option(..., exists=True, dir_okay=False),
) -> None:
    settings = _settings()
    evidence = copyright_svc.freeze_work(settings, work_id, file)
    console.print(evidence)


def main() -> None:
    try:
        app()
    except BhavaError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(exc.exit_code) from exc
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Internal error: {exc}[/red]")
        raise SystemExit(EXIT_INTERNAL) from exc


if __name__ == "__main__":
    main()
