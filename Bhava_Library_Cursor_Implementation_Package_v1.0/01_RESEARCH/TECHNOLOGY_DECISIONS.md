# Technology Decisions

## Runtime

Use Python 3.14 as the preferred runtime and test Python 3.13 as the compatibility baseline.

Reasoning:

- Python 3.14.6 is the current stable maintenance release as of June 10, 2026.
- Python 3.15 is still prerelease and must not be used for production.
- Python provides mature networking, SQLite, hashing, filesystem, and Windows support.
- A single-language implementation avoids Node, Java, Docker, Redis, and database-server dependencies.

Set:

```toml
requires-python = ">=3.13,<3.15"
```

## Environment and dependencies

Use `uv` for:

- Python installation;
- virtual environments;
- dependency resolution;
- lockfile;
- running commands;
- reproducible setup on Windows.

Do not require global Python packages after bootstrap.

## Core packages

Prefer a small, pinned set:

- `httpx` — HTTP client, streaming and connection control;
- `beautifulsoup4` — resilient HTML parsing using the standard `html.parser`;
- `pydantic` and `pydantic-settings` — validated configuration;
- `typer` — CLI;
- `rich` — progress and reports;
- `tenacity` — bounded retries;
- `filetype` — light signature detection;
- `platformdirs` — predictable local paths where needed.

Use the standard library for:

- SQLite;
- FTS5 checks;
- SHA-256;
- disk usage;
- file operations;
- CSV/JSON;
- concurrent queues;
- ZIP inspection;
- logging.

## Database

Use SQLite with:

- STRICT tables where supported;
- foreign keys;
- WAL mode;
- migration table;
- FTS5 for title, description, extracted text, source, taxonomy, and notes;
- one local database at `data/catalog/bhava-library.sqlite3`.

Do not introduce PostgreSQL for a single-user local archive.

## Optional local UI

Prepare an optional extra, not part of the first download milestone:

- FastAPI;
- Jinja2;
- HTMX;
- local binding only: `127.0.0.1`;
- no external CDN;
- no authentication unless remote access is later introduced.

Do not build React, Next.js, Electron, Docker, or a cloud deployment for the initial local lookup screen.

## Quality stack

- `pytest`
- `pytest-httpx`
- `hypothesis`
- `coverage`
- `ruff`
- `mypy`
- `bandit`
- `pip-audit`

## Dependency policy

- Pin all direct dependencies.
- Commit `uv.lock`.
- Use no unmaintained package without a documented exception.
- Avoid binary-system dependencies when the standard library or a pure-Python package is sufficient.
- Keep the core downloader functional without the optional UI.
- No paid API and no AI API are required for acquisition.
