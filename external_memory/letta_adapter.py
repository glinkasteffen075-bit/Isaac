"""Optional Letta Code CLI adapter (companion agent, not kernel)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from external_memory.config import ExternalMemoryConfig

log = logging.getLogger("Isaac.ExternalMemory.Letta")

# Read-only context snippets only; no auto-execution in search path.
_LETTA_CONTEXT_GLOBS = (
    "MEMORY.md",
    "memory.md",
    "AGENTS.md",
    "CONTEXT.md",
)


class LettaAdapter:
    name = "letta"

    def __init__(self, cfg: ExternalMemoryConfig):
        self._cfg = cfg
        self._bin_path: str | None = None
        self._init_error = ""
        self._tried = False
        self._version = ""

    def available(self) -> bool:
        if not self._cfg.letta_enabled:
            return False
        self._ensure()
        return bool(self._bin_path)

    def _ensure(self) -> None:
        if self._tried:
            return
        self._tried = True
        if not self._cfg.letta_enabled:
            return
        candidate = (self._cfg.letta_bin or "letta").strip()
        path = shutil.which(candidate) if not os.path.isabs(candidate) else candidate
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            self._bin_path = path
            self._version = self._probe_version(path)
            log.info("Letta CLI found: %s (%s)", path, self._version or "unknown")
            return
        # absolute path check without which
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            self._bin_path = candidate
            self._version = self._probe_version(candidate)
            return
        self._init_error = (
            f"letta binary not found ({candidate}); "
            "install: npm i -g @letta-ai/letta-code"
        )
        log.info("Letta disabled: %s", self._init_error)

    @staticmethod
    def _probe_version(bin_path: str) -> str:
        try:
            proc = subprocess.run(
                [bin_path, "--version"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            out = (proc.stdout or proc.stderr or "").strip()
            return out.splitlines()[0][:120] if out else ""
        except Exception:
            return ""

    def search(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        """Read-only: surface local Letta context files if present.

        Does not spawn the coding agent (that requires explicit run()).
        """
        if not self._cfg.letta_enabled or not (query or "").strip():
            return []
        hits: list[dict[str, Any]] = []
        roots = [
            Path.cwd() / ".letta",
            Path.cwd(),
        ]
        q = query.lower()
        seen: set[str] = set()
        for root in roots:
            if not root.is_dir():
                continue
            for name in _LETTA_CONTEXT_GLOBS:
                path = root / name
                key = str(path.resolve()) if path.exists() else ""
                if not key or key in seen:
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                seen.add(key)
                # Prefer files whose content or name relates to query terms
                snippet = text.strip()[:400]
                if not snippet:
                    continue
                score = 0.4
                if any(tok in text.lower() for tok in q.split() if len(tok) >= 4):
                    score = 0.7
                hits.append(
                    {
                        "text": f"[letta:{name}] {snippet}",
                        "source": self.name,
                        "score": score,
                        "path": str(path),
                    }
                )
                if len(hits) >= limit:
                    return hits
        return hits

    def remember(
        self,
        messages: list[dict[str, Any]],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Letta Code has no simple programmatic memory write in this bounded adapter.

        Returns False always — persistence is handled by Letta CLI sessions.
        """
        return False

    def run(
        self,
        prompt: str,
        *,
        cwd: str | None = None,
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        """Explicit owner-triggered coding agent run (subprocess)."""
        if not self.available():
            return {
                "ok": False,
                "error": self._init_error or "Letta CLI not available",
                "source": self.name,
            }
        prompt = (prompt or "").strip()
        if not prompt:
            return {"ok": False, "error": "empty prompt", "source": self.name}
        workdir = cwd or os.getcwd()
        try:
            # Non-interactive best-effort: pass prompt as argument if supported;
            # fall back to stdin.
            proc = subprocess.run(
                [self._bin_path, "-p", prompt],
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env={**os.environ, "CI": "1", "NO_COLOR": "1"},
            )
            stdout = (proc.stdout or "").strip()
            stderr = (proc.stderr or "").strip()
            # Some CLI versions may not support -p; retry with positional
            if proc.returncode != 0 and (
                "unknown" in stderr.lower() or "unrecognized" in stderr.lower()
            ):
                proc = subprocess.run(
                    [self._bin_path, prompt],
                    cwd=workdir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                    env={**os.environ, "CI": "1", "NO_COLOR": "1"},
                )
                stdout = (proc.stdout or "").strip()
                stderr = (proc.stderr or "").strip()
            text = stdout or stderr
            return {
                "ok": proc.returncode == 0,
                "text": text[:8000],
                "returncode": proc.returncode,
                "source": self.name,
                "error": "" if proc.returncode == 0 else (stderr[:500] or "letta failed"),
            }
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "error": f"letta timed out after {timeout}s",
                "source": self.name,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc), "source": self.name}

    def status(self) -> dict[str, Any]:
        avail = self.available()
        return {
            "name": self.name,
            "enabled": self._cfg.letta_enabled,
            "available": avail,
            "init_error": self._init_error,
            "bin": self._bin_path or self._cfg.letta_bin,
            "version": self._version,
        }
