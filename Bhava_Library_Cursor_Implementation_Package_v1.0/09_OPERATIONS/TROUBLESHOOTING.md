# Troubleshooting

## `SOURCE_STRUCTURE_CHANGED`

Do not force parsing. Save the HTML and diff. Update the source adapter and fixtures.

## `DISK_GUARD_PAUSE`

Free or relocate storage, then run `resume`. Do not delete state sidecars.

## `ETAG_CHANGED`

The remote object changed. Start a new version rather than appending to the old partial.

## `RANGE_UNSUPPORTED`

Restart that file from zero safely. Never append an entire response to a partial file.

## `MIME_MISMATCH`

Quarantine and inspect. Do not rename merely to match the claimed extension.

## `DEFENDER_UNAVAILABLE`

Continue only with signature/archive validation and report reduced assurance. Do not claim malware scan passed.

## `429`

Honor Retry-After and reduce request rate. Do not add workers.

## `403` or authentication

Record inaccessible. Do not bypass.

## SQLite integrity failure

Stop writes, copy database and WAL files, rebuild from manifests, compare counts.

## Accidental staged binary

Unstage it, verify `.gitignore`, run the Git guard test, and ensure the binary remains only under `data/`.
