# Future Local Lookup UI

This is architecture preparation only. The initial milestone must not spend time building a polished interface.

## Objective

Provide a private localhost search screen for the owner while developing Bhāva resources.

## Technology

- FastAPI;
- Jinja2;
- HTMX;
- SQLite/FTS5;
- server binds only to `127.0.0.1`;
- no cloud;
- no CDN;
- no external analytics;
- no direct public URL.

## Screens

1. Dashboard
   - resource counts;
   - type/format/theme breakdown;
   - disk use;
   - queue and failure status;
   - last backup.

2. Search
   - text search;
   - age/level;
   - type;
   - format;
   - theme;
   - source;
   - profile;
   - download state;
   - Bhāva candidate state.

3. Resource detail
   - metadata;
   - original source URL;
   - local file path;
   - checksum;
   - source snapshot;
   - preview only for safe supported formats;
   - private notes;
   - candidate status.

4. Acquisition
   - read-only job status and resume instructions.

5. Publication research
   - source dossier links;
   - original work records;
   - copyright evidence.

## Safety

- third-party original paths are never mapped as unrestricted static files;
- download/open actions validate the resource ID and path containment;
- HTML is escaped;
- Office and archives are not browser-rendered;
- UI does not modify originals;
- remote binding requires a separately designed authentication phase.
