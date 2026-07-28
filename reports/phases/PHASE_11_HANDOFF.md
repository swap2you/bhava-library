# Phase 11 — Handoff (Curation v1)

**Branch:** `feature/library-curation-v1`  
**HEAD (at handoff update):** run `git rev-parse HEAD`  
**Baseline main:** `17ac6d1ad7fddb3dfe8e47645e43d86476652614`  
**Pre-curation snapshot:** `pre-curation-20260728T230113Z`

## Pipeline results (live catalog)

| Metric | Count |
|--------|------:|
| Resources | 2,470 |
| Local files / originals intact | 2,444 |
| Taxonomy terms seeded | 178 |
| Technical metadata rows | 2,444 |
| Display names | 2,470 |
| Classifications (labels) | 19,817 |
| Evidence rows | 19,817 |
| Educational profiles | 2,470 |
| Program mappings | 2,470 |
| Review-queue rows (`needs_review`) | 13,143 |
| Auto-accepted classification labels | 6,674 |
| Logical view files | 184 |
| Production candidates | 172 |
| Source dossiers | 172 |
| Independent-creation records | 172 |
| Candidate export files | 345 |

### Classification labels by dimension

| Dimension | Labels |
|-----------|-------:|
| audience | 2,470 |
| content-form | 2,470 |
| language | 2,470 |
| production-opportunity | 2,470 |
| program-use | 2,470 |
| reference-boundary | 2,470 |
| scripture | 2,470 |
| topic | 2,470 |
| festival | 57 |

### Content-form (top)

unknown 1819 · audio-story 450 · worksheet 150 · coloring-page 21 · quiz 16 · kirtan 6 · word-search 5 · crossword/comic/archive-bundle 1 each

### Sunday-school program collections

| Collection | Count |
|------------|------:|
| general-reference | 1,831 |
| audio-stories | 450 |
| printables-worksheets | 150 |
| printables-coloring | 21 |
| assessments | 16 |
| story-comics | 1 |
| sunday-school-core | 1 |

## Original integrity

```
compare_original_integrity.py → ok: true
expected_count: 2444
hash_mismatches: 0 / size_mismatches: 0 / missing_on_disk: 0
```

`data/originals/**` was not modified.

## Archive pack

- Implemented: `archive-pack` (split volumes, SHA-256 manifest, `--dry-run`, `--limit`)
- Restore: `archive-restore-check --pack <dir>|--manifest <path> --full`
- Smoke pack (limit 5): 2 volumes, restore `ok: true`
- **Full 13 GiB pack not auto-uploaded**
- Public GitHub upload helper refuses `BHAVA_GITHUB_VISIBILITY=public`

### Private-repository requirements (before any cloud archive upload)

1. Create a **private** GitHub repository (separate from the public code repo), e.g. `bhava-library-archive`.
2. Confirm visibility is private (`gh repo view --json isPrivate`).
3. Use release assets (not Git commits / not LFS by default).
4. Require explicit owner approval; never store credentials in the repo.
5. Run full pack to an external path first:
   `.\bhava.ps1 archive-pack --dest <EXTERNAL_OR_PRIVATE_PATH> --volume-size-mib 1900`
6. Validate: `.\bhava.ps1 archive-restore-check --pack <pack-dir> --full`

## Validation

| Check | Result |
|-------|--------|
| ruff / mypy | pass |
| pytest | 73 passed |
| original integrity | ok |
| archive smoke restore | ok |

## Owner next actions

1. Review `data/exports/classification_review_queue.csv` (13k low-confidence labels).
2. Provide external durable backup path (still pending from acquisition phase).
3. Optionally run full archive-pack to private offline storage.
4. Open PR: `feature/library-curation-v1` → `main` when ready.
5. Do **not** upload archive volumes while any destination is public.

## PR / merge instructions

```powershell
git push -u origin feature/library-curation-v1
gh pr create --base main --head feature/library-curation-v1 --title "Library curation v1: taxonomy, views, provenance, archive-pack" --body "Logical curation without modifying originals. See reports/phases/PHASE_11_HANDOFF.md."
```

Merge only after CI green on the PR.
