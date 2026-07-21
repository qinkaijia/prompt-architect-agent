# Web and desktop workbench

## First-run setup

When no DeepSeek credential exists, the application opens a focused three-step setup instead of the workbench:

1. Open the official DeepSeek key page.
2. Paste a newly-created key into a masked field.
3. Save and connect.

The server validates the key through the model-list endpoint before saving it. Success exposes only a last-four-character hint. Invalid keys, insufficient balance, network failures, rate limits, and unavailable credential storage produce distinct Chinese recovery instructions. Environment-managed credentials are displayed as read-only.

The setup can be skipped into clearly-labelled rule offline mode. Once configured, a compact status pill opens the same settings as a drawer with connection test, automatic/manual model choice, key replacement, removal, and offline switching.

## Workbench

The three-area layout remains: local history, task/result workspace, and explainable analysis. The primary action is **智能生成**. Real stages appear as a compact status row. Questions are rendered as answer fields and resume the same session. A running request can be cancelled.

File selection is authorization: desktop selection creates a local grant, while browser selection uploads into session-scoped temporary storage. The UI names exactly what may be sent to DeepSeek. Manual paths remain available only in rule offline mode.

Below 1100 pixels analysis becomes a drawer; below 800 pixels both side panels become drawers. The setup and settings remain usable at 320 pixels and 200% zoom. System light/dark themes, keyboard focus rings, reduced motion, semantic labels, and low-density neutral styling are preserved.

## Runtime and storage

FastAPI serves the React build and `/api/v1` from one loopback origin. Desktop mode opens that service in pywebview. Managed data is stored under:

```text
PromptArchitect/
├── history.db
├── logs/
├── runs/
└── temp/
```

The credential is stored by the operating system rather than in this directory. `temp/` never contains durable history and is cleared after a task or clean startup.
