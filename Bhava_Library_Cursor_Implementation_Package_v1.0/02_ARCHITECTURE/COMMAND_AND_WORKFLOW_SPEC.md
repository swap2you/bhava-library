# Command and Workflow Specification

## Windows entry point

`bhava.ps1` is the only command the owner needs to remember.

It must bootstrap `uv`/Python when missing or provide exact official installation instructions without silently running untrusted remote scripts unless the user invokes `bootstrap`.

## Commands

```powershell
.\bhava.ps1 bootstrap
.\bhava.ps1 doctor
.\bhava.ps1 scan
.\bhava.ps1 resolve
.\bhava.ps1 estimate --profile core
.\bhava.ps1 acquire --profile core
.\bhava.ps1 resume
.\bhava.ps1 status
.\bhava.ps1 verify
.\bhava.ps1 index
.\bhava.ps1 report
.\bhava.ps1 backup --target "E:\BhavaLibraryBackup"
.\bhava.ps1 restore-check --target "E:\BhavaLibraryBackup"
.\bhava.ps1 serve
```

## `bootstrap`

- checks Git;
- installs or locates uv;
- installs compatible Python;
- creates environment;
- syncs locked dependencies;
- creates local config from template without overwriting;
- creates data directories;
- initializes database;
- runs smoke tests.

## `doctor`

Reports:

- repository path;
- Python and uv;
- database status;
- free disk;
- safety reserve;
- source reachability;
- TLS;
- Defender availability;
- ignored-data validation;
- configuration;
- last scan/acquisition/backup.

Never prints secrets.

## `scan`

- retrieves one source page;
- saves snapshot;
- parses rows;
- diffs prior snapshot;
- updates manifest and database;
- performs no body downloads.

## `estimate`

- resolves links;
- probes size/status;
- calculates batches;
- writes human-readable and JSON reports;
- enforces profile exclusions.

## `acquire --profile core`

Without repeated confirmation:

1. runs doctor;
2. runs scan if stale;
3. resolves unresolved candidates;
4. estimates queue;
5. partitions if over cap;
6. starts first safe batch;
7. verifies each file;
8. updates index;
9. creates final report.

It pauses only for a hard guardrail.

## `resume`

Continues pending and partial jobs without rescanning unless source data is stale.

## `verify`

May verify all or a sample. It must support `--full`.

## `backup`

Uses a timestamped, non-destructive backup directory and verifies hashes. It must not delete the destination's prior backups.

## Exit codes

Document stable exit codes:

- `0` success
- `10` partial success
- `20` disk guard pause
- `21` network unavailable
- `22` source structure changed
- `23` access restricted
- `24` integrity failure
- `25` configuration error
- `26` backup verification failure
- `30` unexpected internal error
