# Phase 10 — Local UI Updates

## Delivered

- `ui/app.py` — docs at `/docs`, dashboard counts, search via `resource_names.display_title`
- Path containment helper rejecting paths outside `data/originals` and `data/quarantine`
- No unrestricted static serving of originals

## Tests

- `test_path_containment_ui.py` — green

## Gate

- UI binds `127.0.0.1` by default via CLI `serve`
