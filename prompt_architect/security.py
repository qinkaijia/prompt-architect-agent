from __future__ import annotations

import re


_SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(
        r"(?i)\b(api[_ -]?key|access[_ -]?token|password|secret)\s*[:=]\s*['\"]?[^\s,'\";]+"
    ),
]


def redact_secrets(value: str) -> tuple[str, bool]:
    redacted = value
    found = False
    for pattern in _SECRET_PATTERNS:
        redacted, count = pattern.subn("[REDACTED]", redacted)
        found = found or count > 0
    return redacted, found


def contains_secret(value: str) -> bool:
    return any(pattern.search(value) for pattern in _SECRET_PATTERNS)
