# Phase 08 — Integrity and Archive Pack

## Delivered

- `curation/integrity.py` — wraps `compare_original_integrity` + DB `PRAGMA integrity_check`
- `curation/archive_pack.py` — split-volume pack, `ARCHIVE_MANIFEST.json`, restore-check, public GitHub refusal
- `curation/ai_enrich.py` — no-op without API key (optional proposals only)
- `curation/snapshot.py` — curate snapshot wrapper

## Tests

- `test_archive_volume_and_public_refuse.py` — fixture pack + restore-check
- `test_no_original_mutation.py`

## Gate

- `python scripts/compare_original_integrity.py` — ok (2444 files baseline)

## Owner note

Full archive pack: `.\bhava.ps1 archive-pack --dest <private-path>` (not run in agent session; use `--dry-run` or `--limit` for planning).
