"""Environment doctor checks."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from bhava_library.config import Settings
from bhava_library.constants import GIB
from bhava_library.infrastructure.database import Database
from bhava_library.infrastructure.disk_guard import compute_reserve_bytes, disk_usage
from bhava_library.infrastructure.windows_defender import defender_available


@dataclass
class DoctorReport:
    ok: bool = True
    checks: list[dict[str, str]] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str) -> None:
        self.checks.append({"name": name, "status": status, "detail": detail})
        if status == "fail":
            self.ok = False


def run_doctor(settings: Settings) -> DoctorReport:
    report = DoctorReport()
    report.add("repository", "ok", str(settings.repo_root))
    report.add("python", "ok", sys.version.split()[0])
    uv = shutil.which("uv")
    report.add("uv", "ok" if uv else "fail", uv or "uv not found on PATH")

    gitignore = settings.repo_root / ".gitignore"
    gi_text = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if "data/**" in gi_text.replace("\\", "/") or "/data/**" in gi_text:
        report.add("gitignore_data", "ok", "data/** ignored")
    else:
        report.add("gitignore_data", "fail", ".gitignore missing data/** rule")

    db = Database(settings.catalog_db)
    try:
        db.migrate()
        integrity = db.integrity_check()
        report.add(
            "database",
            "ok" if integrity == "ok" else "fail",
            f"{settings.catalog_db} integrity={integrity}",
        )
    except Exception as exc:  # noqa: BLE001
        report.add("database", "fail", str(exc))

    snap = disk_usage(settings.data_dir if settings.data_dir.exists() else settings.repo_root)
    reserve = compute_reserve_bytes(
        snap.total_bytes,
        settings.download.reserve_gib,
        settings.download.reserve_percent,
    )
    report.add(
        "disk",
        "ok" if snap.free_bytes > reserve else "fail",
        f"free={snap.free_bytes / GIB:.2f} GiB reserve={reserve / GIB:.2f} GiB",
    )
    report.add(
        "defender",
        "ok" if defender_available() else "warn",
        "available" if defender_available() else "MpCmdRun not found",
    )
    report.add(
        "tls",
        "ok" if settings.download.verify_tls else "fail",
        f"verify_tls={settings.download.verify_tls}",
    )
    report.add(
        "copyright_identity",
        "ok",
        f"{settings.copyright.owner} / {settings.copyright.contact_email}",
    )
    report.add(
        "source",
        "ok" if settings.source_iskcon.enabled else "warn",
        settings.source_iskcon.index_url,
    )
    config_local = settings.repo_root / "config" / "local.toml"
    report.add(
        "config",
        "ok",
        "local.toml present" if config_local.exists() else "using default.toml only",
    )

    # Last events
    try:
        rows = db.execute("SELECT kind, ts FROM events ORDER BY event_id DESC LIMIT 5")
        detail = "; ".join(f"{r['kind']}@{r['ts']}" for r in rows) or "none"
        report.add("recent_events", "ok", detail)
    except Exception:  # noqa: BLE001
        report.add("recent_events", "warn", "no events yet")

    Path(settings.logs_dir).mkdir(parents=True, exist_ok=True)
    return report
