# Download Priority and Capacity Plan

## User environment

Reported free disk space: approximately 159 GB.

The initial non-audio/non-video acquisition is subject to a configurable 20 GiB planned-download cap. The cap protects against incorrect size estimates and unexpectedly large archives; it does not imply that the source collection is known to be under 20 GiB.

## Profiles

### `metadata`

Downloads no resource bodies.

Includes:

- source HTML;
- metadata;
- direct/indirect URL resolution;
- HEAD or one-byte range probes;
- size estimates;
- reports.

### `core` — default initial acquisition

Priority order:

1. PDF, EPUB, TXT, RTF, HTML
2. DOC, DOCX, ODT
3. PPT, PPTX, ODP
4. XLS, XLSX, ODS, CSV
5. JSON, XML and curriculum data
6. images and standalone artwork
7. ZIP and other archives, sorted after ordinary documents
8. unknown document-like MIME types after inspection

Explicitly excludes:

- MP3, WAV, M4A, AAC, OGG
- MP4, MOV, AVI, MKV, WEBM
- streaming playlists
- embedded audio/video pages

### `audio`

Audio only. Disabled until explicitly run.

### `video`

Video only. Disabled until explicitly run.

### `all`

All remaining approved public resources after core verification.

## Disk gates

Before acquisition:

```text
current_free
estimated_queue_bytes
unknown_size_count
temporary_overhead
safety_reserve
projected_free_after
```

Default policy:

- hard minimum free space: 50 GiB;
- minimum free percentage: 15%;
- safety reserve: maximum of 50 GiB or 15% of the volume;
- temporary overhead: 10% of known queued bytes plus 2 GiB;
- initial `core` queue cap: 20 GiB;
- maximum individual file: 2 GiB unless explicitly overridden;
- unknown-size resources are limited to one active download at a time.

If the entire `core` queue exceeds 20 GiB:

1. do not fail;
2. partition it deterministically;
3. prioritize by content value, format, then smaller files;
4. start the first safe batch;
5. leave subsequent batches pending;
6. include exact continuation commands in the report.

During acquisition:

- check free space before every file;
- check free space every 64 MiB while streaming;
- pause gracefully before crossing the reserve;
- flush database and logs;
- retain resumable `.part` files;
- exit with a specific `DISK_GUARD_PAUSE` result.

## Network limits

Defaults:

- global active downloads: 2;
- per-host active downloads: 1;
- request delay: 2 seconds minimum between new requests to the same host;
- bounded exponential retry;
- honor `Retry-After`;
- no retry storms;
- descriptive user agent with contact email;
- TLS verification enabled;
- redirects limited and logged.

## Size discovery

Try in this order:

1. HEAD;
2. GET with `Range: bytes=0-0`;
3. unresolved/unknown size.

Never fetch the full body during the estimate phase.

## Archive handling

ZIP and similar containers:

- download last within `core`;
- do not automatically extract into the originals tree;
- validate archive structure;
- detect path traversal;
- record entry names and uncompressed size;
- quarantine password-protected, malformed, executable, or suspicious archives;
- extraction is a separate later operation.
