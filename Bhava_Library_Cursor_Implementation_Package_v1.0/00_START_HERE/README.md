# Bhāva Library — Cursor Implementation Package v1.0

Prepared: 2026-07-28

## Repository name

- Git/local repository: `bhava-library`
- Display name: **Bhāva Library**
- Recommended local path: `C:\Development\Workspace\DevotionalRepo\bhava-library`

## Immediate objective

Create a private, local-first reference-library platform that:

1. inventories the ISKCON Ministry of Education Media Library;
2. resolves direct and indirect public resource links;
3. estimates total size before downloading;
4. downloads all non-audio/non-video resources first;
5. resumes safely after interruptions;
6. protects disk space continuously;
7. verifies every file;
8. creates a searchable SQLite catalog;
9. keeps third-party originals private and immutable;
10. prepares a later path for original Bhāva/Dauji publications.

The first execution must prioritize documents, books, comics, printables, curricula, Office files, images, and archives. Audio and video are separate later tiers.

## Important storage decision

The downloaded files live under the repository directory for operational convenience, but **must not be committed to Git**.

Git tracks:

- source code;
- configuration templates;
- database schemas;
- manifests;
- metadata snapshots;
- checksums;
- reports;
- test fixtures;
- copyright/publication records.

Git ignores:

- downloaded third-party binaries;
- working databases;
- staging files;
- extracted files;
- caches;
- backup copies;
- generated thumbnails;
- local secrets.

This prevents accidental publication and keeps Git usable.

## How to use this package

1. Create an empty local Git repository at `C:\Development\Workspace\DevotionalRepo\bhava-library`.
2. Extract this ZIP outside that repository or into a temporary folder.
3. Open the new repository in Cursor.
4. Give Cursor `04_CURSOR_PROMPTS/CURSOR_MASTER_PROMPT.md`.
5. Copy the `05_CURSOR_RULES/.cursor` directory into the repository before implementation, or instruct Cursor to create the rules verbatim.
6. Cursor must execute all phases without repeatedly requesting design approval.
7. Cursor must stop only for a hard safety blocker, access-control barrier, corrupted source, or disk-space threshold.
8. After implementation and acquisition, run the independent review prompts under `04_CURSOR_PROMPTS/review`.

## Required first-run commands after Cursor finishes

```powershell
.\bhava.ps1 doctor
.\bhava.ps1 scan
.\bhava.ps1 estimate --profile core
.\bhava.ps1 acquire --profile core
.\bhava.ps1 verify
.\bhava.ps1 index
.\bhava.ps1 report
```

The `core` profile excludes audio and video.

## Publication identity

Use only for new, original Bhāva/Dauji works:

- Copyright owner/public attribution: **Swarna Gauranga Das**
- Publisher: **Dauji Publication**
- Project: **Bhāva**
- Location: **Harrisburg, Pennsylvania, USA**
- Email: **SwarnaGaurangaDas@gmail.com**
- No phone number

Never apply this copyright notice to downloaded third-party originals.
