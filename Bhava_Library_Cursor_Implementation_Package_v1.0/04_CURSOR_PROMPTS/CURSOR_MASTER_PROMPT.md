# CURSOR MASTER PROMPT — BUILD BHĀVA LIBRARY END TO END

## ROLE

Act as the principal software architect, Windows automation engineer, archival systems engineer, data engineer, security engineer, test lead, technical writer, and release validator for a new local-first repository.

## REPOSITORY

- Name: `bhava-library`
- Display name: **Bhāva Library**
- Path: `C:\Development\Workspace\DevotionalRepo\bhava-library`
- Source: `https://iskconeducation.org/media_library/`
- Current machine free space reported by owner: approximately 159 GB
- Initial planned-download cap: 20 GiB
- Initial acquisition profile: `core`
- Audio and video: explicitly deferred

## OWNER AND ORIGINAL-PUBLICATION IDENTITY

Use only for newly created original Bhāva/Dauji works:

- Copyright owner/public attribution: `Svarna Gauranga Das`
- Publisher: `Dauji Publication`
- Project: `Bhāva`
- Location: `Harrisburg, Pennsylvania, USA`
- Contact email: `svarnagaurangdas@gmail.com`
- No phone number

Never stamp this identity onto third-party reference originals.

## MISSION

Create a production-quality private reference-library platform that can inventory, download, verify, index, search, update, and back up the educational resources from the source page.

The first successful end-to-end run must download all safely obtainable non-audio/non-video resources, subject to the disk and 20 GiB batch safeguards.

Do not create the public Bhāva website feature. Do not create an eBook store. Do not create comics. This repository prepares and protects the reference library and future original-publication records.

## AUTONOMY

Do not repeatedly request approval for design, folder structure, package choice, naming, or ordinary implementation details.

Use the supplied architecture and make conservative engineering decisions when details are missing.

Stop only when:

- access would require bypassing a restriction;
- robots/site policy explicitly blocks the operation;
- source structure cannot be safely interpreted;
- disk safety cannot be maintained;
- integrity tests fail;
- a required system capability is unavailable and no safe fallback exists.

When stopped, leave the repository healthy, save state, produce a blocker report, and provide the exact continuation command.

## HARD CONSTRAINTS

1. Work in this new repository only.
2. Never modify the existing Bhāva or Krishna Story Factory repositories.
3. Keep downloaded files physically under `data/` within this project directory.
4. Git-ignore all downloaded and generated binary data.
5. Never push or publish source originals.
6. Never expose originals through a public/static directory.
7. Never alter downloaded originals.
8. Never remove embedded copyright or attribution.
9. No authentication bypass, CAPTCHA bypass, paywall bypass, URL guessing, or hidden-bucket enumeration.
10. Use no paid service or AI API.
11. No Docker, PostgreSQL, Redis, Elasticsearch, Node frontend, or cloud dependency.
12. Prefer Python 3.14; support Python 3.13.
13. Use `uv` and commit `uv.lock`.
14. Use SQLite/FTS5.
15. Use two global download workers maximum and one active download per host.
16. Audio/video are excluded from the initial `core` profile.
17. Check disk space before and during every transfer.
18. Use streaming, resumable `.part` files, atomic finalization, and SHA-256.
19. Quarantine unsafe or ambiguous content.
20. Run tests and validation before the real acquisition.
21. The actual first acquisition should begin automatically after all gates pass; do not stop merely to ask whether to proceed.
22. Preserve logs without secrets or unnecessary personal data.
23. Never claim that a copyright footer registers a work.
24. Do not add Swarna Gauranga Das/Dauji Publication notices to third-party originals.

## REQUIRED TECHNOLOGY

Core:

- Python `>=3.13,<3.15`
- uv
- httpx
- BeautifulSoup using the standard HTML parser
- Pydantic settings
- Typer
- Rich
- Tenacity
- SQLite with FTS5
- standard-library SHA-256 and disk monitoring

