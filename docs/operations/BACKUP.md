# Backup and Recovery

`.\bhava.ps1 backup --target <dir>` creates a timestamped non-destructive copy of config, manifests, copyright records, catalog, originals, and snapshots. Cache and staging are excluded. Hashes are verified during copy. `restore-check` samples up to 25 files.
