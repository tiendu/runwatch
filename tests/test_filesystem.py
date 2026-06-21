from __future__ import annotations

import stat
from pathlib import Path

import pytest

from runwatch.errors import OutputError
from runwatch.filesystem import write_text_atomic


def test_atomic_write_refuses_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("old", encoding="utf-8")

    with pytest.raises(OutputError, match="refusing to overwrite"):
        write_text_atomic(path, "new", overwrite=False)

    assert path.read_text(encoding="utf-8") == "old"


def test_atomic_write_replaces_and_applies_mode(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"

    write_text_atomic(path, "content", overwrite=True, mode=0o640)

    assert path.read_text(encoding="utf-8") == "content"
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert list(tmp_path.glob("*.tmp")) == []
