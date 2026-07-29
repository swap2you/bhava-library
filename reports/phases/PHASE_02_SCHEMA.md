# Phase 02 — Curation Schema Migrations

## Delivered

- `SCHEMA_VERSION = 2` in `database.py`
- `MIGRATION_002` creating curation tables (taxonomy_relations, resource_classifications, classification_evidence, classification_reviews, resource_names, technical_metadata, educational_profiles, program_mappings, production_candidates, source_dossiers, independent_creation_records, curation_runs, curation_events)
- Preserved `taxonomy_terms` and `resource_terms` from migration 001
- `migrate()` applies 001 then 002, records versions 1 and 2
- `seed_taxonomy()` idempotently loads `taxonomy_seed.TAXONOMY`

## Tests

- `tests/unit/test_curation_schema_migration.py` — green
- `tests/unit/test_taxonomy_seed.py` — green

## Gate

- `uv run pytest tests/unit/test_curation_schema_migration.py tests/unit/test_taxonomy_seed.py -q` — pass