Quality:

- pytest
- pytest-httpx
- Hypothesis
- coverage
- Ruff
- mypy
- Bandit
- pip-audit

Optional future UI extra:

- FastAPI
- Jinja2
- HTMX
- localhost only

## REQUIRED REPOSITORY STRUCTURE

Implement the blueprint in `02_ARCHITECTURE/REPOSITORY_BLUEPRINT.md`.

Also create:

- `.cursorignore` excluding all large/local data;
- `.gitignore` that ignores `data/**`;
- pre-commit binary/size guard;
- `bhava.ps1` unified Windows entry point;
- `README.md`;
- architecture decisions;
- runbook;
- troubleshooting;
- backup instructions;
- copyright operations documentation.

## SOURCE ADAPTER

Create an `IskconEducationSourceAdapter` that:

- retrieves the source page respectfully;
- saves immutable HTML snapshots;
- parses Name, Level, Type, Format, Theme, Source, and taxonomy slugs;
- preserves original spelling and normalized values;
- assigns deterministic IDs;
- identifies direct binaries and landing pages;
- resolves public links through evidence-based methods;
- stores unresolved entries rather than guessing;
- detects source-structure drift;
- supports local HTML fixtures for tests.

Do not write a generic recursive web crawler.

## METADATA-ONLY SCAN

`bhava scan` must:

- perform no resource-body downloads;
- save source snapshot and headers;
- parse and normalize;
- diff with prior snapshot;
- write database and JSONL manifest;
- report counts, types, formats, themes, domains, and changes;
- remain idempotent.

## LINK RESOLUTION

Handle:

- direct file URLs;
- redirects;
- `Content-Disposition`;
- WordPress attachment pages;
- `<a download>`;
- download buttons;
- embed/object/iframe;
- audio/video source elements;
- old subdomain links;
- public external direct files.

Every resolution stores method, evidence, confidence, and timestamp.

Do not follow arbitrary recursive links.

## ESTIMATION

`bhava estimate --profile core` must:

- use HEAD, then a one-byte range fallback;
- never fetch full bodies;
- classify profiles;
- calculate known bytes and unknown-size count;
- calculate required temporary overhead;
- read actual free disk;
- calculate reserve and projected free space;
- create deterministic safe batches;
- cap the first core batch at 20 GiB;
- exclude audio and video;
- produce Markdown, JSON, and CSV reports.

## PRIORITY

For `core`, use:

1. PDF/EPUB/text/HTML;
2. Office documents and presentations;
3. spreadsheets/data;
4. images;
5. archives;
6. unknown document-like resources after inspection.

Within a tier, prefer:

- curricula;
- books/comics;
- lesson plans;
- activities/printables;
- worksheets;
- articles;
- smaller files before larger files when content priority is equal.

Audio and video remain pending.

## DOWNLOAD ENGINE

Implement a durable downloader, not a short script.

Required:

- stream to disk;
- no full-file memory buffering;
- Range resume;
- restart safely if Range is unsupported;
- `.part` plus state sidecar;
- atomic rename;
- content-length validation;
- ETag/Last-Modified tracking;
- SHA-256;
- bounded retry with jitter;
- Retry-After;
- TLS verification;
- timeout separation;
- safe filename/path containment;
- configurable per-file maximum;
- per-chunk disk guard;
- Ctrl+C safe shutdown;
- persistent queue;
- stable exit codes;
- no overwrite without a version decision.

## DISK SAFETY

Defaults:

- reserve = max(50 GiB, 15% of volume);
- overhead = 10% of known queue + 2 GiB;
- core initial cap = 20 GiB;
- maximum file = 2 GiB;
- unknown-size download concurrency = 1.

If a batch is unsafe:

- split it;
- start the largest safe high-priority subset;
- leave the rest pending;
- never fill the drive;
- pause with `DISK_GUARD_PAUSE` if the reserve is approached;
- retain resumable state.

