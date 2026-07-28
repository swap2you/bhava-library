# Bhāva Library — Stabilization & Acquisition Completion Report

**Repository:** https://github.com/swap2you/bhava-library  
**Visibility:** public  
**Phase-start commit:** `783811455b4db77c4fe0f1018fd7d38568240716`  
**Current commit (at report authoring):** see `git rev-parse HEAD` / latest `main`  
**Branch:** `main`

## Identity

Corrected active identity everywhere (rules/config/docs/tests):

| Field | Value |
|---|---|
| Copyright owner | **Svarna Gauranga Das** |
| Publisher | **Dauji Publication** |
| Project | **Bhāva** |
| Location | **Harrisburg, Pennsylvania, USA** |
| Email | **svarnagaurangdas@gmail.com** |
| Phone | none |

Obsolete spellings (`Swarna Gauranga Das`, `SwarnaGaurangaDas@gmail.com`) are rejected by config validation and called out in `.cursor/rules/03-copyright.mdc`.

Extracted package `Bhava_Library_Cursor_Implementation_Package_v1.0/`:

- removed from Git tracking;
- excluded via `.cursorignore` and `.gitignore`;
- marked with local `SUPERSEDED.md` (historical only).

## CI

Workflow: `.github/workflows/ci.yml` (Python 3.13 + uv)

Runs: ruff check/format, mypy, pytest, bandit, pip-audit, binary/data tracking guard.

Local gate: **55 passed**.

## Core reconciliation

| Metric | Count |
|---|---|
| Core indexed | 1654 |
| Core terminal failed | 24 |
| Quarantined | 3 |
| Core local files (incl. quarantine) | 1657 |
| Jobs complete (all profiles) | 2437 |
| Jobs terminal_failure (all) | 33 |
| Duplicate file links | 78 |

Classification report (`reports/CORE_RECONCILIATION.md` / `.csv`):

| Classification | Count |
|---|---|
| completed | 3 |
| source-empty | 7 |
| terminal-manual-review | 24 |
| source-broken / landing-page-unresolved / access-restricted / retryable-transient | 0 |

Previous backup skipped long paths (now handled via `\\?\` on Windows; incomplete backups fail verification):

1. Bhakta Burfi fingerprint painting book PDF  
2. 1996 curriculum correspondence PDF  

## Audio

| Metric | Value |
|---|---|
| Candidates | 789 |
| Complete | 787 |
| Terminal | 2 (`EMPTY_REMOTE`, `HTTP_404`) |
| Audio bytes on disk | 10,325,670,104 (~9.62 GiB) |
| Exit from acquire | 10 (`EXIT_PARTIAL`) due to 2 terminals |

Estimate: `reports/AUDIO_ESTIMATE.md`. Video not downloaded.

Disk: before audio ~154.7 GiB free; after ~146.1 GiB free.

## Backup

Skipped required files → `verification_ok=0`, nonzero exit `26`, skipped paths in manifest.  
`--full-verify` / restore `--full` supported.  
Same-drive `data/backups` is **not** durable. **External target required** (not yet run).

## Tests expanded

Downloader/backup coverage includes Range resume, Range ignore, ETag restart, pause persistence, connection interrupt, 429/500/400/410, HTML-for-document, length mismatch, unknown size, disk reserve, path traversal, ZIP slip/bomb/exe/malformed, duplicates, Defender unavailable, audio/core profiles, backup skip incompleteness, long-path helper, full backup + restore verification.

## Remaining limitations

- Windows Defender MpCmdRun often inconclusive (`exit=2`) — treated as inconclusive, not clean/dirty.
- 3 ZIP archives quarantined (contain executables).
- 8 `unknown/` HTML-as-`.bin` legacy core artifacts (manual review).
- 7 historically empty remote PDFs classified `source-empty`.
- Final generated report historically labeled audio counts as “deferred”; wording updated to “Audio resources”.
- External durable backup not yet executed (awaiting path).
