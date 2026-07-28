# Curation schema — rebuild and rollback

## Rebuild

The catalog remains rebuildable from:

1. Source manifests under `manifests/`
2. Verified `local_files` rows (path, size, SHA-256)
3. Derived sidecars under `data/derived/metadata/<resource-id>.json`
4. Taxonomy seed in `src/bhava_library/curation/taxonomy_seed.py`

```powershell
.\bhava.ps1 curate integrity
uv run pytest
```

## Rollback

1. Restore `data/catalog/bhava-library.sqlite3` from `data/snapshots/pre-curation-*/bhava-library.sqlite3`.
2. Delete `data/derived/**` and `data/views/**` if discarding curation outputs.
3. Do **not** touch `data/originals/**`.

Schema version 2 adds curation tables without altering acquisition tables. Dropping version-2 tables returns to acquisition-only operation while preserving originals.
