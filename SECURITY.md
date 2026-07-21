# Security Policy

## Supported versions

Security updates currently target the latest released version.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting feature for this repository. Do not open a public issue containing credentials, exploitable details, or private prompt content.

DeepSeek credentials are accepted only by the local credential endpoint and are stored in the operating-system credential vault. `DEEPSEEK_API_KEY` is supported for managed environments. Keys must never be submitted to issues, chat, fixtures, logs, SQLite, browser storage, or generated artifacts.

The application redacts common secret formats before sending authorized context to a model or publishing artifacts, but this is defense in depth rather than a substitute for removing credentials from source files.

The provider endpoint is fixed to `https://api.deepseek.com`; arbitrary API base URLs are intentionally unsupported to reduce credential-exfiltration risk.
