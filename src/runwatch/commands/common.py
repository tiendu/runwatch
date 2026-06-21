from __future__ import annotations

from pathlib import Path


def write_text_atomic(path: Path, content: str, *, overwrite: bool) -> None:
    """Atomically write text without silently replacing an existing file."""

    if path.exists() and not overwrite:
        raise SystemExit(f"refusing to overwrite existing file: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
    print(f"wrote {path}")
