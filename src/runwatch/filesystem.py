from __future__ import annotations

import os
import stat
import tempfile
from contextlib import suppress
from pathlib import Path

from runwatch.errors import OutputError


def _destination_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def write_bytes_atomic(
    path: Path,
    content: bytes,
    *,
    overwrite: bool,
    mode: int | None = None,
) -> None:
    """Atomically write bytes in the destination directory.

    A unique temporary file avoids collisions between concurrent invocations.
    Existing permissions are preserved on replacement unless ``mode`` is
    supplied explicitly.
    """

    destination_exists = _destination_exists(path)
    if destination_exists and not overwrite:
        raise OutputError(f"refusing to overwrite existing file: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)

    effective_mode = 0o644 if mode is None and not destination_exists else mode
    if effective_mode is None and destination_exists:
        try:
            effective_mode = stat.S_IMODE(path.stat().st_mode)
        except OSError as exc:
            raise OutputError(f"cannot inspect existing file {path}: {exc}") from exc

    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        if effective_mode is not None:
            temporary_path.chmod(effective_mode)

        os.replace(temporary_path, path)
        temporary_path = None

        # Persist the directory entry where the filesystem supports it.
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except OSError as exc:
        raise OutputError(f"cannot write {path}: {exc}") from exc
    finally:
        if temporary_path is not None:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)


def write_text_atomic(
    path: Path,
    content: str,
    *,
    overwrite: bool,
    mode: int | None = None,
) -> None:
    """Atomically write UTF-8 text."""

    write_bytes_atomic(
        path,
        content.encode("utf-8"),
        overwrite=overwrite,
        mode=mode,
    )
