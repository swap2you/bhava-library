# Bhāva Library — Final Implementation and Acquisition Report

Prepared: 2026-07-28  
Repository: `C:\Development\Workspace\DevotionalRepo\bhava-library`  
Branch: `main` (local)

## 1. Repository structure created

Implemented per `02_ARCHITECTURE/REPOSITORY_BLUEPRINT.md`:

- `.cursor/rules/` (copied from package)
- `config/`, `src/bhava_library/`, `tests/`, `docs/`, `manifests/`, `copyright/`, `exports/`, `data/` (gitignored), `bhava.ps1`, `pyproject.toml`, `uv.lock`

## 2. Files added or changed

New implementation at repository root (package left unmodified). Key surfaces:

- CLI: `bhava.ps1` → `uv run bhava-lib …`
- Source adapter: `IskconEducationSourceAdapter`
- Services: doctor, scan, resolve, estimate, download, verify, dedupe, index, report, backup, copyright
- Optional local UI scaffold under `src/bhava_library/ui/`

## 3. Obsolete identity values found and corrected

In **new** implementation only (package retained as specification):

| Obsolete | Corrected |
|---|---|
| Swarna Gauranga Das | **Svarna Gauranga Das** |
| SwarnaGaurangaDas@gmail.com | **svarnagaurangdas@gmail.com** |

Applied in `config/default.toml`, copyright templates/schemas, notices, user-agent, docs, and tests.

## 4. Commands implemented

```text
bootstrap doctor scan resolve estimate acquire resume status
verify index report backup restore-check serve
copyright new-work|notice|freeze
```

## 5. Tests executed

```text
uv run ruff check src tests          → All checks passed
uv run ruff format --check src tests → formatted
uv run mypy src                      → Success: no issues found in 36 source files
uv run pytest (unit/safety/integration) → 21 passed
uv run bandit -r src                 → 0 medium/high (Defender subprocess nosec’d)
uv run pip-audit                     → No known vulnerabilities found
```

## 6. Live resource rows discovered

**2470** media-library rows  
Formats: Documents **1681**, Audio **789**  
Video: **0**

## 7. Link resolution

| Outcome | Count |
|---|---|
| Resolved | 2462 |
| Unresolved (initial resolve) | 8 |
| Inaccessible / broken | 0 |

Most resolutions used `direct_extension`. A few landing pages used `download_button` / HTML inspection.

## 8. Estimated core download size

| Metric | Value |
|---|---|
| Core candidates | 1681 |
| Known bytes | 4,279,306,764 (~3.99 GiB) |
| Unknown size count | 0 |
| Batch cap | 20 GiB |
| First batch | 1681 files / ~3.99 GiB (single batch) |
| Safe to acquire | **Yes** |

## 9. Disk space before and after

| | Free |
|---|---|
| Before acquisition (doctor) | ~173.56 GiB |
| After core acquisition + local backup | ~162.47 GiB |
| Reserve policy | max(50 GiB, 15% volume) ≈ 142–153 GiB |
| Reserve maintained | **Yes** |

## 10. Files and bytes downloaded

| Metric | Value |
|---|---|
| Jobs complete | 1657 |
| Local files recorded | 1657 |
| Verified / indexed | 1654 |
| Bytes on disk (non-quarantine) | 4,245,941,730 (~3.95 GiB) |
| Jobs still retryable | 24 |
| Quarantined | 3 |

## 11. Verification, quarantine, duplicates

- SHA-256 computed; read-only marking applied where verified
- Windows Defender CLI present but often returns inconclusive `exit=2` (hr=0x80004005); treated as inconclusive, not auto-quarantine unless threat markers appear
- Quarantined: **3**
- Duplicate hash groups linked (non-destructive): **44**

## 12. Audio and video deferred

| Profile | Count | Notes |
|---|---|---|
| Audio | **789** | Deferred; not downloaded |
| Video | **0** | None in current catalog |

Exact next command for audio later: `.\bhava.ps1 estimate --profile audio`

## 13. Backup status

Backup completed successfully:

- Target: `data\backups\bhava-library-backup-20260728T182655Z`
- Files: **1666** (skipped 2 long-path edge cases)
- Bytes: **4,257,966,505**
- Sample restore check: **ok** (`.\bhava.ps1 restore-check --target "data\backups"` → 25 hashes verified)

Prefer an external volume for durable copies; a backup under `data\backups` doubles local usage.

## 14. Unresolved risks

1. **24 retryable core jobs** remain (network/transient or awkward landing-page URLs).
2. Some remote PDFs return **HTTP 200 with Content-Length 0** (empty on source) — marked terminal when encountered.
3. A few “resolved” landing pages may store HTML wrappers rather than binary payloads — inspect `data/originals/.../unknown/`.
4. Defender MpCmdRun inconclusive on this host — do not treat as clean attestation.
5. Acquisition runs **serially per host** (httpx streaming is not thread-safe); polite but slower.
6. Package HTML snapshot `_probe.html` under `data/` is local-only / gitignored.

## 15. Exact next command for the owner

Retry remaining core failures, then optionally start audio later:

```powershell
.\bhava.ps1 resume
.\bhava.ps1 status
.\bhava.ps1 report
```

Independent review:

```powershell
# Use prompts under docs\validation\review-prompts\
```

## Identity (original works only)

- Owner: Svarna Gauranga Das  
- Publisher: Dauji Publication  
- Project: Bhāva  
- Location: Harrisburg, Pennsylvania, USA  
- Email: svarnagaurangdas@gmail.com  
- Phone: none  

Never applied to third-party originals under `data/originals/`.
