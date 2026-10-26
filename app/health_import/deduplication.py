from __future__ import annotations

import hashlib
import json
from typing import Any


def source_id(value: Any, *, fallback_parts: tuple[Any, ...]) -> str:
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes) and value:
        return value.hex()
    if value not in (None, ""):
        return str(value)
    return hashlib.sha256(
        "|".join(str(part) for part in fallback_parts).encode("utf-8")
    ).hexdigest()


def normalized_hash(payload: dict[str, Any]) -> str:
    normalized = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

