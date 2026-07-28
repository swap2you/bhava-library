# Backup and Recovery

## Strategy

Use at least two copies:

1. working archive inside the local repository directory;
2. timestamped external backup.

The Git repository is not a backup for downloaded binaries.

## Backup contents

Include:

- `data/originals`;
- `data/catalog`;
- `manifests`;
- `copyright`;
- `config`;
- source code;
- reports required to reconstruct state.

Exclude:

- disposable cache;
- temporary extraction;
- rebuildable thumbnails;
- old `.part` files whose jobs are terminal and documented.

## Non-destructive behavior

Default backup must create:

```text
<target>/bhava-library-backups/YYYY-MM-DD_HH-mm-ss/
```

Do not delete earlier backups.

## Verification

- compare resource/file counts;
- compare byte totals;
- verify all manifest hashes or a documented scalable verification plan;
- restore a sample into a temporary directory;
- open database read-only;
- run integrity check;
- record pass/fail.

## Database recovery

The SQLite database must be rebuildable from:

- source snapshots;
- resource manifests;
- download manifests;
- checksums;
- audit events.

## Disaster recovery order

1. restore repository code;
2. restore config;
3. restore manifests;
4. rebuild or restore database;
5. restore originals;
6. run full verification;
7. rebuild search;
8. produce reconciliation report.
