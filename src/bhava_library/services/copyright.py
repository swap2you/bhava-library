"""Copyright and publication ledger for original Bhāva/Dauji works only."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from bhava_library.config import (
    COPYRIGHT_EMAIL,
    COPYRIGHT_LOCATION,
    COPYRIGHT_OWNER,
    COPYRIGHT_PROJECT,
    COPYRIGHT_PUBLISHER,
    Settings,
)
from bhava_library.domain.errors import ConfigError
from bhava_library.infrastructure.database import Database, utc_now
from bhava_library.infrastructure.filesystem import ensure_dirs
from bhava_library.infrastructure.hashing import sha256_file


def _year(value: str | None = None) -> str:
    if value:
        return value[:4]
    return str(datetime.now(UTC).year)


def book_copyright_page(*, year: str, version: str, work_id: str) -> str:
    return f"""Copyright © {year} {COPYRIGHT_OWNER}
All rights reserved.

Published by {COPYRIGHT_PUBLISHER}
A {COPYRIGHT_PROJECT} Project publication

{COPYRIGHT_LOCATION}
Contact: {COPYRIGHT_EMAIL}

First edition: {year}
Version: {version}
Work ID: {work_id}

No part of this original publication may be reproduced, distributed, transmitted,
or stored except as permitted by applicable law or by written license from the
copyright owner.

Scriptural quotations, source texts, trademarks, and third-party materials remain
the property of their respective rights holders and are credited separately.
"""


def printable_footer(*, year: str, license_type: str = "All rights reserved") -> str:
    return (
        f"© {year} {COPYRIGHT_OWNER} · {COPYRIGHT_PUBLISHER} · "
        f"{COPYRIGHT_PROJECT} Project · {license_type}"
    )


def audio_notice(*, year: str) -> str:
    return f"""Text © {year} {COPYRIGHT_OWNER}
