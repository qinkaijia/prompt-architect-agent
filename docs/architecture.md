# Architecture

Prompt Architect Agent keeps the v0.2 deterministic compiler as an explicit offline path and adds a DeepSeek-driven agent path for the desktop and browser workbench.

## Intelligent data flow

1. `CredentialStore` resolves `DEEPSEEK_API_KEY` before the operating-system credential vault. Full secrets never enter API responses or SQLite.
2. `DeepSeekProvider` uses the fixed `https://api.deepseek.com` endpoint, dynamically lists models, requests JSON output, normalizes usage, and retries transient failures at most twice.
3. `AgentService` owns the persisted session state and an in-memory runtime containing the original request and temporary context grants.
4. `AgentOrchestrator` asks the model for a typed task analysis and six explained complexity dimensions. `StrategyRouter` deterministically maps the score to one of the four existing strategies.
5. A session pauses in `clarifying` when the model returns critical questions. Answers are secret-redacted before persistence and analysis resumes for at most three rounds.
6. `ContextGrantStore` permits only desktop-picker paths or browser uploads. `ContextLoader` reads supported files, extracts PDF text, redacts common secret patterns, applies size limits, and wraps content as untrusted data.
7. The model returns a constrained filename/content package. Filenames must exactly match the selected strategy and pass containment checks.
8. An independent model critic and `PromptReviewer` must both pass. One model repair is allowed; a failed gate publishes nothing.
9. `ArtifactPublisher` atomically writes the reviewed package. `HistoryStore` links the run to the redacted session and token usage.

## Session states and streaming

Agent sessions move through `pending`, `clarifying`, `generating`, `reviewing`, `repairing`, and a terminal `completed`, `failed`, or `cancelled` state. The turn endpoint emits SSE events for real stages, questions, analysis, publication, failure, and cancellation; it never emits a fabricated percentage.

SQLite schema v2 stores redacted session summaries, redacted user/assistant messages, settings, and aggregate usage. Credentials, raw provider requests/responses, model reasoning, and file contents are excluded. Incomplete active sessions are marked failed after restart because their sensitive runtime state is intentionally memory-only.

## Context boundary

- Desktop paths are accepted only from the pywebview-enabled server and registered as opaque in-memory grants.
- Browser files are copied under the managed temporary root and deleted after completion, failure, cancellation, or the next application startup.
- Directory grants are manifest-only; there is no recursive repository scan.
- Text files are limited to 256 KiB, PDFs to 20 MiB, and a task to ten files and roughly 32K input tokens of extracted context.
- Artifact reads still require a database entry and resolution inside the managed run directory.

## Offline compatibility

`PromptArchitect.build()` and `generate()` retain the deterministic v0.2 contract for CLI and explicit offline use. Existing run APIs, Markdown conventions, history import, archive behavior, and project package filenames remain compatible.
