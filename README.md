# Bhāva Library

Private, local-first reference-library platform for inventorying, downloading, verifying, and indexing educational resources from the ISKCON Ministry of Education Media Library.

**Display name:** Bhāva Library  
**Repository:** `bhava-library`  
**Owner / original publications:** Svarna Gauranga Das · Dauji Publication · Bhāva · Harrisburg, Pennsylvania, USA · svarnagaurangdas@gmail.com

## Quick start

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

The `core` profile excludes audio and video.

## Important

- Downloaded third-party originals live under `data/` and are **never** committed to Git.
- Never stamp Bhāva/Dauji copyright notices onto third-party reference originals.
- Never bypass authentication, CAPTCHAs, paywalls, or robots restrictions.

## Documentation

See `docs/` for architecture, operations, copyright, and validation guides.
