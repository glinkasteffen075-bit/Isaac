"""External memory adapter protocol (optional BLAU layer)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ExternalMemoryAdapter(Protocol):
    """Minimal contract for optional external memory backends."""

    name: str

    def available(self) -> bool:
        """True when backend is enabled, importable, and ready."""
        ...

    def search(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        """Return hits: {text, score?, source, ...}. Fail-soft: empty list."""
        ...

    def remember(
        self,
        messages: list[dict[str, Any]],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Persist turn/messages. Fail-soft: False on error."""
        ...
