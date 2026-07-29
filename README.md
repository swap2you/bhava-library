# Bhāva Library

Private, local-first reference library for inventorying, verifying, classifying, and searching educational resources from the ISKCON Ministry of Education Media Library—without modifying or publishing downloaded originals.

**Display name:** Bhāva Library  
**Repository:** `bhava-library`  
**Owner / original publications:** Svarna Gauranga Das · Dauji Publication · Bhāva · Harrisburg, Pennsylvania, USA · svarnagaurangdas@gmail.com

## Quick start (acquisition)

```powershell
.\bhava.ps1 bootstrap
.\bhava.ps1 doctor
.\bhava.ps1 scan
.\bhava.ps1 estimate --profile core
.\bhava.ps1 acquire --profile core
.\bhava.ps1 verify
.\bhava.ps1 index
.\bhava.ps1 report
```

## Curation (logical classification)

```powershell
.\bhava.ps1 curate snapshot
.\bhava.ps1 curate enrich
.\bhava.ps1 curate classify
.\bhava.ps1 curate build-views
.\bhava.ps1 curate review-report
.\bhava.ps1 curate integrity
.\bhava.ps1 serve
```

Canonical originals under `data/originals/**` are **immutable**. Classification uses SQLite, sidecars, and generated views—never physical re-sorting.

## Archive packaging (no public upload)

```powershell
.\bhava.ps1 archive-pack --snapshot-name bhava-library-YYYYMMDD --volume-size-mib 1900
.\bhava.ps1 archive-restore-check --manifest "<manifest>" --full
```

Upload is refused while the GitHub destination is public.

## Important

- Downloaded third-party originals live under `data/` and are **never** committed to ordinary Git.
- Never stamp Bhāva/Dauji copyright notices onto third-party reference originals.
- New Bhāva products use independent creation with provenance—not cosmetic rewriting of third-party expression.

## Documentation

| Path | Content |
|---|---|
| `docs/` | Architecture, operations, copyright, validation |
| `docs/curation/` | Curation rollback/rebuild and taxonomy notes |
| `docs/history/` | Historical acquisition/completion reports |
| `reports/phases/` | Per-phase curation gate reports |
| `config/schemas/curation/` | JSON schemas for curated resources and dossiers |
| `templates/curation/` | Source dossier and review templates |

Historical extracted prompt packages remain local-only and are gitignored.
