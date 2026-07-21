# Development roadmap

## 0.1: rule-based MVP

CLI, normalized task schema, YAML classification and scoring, four strategies, four adapters, bilingual templates, context manifest, quality gate, and tests.

## 0.2: local workbench

React browser UI, Windows desktop shell, FastAPI, SQLite history, preview/export, native path selection, responsive design, and release packaging.

## 0.3: DeepSeek prompt agent

- DeepSeek structured analysis, targeted clarification, generation, model review, and one repair.
- Windows credential-vault setup, dynamic models, SSE stages, cancellation, and token usage.
- Opt-in source/text/PDF context with temporary grants, limits, and secret redaction.
- Deterministic reviewer retained as a second quality gate and offline fallback.

## Next: provider expansion and evaluation

- Optional OpenAI and Kimi providers behind the same interface.
- Repeatable prompt-quality evaluation sets and model comparison.
- Better resumability without persisting raw file contents.

## Later: opt-in project context

- Repository scanner and file index that require explicit user authorization.
- Section-level PDF and datasheet references.
- Cached project summaries and manifest refresh policies.

## Later: feedback optimization

- Failure reason tags and similar-task reuse.
- Prompt version comparison and measured template changes.
- Optional feedback fields attached to local run history.

Cloud accounts, multi-user infrastructure, vector databases, and automatic model execution remain excluded until there is a concrete product need.
