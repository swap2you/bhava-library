# Automated Test Matrix

## Parser

- full fixture row count;
- visible and hidden taxonomy;
- Unicode/entity decoding;
- empty cells;
- duplicate row;
- duplicate URL;
- malformed HTML;
- direct file;
- attachment page;
- old domain;
- external link;
- structure drift.

## Resolution

- redirect;
- Content-Disposition;
- download attribute;
- embed/object/iframe;
- media source;
- multiple candidate files;
- no candidate;
- redirect loop;
- external-host policy;
- authentication response;
- CAPTCHA/access-block response.

## Estimation

- HEAD supported;
- HEAD forbidden but range supported;
- neither available;
- malformed content length;
- file exceeds cap;
- batch exactly at cap;
- unknown sizes;
- audio/video exclusion.

## Downloader

- clean full download;
- Range resume;
- server ignores Range;
- ETag changes mid-resume;
- connection closes;
- timeout;
- 429 and Retry-After;
- 5xx retry;
- 404 terminal;
- Ctrl+C;
- partial state persistence;
- atomic finalization;
- no overwrite;
- filename collision;
- path traversal;
- reserved Windows filename;
- long path.

## Disk guard

- insufficient start space;
- reserve boundary;
- free space drops during transfer;
- safe graceful pause;
- resume after space restored;
- partition over-20-GiB queue.

## Verification

- valid file;
- byte mismatch;
- hash mismatch;
- extension/MIME/signature mismatch;
- duplicate hash;
- malformed ZIP;
- zip slip;
- zip bomb ratio;
- encrypted archive;
- executable content;
- Defender unavailable;
- Defender detection;
- read-only marking.

## Database

- migrations;
- foreign keys;
- state transition validation;
- transaction rollback;
- WAL recovery;
- integrity check;
- rebuild from JSONL;
- FTS5 search;
- duplicate groups;
- snapshot diff.

## Git safety

- `data/**` ignored;
- PDF rejected;
- MP3 rejected;
- ZIP rejected;
- file over 5 MiB rejected;
- approved tiny fixture allowed;
- `.cursorignore` excludes binaries.

## Copyright

- original notice uses exact owner and publisher;
- correct first-publication year input;
- unpublished notice;
- audio © and ℗;
- no phone number;
- third-party resource cannot receive owner notice;
- unknown publication status blocks registration suggestion;
- immutable work version and hash.

## Backup

- timestamped non-destructive backup;
- interrupted backup resume;
- hash verification;
- missing file detection;
- restore sample;
- cache excluded;
- prior backup retained.

## E2E

- fresh bootstrap;
- scan-only zero bodies;
- estimate-only zero bodies;
- core excludes audio/video;
- first batch obeys cap;
- acquisition/verify/index/report;
- pause/resume;
- update scan downloads only new/changed items.
