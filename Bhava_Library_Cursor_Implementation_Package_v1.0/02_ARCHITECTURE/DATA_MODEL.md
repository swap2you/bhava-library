# Data Model

## Main tables

### `sources`

- `source_id`
- `name`
- `base_url`
- `adapter`
- `enabled`
- `created_at`
- `last_scan_at`

### `source_snapshots`

- `snapshot_id`
- `source_id`
- `retrieved_at`
- `html_path`
- `html_sha256`
- `http_status`
- `final_url`
- `parser_version`
- `row_count`

### `resources`

- `resource_id`
- `source_id`
- `source_row_key`
- `title_original`
- `title_normalized`
- `level`
- `media_type`
- `media_format`
- `theme`
- `source_label`
- `language`
- `original_url`
- `resolved_url`
- `source_domain`
- `resolution_method`
- `resolution_confidence`
- `profile`
- `priority`
- `status`
- `first_seen_at`
- `last_seen_at`
- `removed_at`

### `remote_objects`

- `remote_object_id`
- `resource_id`
- `url`
- `final_url`
- `http_status`
- `mime_type`
- `content_length`
- `accept_ranges`
- `etag`
- `last_modified`
- `probed_at`

### `download_jobs`

- `job_id`
- `resource_id`
- `batch_id`
- `state`
- `attempt_count`
- `bytes_downloaded`
- `expected_bytes`
- `part_path`
- `started_at`
- `updated_at`
- `completed_at`
- `last_error_code`
- `last_error_message`

### `local_files`

- `file_id`
- `resource_id`
- `relative_path`
- `size_bytes`
- `sha256`
- `detected_type`
- `verified_at`
- `read_only`
- `duplicate_of_file_id`
- `quarantine_reason`

### `taxonomy_terms`

Normalized dimensions and aliases.

### `resource_terms`

Many-to-many resource taxonomy.

### `events`

Append-only audit events for scan, resolution, estimate, download, verify, pause, failure, backup, and promotion.

### `backups`

Backup target, run, file count, bytes, verification, and restore test.

## Future publication tables

These must never imply ownership of third-party originals.

- `original_works`
- `work_versions`
- `work_contributors`
- `source_dossiers`
- `asset_rights`
- `copyright_notices`
- `registration_events`
- `publication_events`
- `bhava_exports`

## FTS5

Index only text fields and extracted text. Never attempt to place binary bytes into FTS.

Indexed fields:

- title;
- source;
- theme;
- type;
- format;
- level;
- language;
- description;
- extracted text;
- private research notes;
- original-work source dossier.

## State machine

```text
discovered
 -> resolving
 -> resolved | unresolved | inaccessible
 -> estimated | size_unknown
 -> queued
 -> downloading
 -> paused | failed_retryable | failed_terminal
 -> downloaded
 -> verifying
 -> verified | quarantined | corrupt
 -> indexed
```

Transitions must be validated. No direct `discovered -> verified`.
