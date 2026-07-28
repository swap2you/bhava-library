# Site and Acquisition Findings

## Source

`https://iskconeducation.org/media_library/`

The source page is a large structured table. Its visible and hidden fields include:

- Name
- Level
- Type
- Format
- Theme
- Source
- normalized taxonomy slugs

The collection includes audio, video, textbooks, documents, curricula, printables, activity books, comics, Office files, archives, and other educational material contributed by multiple educators.

## Technical implications

The site should not be mirrored as ordinary webpages. The useful object is the resource manifest represented by the table.

Resource links may be:

1. direct binary files;
2. WordPress attachment or landing pages;
3. legacy-domain links;
4. WordPress uploads;
5. external public links;
6. broken or redirected links.

A source adapter must preserve the table metadata, then resolve each row into zero or more downloadable artifacts.

## Acquisition boundary

The tool may retrieve publicly accessible resources without authentication. It must not:

- bypass robots restrictions;
- defeat authentication;
- scrape private areas;
- bypass a paywall;
- solve CAPTCHAs;
- defeat rate limits;
- enumerate hidden storage;
- guess protected URLs;
- use credentials not supplied by the owner;
- circumvent cloud-drive permissions.

Inaccessible items remain catalog records with an error state.

## Why HTTrack is not the primary solution

HTTrack is useful for a private webpage snapshot but does not create the needed metadata model, priority queue, content hash catalog, disk guardrails, or reliable association between educational taxonomy and downloaded files.

The recommended solution is:

```text
table snapshot
  -> row parser
  -> normalized manifest
  -> link resolver
  -> HEAD/range probe
  -> size estimate
  -> priority scheduler
  -> resumable downloader
  -> verification
  -> SQLite index
  -> reports and backup
```

## Source snapshots

Every scan must save:

- the retrieved HTML;
- retrieved timestamp;
- final URL;
- HTTP headers;
- SHA-256 of the HTML;
- parser version;
- resource count;
- taxonomy counts.

The previous snapshot must be retained so later runs can identify:

- new records;
- removed records;
- changed links;
- changed metadata;
- changed file sizes;
- broken and recovered links.
