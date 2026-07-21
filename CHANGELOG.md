# Changelog

## 0.3.0 - 2026-07-21

- Added DeepSeek-powered task understanding, clarification, prompt generation, review, and one deterministic repair pass.
- Added a three-step first-run credential guide backed by Windows Credential Manager, with environment-variable fallback and no plaintext storage.
- Added dynamic model discovery, connection testing, SSE progress, cancellation, token accounting, and redacted session history.
- Added explicitly authorized text, source-code, and text-extractable PDF context with bounded temporary storage and cleanup.
- Preserved the rule-based offline workflow, existing CLI, four prompt strategies, and local artifact history.
- Expanded API, frontend, storage, security, packaging, and end-to-end tests for the intelligent-agent workflow.

## 0.2.0 - 2026-07-21

- Added a quiet, responsive React workbench for local browser and Windows desktop use.
- Added FastAPI endpoints, an in-memory build API, and SQLite-backed local history.
- Added Markdown preview, copy/download actions, archive, legacy import, and native path pickers.
- Added same-origin and path-containment safeguards without reading selected file contents.
- Added Windows installer and portable-package release automation.
- Kept the existing CLI and rule-based generation behavior compatible.

## 0.1.0 - 2026-07-21

- Initial rule-based Prompt Architect Agent MVP.
- Added four prompt strategies and four target-model adapters.
- Added bilingual Jinja templates, context manifests, quality review, Typer CLI, tests, and documentation.