Sound recording ℗ {year} {COPYRIGHT_OWNER}
Published by {COPYRIGHT_PUBLISHER}, a {COPYRIGHT_PROJECT} Project publication
Contact: {COPYRIGHT_EMAIL}
"""


def draft_notice(*, year: str) -> str:
    return f"DRAFT — NOT FOR DISTRIBUTION\nCopyright © {year} {COPYRIGHT_OWNER}\n"


def preview_notice(*, year: str) -> str:
    return f"PREVIEW — NOT FOR REDISTRIBUTION\nCopyright © {year} {COPYRIGHT_OWNER}\n"


def refuse_third_party_stamp(resource_id: str) -> None:
    raise ConfigError(
        f"Refusing to apply {COPYRIGHT_OWNER}/{COPYRIGHT_PUBLISHER} notice to "
        f"third-party resource {resource_id}. Reference originals remain unmodified."
    )


def new_work(
    settings: Settings,
    *,
    title: str,
    work_type: str = "story",
    work_id: str | None = None,
) -> Path:
    ensure_dirs(settings.copyright_dir / "manifests")
    year = _year()
    wid = work_id or f"BHAVA-WORK-{year}-{datetime.now(UTC).strftime('%H%M%S')}"
    manifest: dict[str, object] = {
        "work_id": wid,
        "title": title,
        "version": "0.1.0",
        "status": "draft",
        "work_type": work_type,
        "project": COPYRIGHT_PROJECT,
        "publisher": COPYRIGHT_PUBLISHER,
        "copyright_owner": COPYRIGHT_OWNER,
        "contact_email": COPYRIGHT_EMAIL,
        "location": COPYRIGHT_LOCATION,
        "created_at": utc_now(),
        "first_published_at": None,
        "publication_status": "unpublished",
        "contributors": [],
        "source_dossier": [],
        "third_party_assets": [],
        "fonts": [],
        "ai_use": [],
        "files": [],
        "notices": [],
        "reviews": {"devotional": None, "editorial": None, "rights": None, "accessibility": None},
        "registration": {
            "status": "not_started",
            "application_type": None,
            "application_number": None,
            "certificate_number": None,
        },
    }
    path = settings.copyright_dir / "manifests" / f"{wid}.yaml"
    # Prefer JSON if PyYAML not available as dependency — write YAML-compatible manually
    text = (
        "\n".join(
            [
                f"work_id: {wid}",
                f'title: "{title}"',
                'version: "0.1.0"',
                "status: draft",
                f"work_type: {work_type}",
                f'project: "{COPYRIGHT_PROJECT}"',
                f'publisher: "{COPYRIGHT_PUBLISHER}"',
                f'copyright_owner: "{COPYRIGHT_OWNER}"',
                f'contact_email: "{COPYRIGHT_EMAIL}"',
                f'location: "{COPYRIGHT_LOCATION}"',
                f'created_at: "{manifest["created_at"]}"',
                "first_published_at:",
                "publication_status: unpublished",
            ]
        )
        + "\n"
    )
    path.write_text(text, encoding="utf-8")
    # Also JSON sidecar for tooling without YAML dep
    path.with_suffix(".json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    db = Database(settings.catalog_db)
    db.migrate()
    with db.session() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO original_works(
              work_id, title, version, status, work_type, project, publisher,
              copyright_owner, contact_email, location, created_at,
              publication_status, manifest_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                wid,
                title,
                "0.1.0",
                "draft",
                work_type,
                COPYRIGHT_PROJECT,
                COPYRIGHT_PUBLISHER,
                COPYRIGHT_OWNER,
                COPYRIGHT_EMAIL,
                COPYRIGHT_LOCATION,
                utc_now(),
                "unpublished",
                str(path.relative_to(settings.repo_root)),
            ),
        )
    # Append works.csv
    csv_path = settings.copyright_dir / "works.csv"
    if not csv_path.exists():
        csv_path.write_text(
            "work_id,title,work_type,version,status,author,copyright_owner,publisher,"
            "created_at,first_published_at,publication_status,deposit_path,deposit_sha256,"
            "registration_status,application_type,application_number,certificate_number,notes\n",
            encoding="utf-8",
        )
    with csv_path.open("a", encoding="utf-8") as fh:
        fh.write(
            f"{wid},{title},{work_type},0.1.0,draft,{COPYRIGHT_OWNER},{COPYRIGHT_OWNER},"
            f"{COPYRIGHT_PUBLISHER},{manifest['created_at']},,unpublished,,,,,,,\n"
        )
    return path


def generate_notice(settings: Settings, work_id: str, kind: str = "book") -> Path:
    manifest_json = settings.copyright_dir / "manifests" / f"{work_id}.json"
    if not manifest_json.exists():
        raise ConfigError(f"Unknown work_id {work_id}")
    data = json.loads(manifest_json.read_text(encoding="utf-8"))
    year = _year(data.get("first_published_at") or data.get("created_at"))
    if kind == "book":
        text = book_copyright_page(
            year=year, version=data.get("version") or "0.1.0", work_id=work_id
        )
    elif kind == "footer":
        text = printable_footer(year=year)
    elif kind == "audio":
        text = audio_notice(year=year)
    elif kind == "draft":
        text = draft_notice(year=year)
    elif kind == "preview":
        text = preview_notice(year=year)
    else:
        raise ConfigError(f"Unknown notice kind {kind}")
    out = settings.copyright_dir / "templates" / f"{work_id}-{kind}-notice.txt"
    ensure_dirs(out.parent)
    out.write_text(text, encoding="utf-8")
    return out


def freeze_work(settings: Settings, work_id: str, file_path: Path) -> dict[str, str]:
    if not file_path.exists():
        raise ConfigError(f"File not found: {file_path}")
    digest = sha256_file(file_path)
    evidence_dir = settings.copyright_dir / "evidence" / work_id
    ensure_dirs(evidence_dir)
    evidence = {
        "work_id": work_id,
        "path": str(file_path),
        "sha256": digest,
        "frozen_at": utc_now(),
        "copyright_owner": COPYRIGHT_OWNER,
        "publisher": COPYRIGHT_PUBLISHER,
    }
    out = evidence_dir / f"freeze-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    db = Database(settings.catalog_db)
    with db.session() as conn:
        conn.execute(
            "UPDATE original_works SET deposit_sha256=?, version=version WHERE work_id=?",
            (digest, work_id),
        )
    return evidence
