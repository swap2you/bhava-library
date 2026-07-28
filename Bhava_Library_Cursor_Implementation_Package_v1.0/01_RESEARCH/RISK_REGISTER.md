# Risk Register

| ID | Risk | Control |
|---|---|---|
| R-01 | Source page changes | Adapter fixtures, snapshot diffing, parser confidence report |
| R-02 | Incorrect direct link resolution | Preserve source and resolved URL, resolution evidence, review queue |
| R-03 | Disk exhaustion | Estimate, reserve, per-chunk checks, graceful pause |
| R-04 | Huge or deceptive file | MIME/signature check, size cap, streaming |
| R-05 | Partial or corrupted file | `.part`, atomic rename, hash, content-length verification |
| R-06 | Duplicate files | SHA-256 duplicate groups; no destructive deletion by default |
| R-07 | Malicious archive | Quarantine, no execution, zip-slip checks, Defender integration |
| R-08 | Accidental Git commit | `.gitignore`, pre-commit binary guard, CI/review test |
| R-09 | Accidental public exposure | Separate repo, no static/public path, local-only optional UI |
| R-10 | Third-party originals altered | Immutable originals, read-only attribute after verification |
| R-11 | False copyright claim | Never stamp downloaded originals; copyright only original outputs |
| R-12 | Copyright registration misunderstood | Separate notice, evidence ledger, formal registration workflow |
| R-13 | Server overload | One connection per host, pacing, Retry-After, resumable jobs |
| R-14 | Access restriction encountered | Stop that item; no bypass; record inaccessible state |
| R-15 | Audio/video consumes capacity | Separate disabled profiles |
| R-16 | Cursor loads huge binaries | `.cursorignore`; manifests and metadata only |
| R-17 | Backup silently incomplete | checksums, inventory count, sampled restore, backup report |
| R-18 | Dependency drift | `uv.lock`, version gates, dependency audit |
| R-19 | Search database corruption | WAL, backups, integrity check, database rebuild from manifests |
| R-20 | Unclear provenance in future content | source dossier and transformation ledger |
