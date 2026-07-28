# Repository Blueprint

Repository: `bhava-library`  
Display name: **Bhāva Library**

```text
bhava-library/
├── .cursor/
│   └── rules/
├── .cursorignore
├── .editorconfig
├── .gitattributes
├── .gitignore
├── .pre-commit-config.yaml
├── README.md
├── LICENSE-CODE.md
├── SECURITY.md
├── pyproject.toml
├── uv.lock
├── bhava.ps1
├── config/
│   ├── default.toml
│   ├── local.example.toml
│   ├── sources/
│   │   └── iskcon-education.toml
│   └── schemas/
├── src/
│   └── bhava_library/
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       ├── logging.py
│       ├── constants.py
│       ├── domain/
│       │   ├── models.py
│       │   ├── enums.py
│       │   └── errors.py
│       ├── sources/
│       │   ├── base.py
│       │   └── iskcon_education.py
│       ├── services/
│       │   ├── doctor.py
│       │   ├── scan.py
│       │   ├── resolve.py
│       │   ├── estimate.py
│       │   ├── schedule.py
│       │   ├── download.py
│       │   ├── verify.py
│       │   ├── deduplicate.py
│       │   ├── index.py
│       │   ├── report.py
│       │   ├── backup.py
│       │   └── copyright.py
│       ├── infrastructure/
│       │   ├── http.py
│       │   ├── database.py
│       │   ├── filesystem.py
│       │   ├── disk_guard.py
│       │   ├── hashing.py
│       │   ├── mime.py
│       │   └── windows_defender.py
│       ├── migrations/
│       ├── reports/
│       └── ui/                 # optional local-only phase
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── e2e/
│   ├── fixtures/
│   │   └── iskcon_education/
│   └── safety/
├── docs/
│   ├── architecture/
│   ├── operations/
│   ├── copyright/
│   └── validation/
├── manifests/                  # Git-tracked lightweight records
│   ├── sources/
│   ├── snapshots/
│   ├── downloads/
│   └── checksums/
├── reports/                    # selected lightweight reports may be tracked
├── copyright/                  # original Bhāva/Dauji works only
│   ├── works.csv
│   ├── manifests/
│   ├── evidence/
│   ├── registration/
│   └── templates/
├── exports/
│   └── bhava-ready/            # original approved outputs only
└── data/                       # entirely local and Git-ignored
    ├── catalog/
    │   └── bhava-library.sqlite3
    ├── originals/
    │   └── iskcon-education/
    │       ├── documents/
    │       ├── office/
    │       ├── images/
    │       ├── archives/
    │       ├── audio/
    │       ├── video/
    │       └── unknown/
    ├── staging/
    ├── quarantine/
    ├── snapshots/
    ├── cache/
    ├── derived/
    └── backups/
```

## Immutability rule

After successful verification, an original downloaded file:

- is renamed to a stable resource ID plus sanitized original filename;
- receives SHA-256;
- is marked read-only where supported;
- is never edited in place;
- is never overwritten silently;
- is replaced only by a new version record if the source changes.

## Git rule

`data/**` is ignored. A pre-commit guard must reject:

- PDFs;
- audio/video;
- archives;
- Office files;
- files over 5 MiB;
- SQLite database files;
- `.part` files.

Exceptions require an explicit allowlist entry and test fixture designation.
