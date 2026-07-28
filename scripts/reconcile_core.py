"""Reconcile remaining core download jobs and classify outcomes."""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "catalog" / "bhava-library.sqlite3"
OUT_DIR = ROOT / "reports" / "generated"
UA = "BhavaLibrary/1.0 (+mailto:svarnagaurangdas@gmail.com)"

CLASSIFICATIONS = (
    "completed",
    "source-empty",
    "source-broken",
    "landing-page-unresolved",
    "access-restricted",
    "retryable-transient",
    "terminal-manual-review",
)


def classify_row(
    *,
    state: str,
    error_code: str | None,
    error_message: str | None,
    http_status: int | None,
    content_length: int | None,
    content_type: str | None,
    resolved_url: str | None,
    original_url: str | None,
    bytes_downloaded: int,
    expected_bytes: int | None,
) -> tuple[str, str]:
    url = resolved_url or original_url or ""
    ext = Path(urlparse(url).path).suffix.lower()
    msg = (error_message or "").lower()
    code = (error_code or "").upper()
    ctype = (content_type or "").lower()

    if state == "complete" and bytes_downloaded > 0:
        return "completed", "Job complete with nonzero payload"
    if code == "EMPTY_REMOTE" or (http_status == 200 and content_length == 0):
        return "source-empty", "Remote returns empty body / Content-Length 0"
    if http_status in {404, 410} or code in {"HTTP_404", "HTTP_410"}:
        return "source-broken", f"HTTP {http_status or code}"
    if http_status in {401, 403} or "access restricted" in msg or "captcha" in msg:
        return "access-restricted", "Authentication/CAPTCHA/forbidden"
    if "text/html" in ctype and ext in {".pdf", ".doc", ".docx", ".rtf", ".zip", ".epub"}:
        return "landing-page-unresolved", "HTML returned for document URL"
    if not ext or ext not in {
        ".pdf",
        ".doc",
        ".docx",
        ".rtf",
        ".txt",
        ".epub",
        ".zip",
        ".rar",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".csv",
        ".json",
        ".xml",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".mp3",
        ".wav",
        ".m4a",
    }:
        if "text/html" in ctype or (resolved_url or "").rstrip("/").endswith(
            tuple(["media_library", "zip", "doc", "pdf"])
        ):
            if http_status and http_status < 400 and "text/html" in ctype:
                return "landing-page-unresolved", "Landing page without direct file"
    if code in {"LENGTH_MISMATCH"} and http_status and 500 <= http_status < 600:
        return "retryable-transient", "Server error with length mismatch"
    if http_status and 500 <= http_status < 600:
        return "retryable-transient", f"HTTP {http_status}"
    if http_status == 429 or "rate limited" in msg:
        return "retryable-transient", "Rate limited"
    if code in {"LENGTH_MISMATCH", "EMPTY_BODY"} and (expected_bytes or 0) > 0:
        return "terminal-manual-review", "Persistent length/empty mismatch"
    if state in {"retryable", "pending", "active", "paused"}:
        # Cap: if many attempts, escalate
        return "terminal-manual-review", "Unresolved after acquisition attempts"
    return "terminal-manual-review", "Needs manual review"


def probe(url: str) -> dict[str, object]:
    if not url or url.startswith("urn:"):
        return {"http_status": None, "content_length": None, "content_type": None, "final_url": url}
    try:
        with httpx.Client(
            headers={"User-Agent": UA},
            follow_redirects=True,
            timeout=30.0,
            verify=True,
        ) as client:
            try:
                head = client.head(url)
                cl = head.headers.get("content-length")
                return {
                    "http_status": head.status_code,
                    "content_length": int(cl) if cl and cl.isdigit() else None,
                    "content_type": (head.headers.get("content-type") or "").split(";")[0],
                    "final_url": str(head.url),
                }
            except Exception:
                get = client.get(url, headers={"Range": "bytes=0-0"})
                cr = get.headers.get("content-range", "")
                total = None
                if "/" in cr and cr.rsplit("/", 1)[-1].isdigit():
                    total = int(cr.rsplit("/", 1)[-1])
                return {
                    "http_status": get.status_code,
                    "content_length": total,
                    "content_type": (get.headers.get("content-type") or "").split(";")[0],
                    "final_url": str(get.url),
                }
    except Exception as exc:  # noqa: BLE001
        return {
            "http_status": None,
            "content_length": None,
            "content_type": None,
            "final_url": url,
            "probe_error": str(exc)[:200],
        }


