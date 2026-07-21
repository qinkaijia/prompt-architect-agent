# Prompt Architect Agent v0.3.0

Prompt Architect is now a DeepSeek-powered prompt agent instead of only a deterministic prompt compiler.

## Highlights

- DeepSeek task understanding, targeted clarification, prompt generation, independent review, and one repair pass.
- Friendly first-run API Key setup backed by Windows Credential Manager, with environment-variable support.
- Dynamic model discovery, connection testing, real stage streaming, cancellation, and token-usage records.
- Explicitly authorized source, text, and PDF context with secret redaction, strict limits, and temporary cleanup.
- Model quality review plus the existing deterministic safety gate.
- Existing CLI, rule offline mode, history, artifacts, and four strategy contracts remain compatible.

## Security note

Never post an API Key in chat or commit it to a repository. Configure a newly-created key only inside the local application. Keys are excluded from SQLite, logs, browser storage, and generated artifacts.

## Known limits

- Only DeepSeek is supported in the intelligent path.
- The application generates prompts but does not execute target agents.
- Scanned PDFs require external OCR and are reported as unreadable.
- Active unfinished sessions restart from the beginning after an application restart.
