# Web and desktop workbench

## Product layout

The application opens directly into a three-area workspace: searchable history, the task and result surface, and an explainable analysis panel. Below 1100 pixels the analysis becomes a drawer; below 800 pixels both side panels become drawers and the content flows in one column.

The visual system uses quiet neutral surfaces, one teal accent, an 8-pixel spacing rhythm, restrained borders, and system fonts. It follows the operating-system color scheme and honors reduced-motion preferences.

## Runtime

The React production build is packaged in `prompt_architect/web/static`. FastAPI serves the static application and `/api/v1` endpoints from one origin. Browser mode uses `prompt-architect web`; desktop mode starts the same server on a random loopback port and opens it in pywebview.

Desktop data is stored under the platform application-data directory:

```text
PromptArchitect/
├── history.db
├── logs/
└── runs/
```

## Persistence and recovery

SQLite stores only secret-redacted metadata and artifact indexes. Markdown and JSON stay in per-run directories. Publishing is atomic and an indexing failure rolls back the new run directory. If the process is interrupted between those steps, the next startup reconciles the unindexed run folder from its analysis and review files.

Runs can be archived but are not permanently deleted in v0.2. Legacy CLI output can be imported explicitly; it is copied into the managed runs directory before indexing.

## Security boundary

- The server listens on `127.0.0.1` only.
- Same-origin and trusted-host checks reject cross-origin browser writes.
- The native bridge has no general shell or arbitrary file-read function.
- File and directory selection records paths only; task generation does not read their contents.
- Artifact filenames must exist in the database and resolve inside the managed run directory.
- Original requests and detected secrets are excluded from persisted analysis and history.
