import hashlib
import json
from collections.abc import Mapping, Sequence


def _normalize(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split()).lower()
    if isinstance(value, Mapping):
        return {key: _normalize(value[key]) for key in sorted(value)}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize(item) for item in value]
    return value


def content_hash(payload: str | dict | list | None) -> str:
    normalized = _normalize(payload)
    if isinstance(normalized, str):
        serialized = normalized
    else:
        serialized = json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()
