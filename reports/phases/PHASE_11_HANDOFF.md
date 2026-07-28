# Phase 11 — Handoff (Curation v1)

**Branch:** `feature/library-curation-v1`  
**Date:** 2026-07-28  
**Baseline snapshot:** `pre-curation-20260728T230113Z`

## Catalog counts (post-migration)

| Metric | Count |
|--------|------:|
| Resources | 2,470 |
| Local files (originals catalog) | 2,444 |
| Taxonomy terms (seeded) | 178 |
| Schema versions applied | 1, 2 |

Curation tables (`resource_classifications`, `resource_names`, etc.) are populated by running the curate pipeline — not pre-filled in this handoff commit.

## Original integrity

```
compare_original_integrity.py → ok: true
expected_count: 2444
hash_mismatches: 0
```

Originals under `data/originals/**` were not modified during implementation.

## Validation run

| Check | Result |
|-------|--------|
| `uv run ruff check src tests scripts` | pass |
| `uv run ruff format src tests scripts` | pass |
| `uv run mypy src` | pass |
| `uv run pytest -q` | 73 passed |
| `python scripts/compare_original_integrity.py` | ok |

## New commands

```powershell
.\bhava.ps1 curate snapshot
.\bhava.ps1 curate enrich
.\bhava.ps1 curate classify
.\bhava.ps1 curate build-views
.\bhava.ps1 curate review-report
.\bhava.ps1 curate integrity
.\bhava.ps1 curate sunday-school
.\bhava.ps1 curate candidates
.\bhava.ps1 archive-pack --dry-run
.\bhava.ps1 archive-restore-check --pack <dir>
.\bhava.ps1 serve   # 127.0.0.1:8765, /docs enabled
```

## Recommended owner pipeline

1. `.\bhava.ps1 curate enrich` — sidecars to `data/derived/`
2. `.\bhava.ps1 curate classify`
3. `.\bhava.ps1 curate sunday-school`
4. `.\bhava.ps1 curate build-views`
5. `.\bhava.ps1 curate review-report`
6. `.\bhava.ps1 curate candidates`
7. `.\bhava.ps1 curate integrity`

Full archive (13GB+): `.\bhava.ps1 archive-pack --dest <private-backup-path>` — run locally when ready; agent session used fixture-only restore test.

## Copyright identity

Active: **Svarna Gauranga Das** / svarnagaurangdas@gmail.com / Dauji Publication

## Modules added

`src/bhava_library/curation/` — names, enrich, classify, sunday_school, views, review, provenance, integrity, archive_pack, ai_enrich, snapshot

## Not in scope

- Public website / store
- Uploading archive volumes to public GitHub (refused by helper)
- Hard dependency on pypdf/mutagen (optional, degraded)
