"""Typer CLI entry point."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from bhava_library import __version__
from bhava_library.config import Settings, load_settings
from bhava_library.constants import EXIT_BACKUP_VERIFY, EXIT_CONFIG, EXIT_INTERNAL, EXIT_SUCCESS
from bhava_library.curation import (
    run_archive_pack,
    run_archive_restore_check,
    run_build_views,
    run_candidates,
    run_classify,
    run_enrich,
    run_integrity,
    run_review_report,
    run_snapshot,
    run_sunday_school,
)
from bhava_library.domain.errors import BackupVerifyError, BhavaError
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
curate_app = typer.Typer(help="Metadata curation (never modifies originals)")
app.add_typer(copyright_app, name="copyright")
app.add_typer(curate_app, name="curate")
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
    db = Database(settings.catalog_db)
    db.migrate()
    pending = db.execute(
        """
        SELECT COUNT(*) AS n
        FROM download_jobs j
        JOIN resources r ON r.resource_id = j.resource_id
        WHERE j.state IN ('pending','paused','retryable','active')
          AND (
            ? = 'all'
            OR r.profile = ?
            OR (? = 'core' AND r.profile IN ('core','unknown'))
          )
        """,
        (profile, profile, profile),
    )
    if not pending or pending[0]["n"] == 0:
        console.print(f"No queued {profile} jobs; running estimate for profile")
        if profile == "core":
            # Ensure catalog freshness only for core bootstrap
            rows = db.execute("SELECT COUNT(*) AS n FROM resources WHERE removed_at IS NULL")
            if not rows or rows[0]["n"] == 0:
                scan_svc.run_scan(settings)
                resolve_svc.run_resolve(settings)
        estimate_svc.run_estimate(settings, profile=profile)
    code = download_svc.run_acquire(settings, profile=profile)
    raise typer.Exit(code)


@app.command()
def resume(profile: str = typer.Option("core", help="Acquisition profile to resume")) -> None:
    """Resume pending/partial downloads for a profile."""
    settings = _settings()
    code = download_svc.run_resume(settings, profile=profile)
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
    full_verify: bool = typer.Option(False, "--full-verify", help="Hash-check every copied file"),
) -> None:
    """Create a timestamped non-destructive backup."""
    settings = _settings()
    try:
        result = backup_svc.run_backup(settings, target=target, full_verify=full_verify)
    except BackupVerifyError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EXIT_BACKUP_VERIFY) from exc
    console.print(result)
    code = EXIT_SUCCESS if bool(result.get("verification_ok")) else EXIT_BACKUP_VERIFY
    raise typer.Exit(code)


@app.command("restore-check")
def restore_check(
    target: str = typer.Option(..., help="Backup folder or parent directory"),
    full: bool = typer.Option(False, "--full", help="Verify every manifest entry"),
) -> None:
    """Verify a backup via sampled or full hash checks."""
    settings = _settings()
    try:
        result = backup_svc.run_restore_check(settings, target=target, full=full)
    except BackupVerifyError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EXIT_BACKUP_VERIFY) from exc
    console.print(result)
    raise typer.Exit(EXIT_SUCCESS)


@curate_app.command("snapshot")
def curate_snapshot() -> None:
    """Create a pre-curation-style originals inventory snapshot."""
    settings = _settings()
    path = run_snapshot(settings)
    console.print(f"Wrote snapshot {path}")
    raise typer.Exit(EXIT_SUCCESS)


@curate_app.command("enrich")
def curate_enrich(limit: int | None = typer.Option(None, help="Max resources")) -> None:
    """Extract technical metadata into derived sidecars."""
    settings = _settings()
    result = run_enrich(settings, limit=limit)
    console.print(result)
    raise typer.Exit(EXIT_SUCCESS)


@curate_app.command("classify")
def curate_classify(limit: int | None = typer.Option(None, help="Max resources")) -> None:
    """Apply deterministic taxonomy classification rules."""
    settings = _settings()
    result = run_classify(settings, limit=limit)
    console.print(result)
    raise typer.Exit(EXIT_SUCCESS)


@curate_app.command("build-views")
def curate_build_views() -> None:
    """Generate HTML/CSV/JSON/MD logical views under data/views/."""
    settings = _settings()
    result = run_build_views(settings)
    console.print(result)
    raise typer.Exit(EXIT_SUCCESS)


@curate_app.command("review-report")
def curate_review_report() -> None:
    """Export low-confidence classification review queue CSV."""
    settings = _settings()
    path = run_review_report(settings)
    console.print(f"Wrote {path}")
    raise typer.Exit(EXIT_SUCCESS)


@curate_app.command("integrity")
def curate_integrity() -> None:
    """Compare originals inventory to pre-curation snapshot + DB pragma."""
    settings = _settings()
    result = run_integrity(settings)
    console.print(result)
    code = EXIT_SUCCESS if result.get("ok") else EXIT_INTERNAL
    raise typer.Exit(code)


@curate_app.command("sunday-school")
def curate_sunday_school(limit: int | None = typer.Option(None, help="Max resources")) -> None:
    """Build Sunday-school educational profiles and program mappings."""
    settings = _settings()
    result = run_sunday_school(settings, limit=limit)
    console.print(result)
    raise typer.Exit(EXIT_SUCCESS)


@curate_app.command("candidates")
def curate_candidates(limit: int | None = typer.Option(None, help="Max candidates")) -> None:
    """Export Bhāva production candidate metadata (no binaries)."""
    settings = _settings()
    result = run_candidates(settings, limit=limit)
    console.print(result)
    raise typer.Exit(EXIT_SUCCESS)


@app.command("archive-pack")
def archive_pack(
    dest: str | None = typer.Option(None, help="Output directory"),
    volume_size_mib: int = typer.Option(1900, help="Max volume size in MiB"),
    dry_run: bool = typer.Option(False, help="Plan volumes without writing tar.gz"),
    limit: int | None = typer.Option(None, help="Limit files (testing)"),
) -> None:
    """Create split-volume archive of catalog, derived, views, and originals."""
    settings = _settings()
    out = Path(dest) if dest else None
    result = run_archive_pack(
        settings,
        dest=out,
        volume_size_mib=volume_size_mib,
        dry_run=dry_run,
        limit_files=limit,
    )
    console.print(result)
    raise typer.Exit(EXIT_SUCCESS)


@app.command("archive-restore-check")
def archive_restore_check(
    pack: Path = typer.Option(..., exists=True, file_okay=False, help="Archive pack dir"),
    full: bool = typer.Option(False, help="Verify every manifest entry"),
) -> None:
    """Verify archive pack volumes against ARCHIVE_MANIFEST.json."""
    result = run_archive_restore_check(pack, full=full)
    console.print(result)
    code = EXIT_SUCCESS if result.get("ok") else EXIT_BACKUP_VERIFY
    raise typer.Exit(code)


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
