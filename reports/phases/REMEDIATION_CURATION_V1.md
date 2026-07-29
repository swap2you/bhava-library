# Curation v1 Remediation Report

Branch: `feature/library-curation-v1`  
Baseline commit: `62592854ecb5cc7f6026460054fd637aeebd016c`  
Date: 2026-07-29

## 1. Baseline reconciliation

| Check | Result |
|-------|--------|
| Local HEAD | `62592854ecb5cc7f6026460054fd637aeebd016c` |
| Remote branch match | Confirmed before remediation |
| Originals integrity | 2444/2444 match pre-curation snapshot `pre-curation-20260728T230113Z` before and after |

## 2. Classify idempotency

| Metric | Before | After (stable double-run) |
|--------|--------|---------------------------|
| classifications | 19817 | 20730 |
| evidence | 19817 | 20730 |
| Double-run labels | — | `20730` == `20730` |

Migration 003 adds unique evidence index. Reclassify deletes prior rows per resource before rewrite so stale `rules-v1.0` labels cannot coexist with `rules-v2.0`.

## 3. Program mapping idempotency

| Metric | Before | After (stable double-run) |
|--------|--------|---------------------------|
| program_mappings | 2470 (all `sunday-school`) | 4173 |
| Double-run mappings | — | `4173` == `4173` |

Distinct configured programs:

- sunday-school: 503
- bal-gopal: 169
- damodara: 423
- gopinath: 730
- gurukula: 270
- homeschool: 823
- family-bhakti: 533
- youth: 722

Config source: `config/programs.toml` (`programs-v1`).

## 4. Classification rule fixes

- coloring-book evaluated before coloring-page; page rule no longer matches `book`
- multi-label topic / person / festival / program-use
- language fallback is honest `unknown` (catalog `language` is null for acquired rows)
- `media_format` + technical metadata consumed
- content-form unknown: **1819 → 922**
- language english default: **2470 → 0**; language unknown: **0 → 2470**

## 5. Program configuration

Real TOML profiles for Sunday School, Bal Gopal, Damodara, Gopinath, Gurukula, homeschool, family bhakti, and youth. Mapper uses explicit `program-use` first, then form/age suitability fallback with `match_reason` recorded in assumptions JSON.

## 6. Display filenames

Format uses known dimensions only:

`[Clean Title] — [Content Form] — [Age Band] — [Language] — [Resource ID].[ext]`

Unknown language is omitted. Originals untouched. Live conflict count: **0**.

## 7. Technical enrichment

Optional `metadata` extra (`pypdf`, `mutagen`, Pillow, Office parsers). Live enrich:

| Status | Count |
|--------|------:|
| full | 1722 |
| fallback_only | 711 |
| skipped_quarantine | 3 |
| errors | 8 |
| enriched | 2444 |

## 8. Candidate / dossier semantics

| Status | Count | Meaning |
|--------|------:|---------|
| `candidate_proposal` | 151 | metadata-only proposal shells |
| `proposed` | 21 | legacy rows retained |
| `dossier_shell` | 151 | pending human dossier shells |
| `pending` | 21 | legacy dossier rows |

No fabricated reference binaries. Candidate export binary scan: **clean**.

## 9. Archive pack correctness

Packer rewritten with canonical manifest self-hash, exclusive compressed volume limit, oversize rejection, staging/cleanup, and non-tautological restore checks. Full ~13 GiB pack **not** executed (tests gate first). Public GitHub upload remains refused.

## 10. HTML escaping

Generated views escape user-controlled titles/terms via `html.escape`. Covered by unit tests.

## 11. Faceted localhost UI

Search facets for content-form, audience, language, program, review state, quarantine, duplicates. Resource detail page at `/resource/{id}`.

## 12. Live local UAT

`scripts/uat_curation.py` read-only sampling: **ok**. Audio metadata present. Quarantine representation: 3 zip-with-executable. Terminal jobs complete: 2437. Originals unchanged.

## 13. Validation gates (local)

| Gate | Result |
|------|--------|
| ruff check | pass |
| ruff format | pass |
| mypy | pass |
| pytest | 89 passed |
| bandit | exit 0 |
| pip-audit | no known vulnerabilities |
| compare_original_integrity | ok |

## 14. Remaining human review

- Language remains `unknown` until catalog language evidence exists
- 922 content-form unknowns need human/AI-assisted review
- 151 candidate proposals require doctrinal/product/rights review before any original-work creation
- No approved independent-creation records were fabricated
