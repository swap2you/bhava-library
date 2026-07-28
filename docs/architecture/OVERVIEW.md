# Architecture Overview

Bhāva Library is a local-first archival pipeline:

```text
source HTML snapshot
  -> IskconEducationSourceAdapter
  -> SQLite + JSONL manifests
  -> link resolver
  -> HEAD/range estimator
  -> priority scheduler (core excludes audio/video)
  -> resumable downloader
  -> verifier / quarantine / dedupe
  -> FTS5 index
  -> reports / backup
```

Downloaded third-party originals remain under `data/` and are Git-ignored.
Original Bhāva/Dauji publication records use copyright identity:

- Svarna Gauranga Das
- Dauji Publication
- Bhāva
- Harrisburg, Pennsylvania, USA
- svarnagaurangdas@gmail.com
