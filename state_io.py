from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Callable


log = logging.getLogger(__name__)


def atomic_write_json(path: Path, payload: Any, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        if mode is not None:
            os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
        if mode is not None:
            os.chmod(path, mode)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def load_json_or_recover(path: Path, *, fallback_factory: Callable[[], Any], context: str) -> Any:
    if not path.exists():
        return fallback_factory()
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("%s is invalid and will be reset (%s)", context, exc.__class__.__name__)
        return fallback_factory()
