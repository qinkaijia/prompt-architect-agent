# Prompt Architect Agent v0.2.0

This release adds a local-first Windows desktop and browser workbench while preserving the v0.1 CLI.

## Highlights

- Quiet, responsive React interface with system light/dark theme support.
- FastAPI service backed by the existing deterministic prompt architecture core.
- Searchable, archivable SQLite history with secret-redacted metadata.
- Markdown preview, source view, copy actions, ZIP download, and desktop folder access.
- Windows installer and portable package that work without model APIs or an internet connection.
- Loopback-only service, same-origin checks, bounded native bridge, and artifact path containment.

## Downloads

- `Prompt-Architect-0.2.0-Setup.exe` — per-user Windows installer.
- `Prompt-Architect-0.2.0-Portable.zip` — portable Windows bundle.
- `SHA256SUMS.txt` — SHA-256 checksums for both packages.

Existing v0.1 CLI output can be imported from the History panel. This release does not invoke AI models, scan repositories, read selected file contents, or provide cloud sync.