## VERIFICATION

After every file:

- verify byte length where known;
- compute SHA-256;
- detect type by signature;
- compare extension/MIME/signature;
- perform safe format sanity checks;
- scan with Windows Defender when available;
- quarantine suspicious files;
- group duplicate hashes;
- keep originals unchanged;
- mark verified originals read-only;
- update manifest and audit events.

Do not destructively delete duplicates in V1.

## INDEX

Build SQLite and FTS5 indexes for metadata. Content extraction is not required for the first acquisition milestone, but design extension points.

The database must be rebuildable from manifests.

## COPYRIGHT MODULE

Implement a copyright/publication ledger for original works only.

Configuration:

```toml
[copyright]
owner = "Swarna Gauranga Das"
publisher = "Dauji Publication"
project = "Bhāva"
location = "Harrisburg, Pennsylvania, USA"
contact_email = "SwarnaGaurangaDas@gmail.com"
```

Create:

- work manifest schema;
- notice generator;
- printable footer generator;
- book/comic copyright-page generator;
- audio ©/℗ generator;
- version and hash evidence;
- registration ledger;
- existing-nine-stories intake template.

Never alter third-party source files to add these notices.

## BACKUP

Create a non-destructive Windows backup command.

Requirements:

- timestamped destination;
- resumable copy;
- include originals, manifests, catalog, config, and copyright records;
- exclude cache and disposable staging;
- hash verification;
- file count and byte report;
- sampled restore test;
- never use destructive mirror/delete behavior by default.

## OPTIONAL LOCAL UI

Scaffold only after the downloader milestone is complete and tests pass.

Implement a minimal local-only search UI if time permits, but do not delay acquisition for it.

## TESTING

Implement all tests from `08_VALIDATION/AUTOMATED_TEST_MATRIX.md`.

Use recorded/local fixtures for source parser tests. Unit and integration tests must not hammer the live site.

Before real acquisition run:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
uv run bandit -r src
uv run pip-audit
```

Resolve failures. Do not falsely report skipped checks as passing.

## REQUIRED END-TO-END EXECUTION

After implementation, fixtures, tests, and dry-run validation pass:

1. run doctor;
2. run live scan;
3. run resolution;
4. run core estimate;
5. produce capacity report;
6. if safe, automatically start `core` acquisition;
7. verify completed files;
8. build index;
9. generate final report;
10. provide continuation commands for pending batches;
11. do not download audio/video.

If live download cannot continue for a hard guardrail, preserve complete state and explain the exact blocker.

## REQUIRED DOCUMENTATION

- setup;
- command reference;
- architecture;
- source adapter;
- storage;
- disk safeguards;
- update workflow;
- backup and restore;
- copyright/publication process;
- existing nine stories process;
- troubleshooting;
- adding another source;
- UAT;
- rollback;
- security.

## REQUIRED FINAL REPORT

Return:

1. repository path and branch/commit;
2. architecture implemented;
3. commands available;
4. tests and exact results;
5. source rows found;
6. resolved/unresolved/broken counts;
7. core known and unknown size;
8. disk space before and after;
9. files downloaded;
10. bytes downloaded;
11. verification/quarantine/duplicate counts;
12. pending batches;
13. audio/video deferred counts and estimated bytes;
14. backup status;
15. documentation index;
16. unresolved risks;
17. exact next command.

## DEFINITION OF DONE

Done means:

- repository is reproducible;
- downloaded data cannot enter Git;
- source manifests are complete;
- core downloader has actually run or stopped at a documented hard guardrail;
- operations resume safely;
- disk reserve was maintained;
- files are verified;
- search index is usable;
- tests pass;
- copyright module correctly distinguishes original from third-party material;
- independent review prompts are ready;
- documentation enables another agent to validate the work.

Begin immediately with read-only project bootstrap planning, then implement all phases. Do not ask for routine confirmations.
