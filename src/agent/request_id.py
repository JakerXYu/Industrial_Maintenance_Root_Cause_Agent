"""Shared request ID validation.

Request IDs double as trace file basenames and as keys in the in-memory
approval map, so they must be constrained to a safe charset and must never
name a Windows reserved device. The same validator is enforced at three
boundaries: ``AgentRunner.run``, the FastAPI routes, and ``TraceStore``
save/load (via a containment-checked path helper).

Validation is strict: invalid IDs raise, they are never silently rewritten.
"""

import re
from pathlib import Path

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")

# Windows reserves these basenames regardless of extension, so we reject the
# bare name to avoid ever writing ``CON.json`` etc.
_WINDOWS_RESERVED_BASENAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{i}" for i in range(1, 10)]
    + [f"LPT{i}" for i in range(1, 10)]
)


class InvalidRequestIdError(ValueError):
    """Raised when a request ID is not safe for use as a path basename."""


def is_valid_request_id(request_id: str) -> bool:
    """Return True if ``request_id`` matches the charset and is not reserved."""
    if not isinstance(request_id, str):
        return False
    if not _REQUEST_ID_RE.match(request_id):
        return False
    return request_id.upper() not in _WINDOWS_RESERVED_BASENAMES


def validate_request_id(request_id: str) -> str:
    """Return ``request_id`` when valid; raise ``InvalidRequestIdError`` otherwise."""
    if not is_valid_request_id(request_id):
        raise InvalidRequestIdError(
            f"invalid request_id {request_id!r}: must match "
            "^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$ and not be a Windows reserved "
            "device basename"
        )
    return request_id


def request_id_path(base_dir: Path, request_id: str) -> Path:
    """Build ``base_dir / f"{request_id}.json"`` with validation and containment.

    The resolved path is checked to stay inside ``base_dir`` so a request ID can
    never escape the trace directory through traversal or a reserved name.
    """
    validate_request_id(request_id)
    base = base_dir.resolve()
    target = (base / f"{request_id}.json").resolve()
    if target.parent != base:
        raise InvalidRequestIdError(
            f"request_id {request_id!r} resolves outside the traces directory"
        )
    return target
