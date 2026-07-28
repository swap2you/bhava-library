# Phase 03 — Display Names and Technical Enrichment

## Delivered

- `curation/names.py` — display titles, slugs, ASCII aliases (no original renames)
- `curation/enrich.py` — technical metadata with zipfile + optional pypdf/mutagen degradation
- Sidecars under `data/derived/technical/` and `data/derived/metadata/` only

## Tests

- Covered in `test_names_and_classify.py`, `test_no_original_mutation.py`

## Gate

- Original bytes unchanged after enrich on fixtures
