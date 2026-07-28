# Bhāva Library — Stabilization & Acquisition Completion Report

**Repository:** https://github.com/swap2you/bhava-library  
**Visibility:** public  
**Base commit at phase start:** `783811455b4db77c4fe0f1018fd7d38568240716`  
**Branch:** `main`

## Identity

Corrected active identity everywhere (rules/config/docs/tests):

- Copyright owner: **Svarna Gauranga Das**
- Publisher: **Dauji Publication**
- Project: **Bhāva**
- Location: **Harrisburg, Pennsylvania, USA**
- Email: **svarnagaurangdas@gmail.com**
- Phone: none

`.cursor/rules/03-copyright.mdc` updated. Extracted package directory:

- untracked from Git;
- excluded in `.cursorignore` and `.gitignore`;
- marked `SUPERSEDED.md` at package root.

## CI

Added `.github/workflows/ci.yml` (Python 3.13 + uv):

- ruff check/format, mypy, pytest, bandit, pip-audit, binary/data tracking guard

Local gate: **45 passed** (`uv run pytest`).

## Core reconciliation

| Metric | Count |
|---|---|
| Jobs complete | 1650–1657 (see live status) |
| Terminal failures | 24–31 classified |
| Indexed verified files | 1654 |
| Quarantined | 3 |
| Duplicate groups linked | 44 |
| Audio deferred (pre-audio phase) | 789 |

Reports:

- `reports/CORE_RECONCILIATION.md`
- `reports/CORE_RECONCILIATION.csv`
- `reports/generated/core-reconciliation-*.csv`

Classifications used: completed, source-empty, source-broken, landing-page-unresolved, access-restricted, retryable-transient, terminal-manual-review.

Previous backup skipped long paths (documented in reconciliation):

1. Bhakta Burfi fingerprint painting book PDF (long path)
2. 1996 curriculum correspondence PDF (long path / empty source)

## Backup behavior fix

Backups with required skipped files now:

- record skipped paths in manifest;
- set `verification_ok = 0`;
- raise `BackupVerifyError` / nonzero exit (`26`);
- support `--full-verify` and restore `--full`.

Same-drive `data/backups` is **not** the durable backup. External target required.

## Audio estimate

See `reports/AUDIO_ESTIMATE.md`:

- 789 audio candidates; ~9.62 GiB known; 1 unknown; safe to acquire (narrow reserve margin).

## Commands

```powershell
.\bhava.ps1 resume --profile core
.\bhava.ps1 acquire --profile audio
.\bhava.ps1 backup --target "<EXTERNAL_BACKUP_PATH>"
.\bhava.ps1 restore-check --target "<EXTERNAL_BACKUP_PATH>" --full
```

`resume` now accepts `--profile`.