def apply_terminal(conn: sqlite3.Connection, resource_id: str, classification: str) -> None:
    if classification in {"completed"}:
        return
    if classification == "retryable-transient":
        conn.execute(
            "UPDATE download_jobs SET state='retryable', updated_at=? WHERE resource_id=?",
            (datetime.now(UTC).isoformat(), resource_id),
        )
        return
    # All other classes become terminal
    conn.execute(
        """
        UPDATE download_jobs
        SET state='terminal_failure', last_error_code=?, updated_at=?
        WHERE resource_id=?
        """,
        (classification.upper().replace("-", "_"), datetime.now(UTC).isoformat(), resource_id),
    )
    conn.execute(
        "UPDATE resources SET status='failed_terminal' WHERE resource_id=?",
        (resource_id,),
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    # Jobs of interest: retryable/pending/active/paused + completed-with-zero + quarantined
    rows = list(
        conn.execute(
            """
            SELECT j.*, r.title_original, r.original_url, r.resolved_url, r.profile, r.status AS resource_status
            FROM download_jobs j
            JOIN resources r ON r.resource_id = j.resource_id
            WHERE j.state IN ('retryable','pending','active','paused','terminal_failure')
               OR r.status IN ('quarantined','failed_terminal','downloading')
               OR (j.state='complete' AND COALESCE(j.bytes_downloaded,0)=0)
            ORDER BY j.job_id
            """
        )
    )

    report_rows: list[dict[str, object]] = []
    for row in rows:
        url = row["resolved_url"] or row["original_url"]
        probed = probe(url)
        classification, action = classify_row(
            state=row["state"],
            error_code=row["last_error_code"],
            error_message=row["last_error_message"],
            http_status=probed.get("http_status")
            if isinstance(probed.get("http_status"), int)
            else None,
            content_length=probed.get("content_length")
            if isinstance(probed.get("content_length"), int)
            else None,
            content_type=str(probed.get("content_type") or ""),
            resolved_url=row["resolved_url"],
            original_url=row["original_url"],
            bytes_downloaded=int(row["bytes_downloaded"] or 0),
            expected_bytes=row["expected_bytes"],
        )
        # If probe shows real content and job is retryable, keep transient
        if (
            classification == "terminal-manual-review"
            and isinstance(probed.get("content_length"), int)
            and int(probed["content_length"]) > 0
            and "text/html" not in str(probed.get("content_type") or "").lower()
            and row["state"] in {"retryable", "pending", "paused"}
        ):
            classification = "retryable-transient"
            action = "Remote appears downloadable; retry once more"

        apply_terminal(conn, row["resource_id"], classification)
        report_rows.append(
            {
                "resource_id": row["resource_id"],
                "title": row["title_original"],
                "original_url": row["original_url"],
                "resolved_url": row["resolved_url"],
                "http_status": probed.get("http_status"),
                "attempt_count": row["attempt_count"],
                "current_bytes": row["bytes_downloaded"],
                "expected_bytes": row["expected_bytes"] or probed.get("content_length"),
                "error_code": row["last_error_code"],
                "error_message": row["last_error_message"],
                "content_type": probed.get("content_type"),
                "final_classification": classification,
                "recommended_action": action,
            }
        )
    conn.commit()

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    csv_path = OUT_DIR / f"core-reconciliation-{stamp}.csv"
    md_path = OUT_DIR / f"core-reconciliation-{stamp}.md"
    json_path = OUT_DIR / f"core-reconciliation-{stamp}.json"

    fields = [
        "resource_id",
        "title",
        "original_url",
        "resolved_url",
        "http_status",
        "attempt_count",
        "current_bytes",
        "expected_bytes",
        "error_code",
        "error_message",
        "final_classification",
        "recommended_action",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for item in report_rows:
            writer.writerow(item)

    counts: dict[str, int] = {c: 0 for c in CLASSIFICATIONS}
    for item in report_rows:
        counts[str(item["final_classification"])] = (
            counts.get(str(item["final_classification"]), 0) + 1
        )

    # Extra inspections
    quarantine = list(
        conn.execute(
            "SELECT resource_id, relative_path, size_bytes, detected_type, quarantine_reason, sha256 FROM local_files WHERE quarantine_reason IS NOT NULL"
        )
    )
    unknown_files = list((ROOT / "data" / "originals" / "iskcon-education" / "unknown").rglob("*"))
    unknown_files = [p for p in unknown_files if p.is_file()]
    htmlish = list(
        conn.execute(
            "SELECT resource_id, relative_path, size_bytes, detected_type FROM local_files WHERE detected_type LIKE '%html%' OR relative_path LIKE '%.bin'"
        )
    )
    zero_byte = list(
        conn.execute(
            "SELECT resource_id, relative_path, size_bytes FROM local_files WHERE size_bytes=0"
        )
    )
    mismatches = list(
        conn.execute(
            """
            SELECT resource_id, relative_path, detected_type
            FROM local_files
            WHERE quarantine_reason IN ('signature_mismatch','byte_mismatch')
            """
        )
    )

    md = [
        f"# Core reconciliation — {stamp}",
        "",
        f"Rows classified: **{len(report_rows)}**",
        "",
        "## Classification counts",
        "",
    ]
    for key, value in counts.items():
        md.append(f"- `{key}`: {value}")
    md.extend(
        [
            "",
            "## Quarantine",
            "",
            f"Count: {len(quarantine)}",
        ]
    )
    for q in quarantine:
        md.append(
            f"- {q['resource_id']}: {q['quarantine_reason']} ({q['detected_type']}, {q['size_bytes']} bytes) `{q['relative_path']}`"
        )
    md.extend(["", "## Unknown directory files", "", f"Count: {len(unknown_files)}"])
    for p in unknown_files[:50]:
        md.append(f"- `{p.relative_to(ROOT)}` ({p.stat().st_size} bytes)")
    md.extend(["", "## HTML / .bin detections", "", f"Count: {len(htmlish)}"])
    for h in htmlish[:50]:
        md.append(f"- {h['resource_id']}: {h['detected_type']} `{h['relative_path']}`")
    md.extend(["", "## Zero-byte local files", "", f"Count: {len(zero_byte)}"])
    md.extend(["", "## Signature/byte mismatches", "", f"Count: {len(mismatches)}"])
    md.extend(
        [
            "",
            "## Previous backup skipped paths",
            "",
            "- `.../BL-IE-0E1D7E886979_Bhakta20Burfi20Feeds20the20Bull20-20fingerprint20painting20book20by20NC20gurukula20student_0.pdf` (long path)",
            "- `.../BL-IE-1E204BCBFA67_199620curriculum20correspondence20-20curriculum20topics20-20songs20by20grade20level20-20etiquette.pdf` (long path / empty source)",
            "",
            f"CSV: `{csv_path.relative_to(ROOT)}`",
        ]
    )
    md_path.write_text("\n".join(md), encoding="utf-8")
    # Also copy stable names into reports/ (tracked-friendly summaries without generated/)
    summary = {
        "stamp": stamp,
        "counts": counts,
        "rows": report_rows,
        "quarantine": [dict(q) for q in quarantine],
        "unknown_file_count": len(unknown_files),
        "htmlish_count": len(htmlish),
        "zero_byte_count": len(zero_byte),
        "mismatch_count": len(mismatches),
    }
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    tracked = ROOT / "reports" / "CORE_RECONCILIATION.md"
    tracked.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({"csv": str(csv_path), "md": str(md_path), "counts": counts}, indent=2))


if __name__ == "__main__":
    main()
