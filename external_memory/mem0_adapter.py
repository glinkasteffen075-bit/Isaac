"""Optional Mem0 OSS adapter (local-first)."""

from __future__ import annotations

import logging
import os
from typing import Any

from external_memory.config import ExternalMemoryConfig

log = logging.getLogger("Isaac.ExternalMemory.Mem0")


class Mem0Adapter:
    name = "mem0"

    def __init__(self, cfg: ExternalMemoryConfig):
        self._cfg = cfg
        self._memory = None
        self._init_error = ""
        self._tried = False

    def available(self) -> bool:
        if not self._cfg.mem0_enabled:
            return False
        self._ensure()
        return self._memory is not None

    def _ensure(self) -> None:
        if self._tried:
            return
        self._tried = True
        if not self._cfg.mem0_enabled:
            return
        try:
            from mem0 import Memory  # type: ignore
        except ImportError as exc:
            self._init_error = f"mem0ai not installed: {exc}"
            log.info("Mem0 disabled (package missing): %s", exc)
            return
        try:
            self._cfg.mem0_dir.mkdir(parents=True, exist_ok=True)
            config = self._build_config()
            if config is None:
                self._init_error = "no local/cloud backend configured"
                log.warning("Mem0 enabled but no usable backend config")
                return
            self._memory = Memory.from_config(config)
            log.info("Mem0 adapter online (user_id=%s)", self._cfg.owner_id)
        except Exception as exc:
            self._init_error = str(exc)
            self._memory = None
            log.warning("Mem0 init failed: %s", exc)

    def _build_config(self) -> dict[str, Any] | None:
        """Prefer Ollama+Chroma local; cloud only with explicit flag."""
        chroma_path = str(self._cfg.mem0_dir / "chroma")
        history_path = str(self._cfg.mem0_dir / "history.db")
        openai_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        force_cloud = self._cfg.mem0_allow_cloud and (
            os.getenv("ISAAC_MEM0_FORCE_CLOUD", "").strip().lower()
            in {"1", "true", "yes", "on"}
        )

        if not force_cloud:
            base = self._cfg.ollama_host.rstrip("/")
            return {
                "vector_store": {
                    "provider": "chroma",
                    "config": {
                        "collection_name": "isaac_mem0",
                        "path": chroma_path,
                    },
                },
                "llm": {
                    "provider": "ollama",
                    "config": {
                        "model": self._cfg.ollama_llm,
                        "ollama_base_url": base,
                        "temperature": 0.1,
                    },
                },
                "embedder": {
                    "provider": "ollama",
                    "config": {
                        "model": self._cfg.ollama_embed,
                        "ollama_base_url": base,
                    },
                },
                "history_db_path": history_path,
                "version": "v1.1",
            }

        if self._cfg.mem0_allow_cloud and openai_key:
            return {
                "vector_store": {
                    "provider": "chroma",
                    "config": {
                        "collection_name": "isaac_mem0",
                        "path": chroma_path,
                    },
                },
                "llm": {
                    "provider": "openai",
                    "config": {"model": "gpt-4o-mini", "temperature": 0.1},
                },
                "embedder": {
                    "provider": "openai",
                    "config": {"model": "text-embedding-3-small"},
                },
                "history_db_path": history_path,
                "version": "v1.1",
            }
        return None

    def search(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        if not self.available() or not (query or "").strip():
            return []
        try:
            raw = self._memory.search(
                query.strip(),
                user_id=self._cfg.owner_id,
                limit=limit,
            )
            return self._normalize_search(raw, limit=limit)
        except TypeError:
            # Older/newer SDK signature variants
            try:
                raw = self._memory.search(
                    query.strip(),
                    filters={"user_id": self._cfg.owner_id},
                )
                return self._normalize_search(raw, limit=limit)
            except Exception as exc:
                log.debug("Mem0 search failed: %s", exc)
                return []
        except Exception as exc:
            log.debug("Mem0 search failed: %s", exc)
            return []

    def _normalize_search(self, raw: Any, *, limit: int) -> list[dict[str, Any]]:
        items: list[Any]
        if isinstance(raw, dict):
            items = raw.get("results") or raw.get("memories") or []
        elif isinstance(raw, list):
            items = raw
        else:
            items = []
        out: list[dict[str, Any]] = []
        for item in items[:limit]:
            if isinstance(item, dict):
                text = (
                    item.get("memory")
                    or item.get("text")
                    or item.get("data")
                    or ""
                )
                if isinstance(text, dict):
                    text = text.get("memory") or text.get("text") or str(text)
                score = item.get("score")
                try:
                    score_f = float(score) if score is not None else None
                except (TypeError, ValueError):
                    score_f = None
                if str(text).strip():
                    hit: dict[str, Any] = {
                        "text": str(text).strip()[:400],
                        "source": self.name,
                    }
                    if score_f is not None:
                        hit["score"] = score_f
                    out.append(hit)
            elif item:
                out.append({"text": str(item)[:400], "source": self.name})
        return out

    def remember(
        self,
        messages: list[dict[str, Any]],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        if not self.available() or not messages:
            return False
        try:
            # Normalize roles for Mem0
            normalized = []
            for m in messages:
                role = (m.get("role") or "user").strip()
                if role in {"steffen", "owner", "user"}:
                    role = "user"
                elif role in {"isaac", "assistant", "ai"}:
                    role = "assistant"
                content = (m.get("content") or m.get("text") or "").strip()
                if content:
                    normalized.append({"role": role, "content": content[:2000]})
            if not normalized:
                return False
            kwargs: dict[str, Any] = {"user_id": self._cfg.owner_id}
            if metadata:
                kwargs["metadata"] = metadata
            self._memory.add(normalized, **kwargs)
            return True
        except Exception as exc:
            log.debug("Mem0 remember failed: %s", exc)
            return False

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self._cfg.mem0_enabled,
            "available": self.available(),
            "init_error": self._init_error,
            "user_id": self._cfg.owner_id,
            "data_dir": str(self._cfg.mem0_dir),
        }
