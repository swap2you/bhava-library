# Component Architecture

## Source adapter

`IskconEducationSourceAdapter`

Responsibilities:

- retrieve source HTML;
- parse table rows;
- preserve visible metadata and taxonomy slugs;
- assign deterministic source-row ID;
- emit normalized candidate resources;
- resolve landing pages;
- identify source and external domains;
- produce parser confidence and warnings.

The source-specific code must not leak into downloader logic.

## Scanner

Creates or updates a snapshot without downloading resource bodies.

Outputs:

- source snapshot;
- resource manifest;
- changes from previous scan;
- unresolved links;
- broken links;
- taxonomy report.

## Resolver

Resolution evidence must record:

- original row link;
- resolution method;
- page URL;
- selector or redirect used;
- resolved URL;
- confidence;
- timestamp;
- status.

Methods include:

- direct extension;
- `Content-Disposition`;
- final redirect;
- `<a download>`;
- recognized download button;
- `<audio>/<video>/<source>`;
- iframe/embed source;
- PDF/object tag;
- WordPress attachment metadata.

## Estimator

Collects status, MIME, size, range support, and last-modified without full body downloads.

## Scheduler

Produces deterministic queues by profile, priority, source host, size, and retry state.

It enforces:

- audio/video exclusion in `core`;
- initial cap;
- disk reserve;
- one active request per host;
- continuation batches.

## Downloader

Requirements:

- streaming;
- range resume when server supports it;
- safe restart when it does not;
- `.part` and state sidecar;
- atomic finalization;
- bounded retry;
- TLS validation;
- redirect logging;
- disk checks during transfer;
- progress persistence;
- Ctrl+C safe shutdown;
- no in-memory whole-file buffering.

## Verifier

Checks:

- final byte count;
- SHA-256;
- extension versus signature;
- basic parser/open check;
- duplicate hash;
- archive safety;
- optional Windows Defender scan;
- read-only finalization.

## Catalog and index

SQLite is the source of local search truth. Lightweight JSONL manifests provide recovery and interoperability.

The database must be rebuildable from source snapshots and download manifests.

## Backup

Backs up:

- code and configuration;
- manifests;
- catalog;
- originals;
- copyright records.

Never use a destructive mirror mode by default.

## Optional local UI

Read-only search by default. Administrative actions remain in the CLI until a later approved phase.
