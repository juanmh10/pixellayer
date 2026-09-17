"""
File Utilities
===============
Helper functions for file path generation, size formatting,
and safe file operations.
"""

from __future__ import annotations

import math
from pathlib import Path

from src.utils.config import config
from src.utils.exceptions import FileNotFoundError_, SecurityError


def resolve_safe_path(
    path_str: str | Path,
    is_output: bool = False,
    base_dir: str | Path | None = None,
) -> str:
    """Resolve and validate a path against allowed workspaces to prevent path traversal.

    When path_str is relative:
    - If not is_output: checks cwd first, then searches across all allowed workspaces.
    - If is_output: resolves relative to base_dir (if provided) or cwd.

    Raises SecurityError if the resolved path is outside allowed workspaces.
    Raises FileNotFoundError_ if is_output is False and the target file does not exist.
    """
    raw_p = Path(path_str)
    allowed = config.get_allowed_workspaces()

    if raw_p.is_absolute():
        p = raw_p.resolve()
    else:
        if not is_output:
            # 1. Try relative to CWD
            candidate = (Path.cwd() / raw_p).resolve()
            if candidate.exists() and any(candidate.is_relative_to(ws) for ws in allowed):
                p = candidate
            else:
                # 2. Search across allowed workspaces (deepest prefix first)
                found = None
                for ws in allowed:
                    cand = (ws / raw_p).resolve()
                    if cand.exists() and cand.is_relative_to(ws):
                        found = cand
                        break
                p = found if found is not None else (allowed[0] / raw_p).resolve()
        else:
            if base_dir:
                base = Path(base_dir).resolve()
                p = (base / raw_p).resolve()
            else:
                p = (Path.cwd() / raw_p).resolve()

    # Verify confinement inside allowed workspaces
    is_safe = any(p.is_relative_to(ws) for ws in allowed)
    if not is_safe:
        raise SecurityError(
            f"Access denied: path '{path_str}' is outside authorized workspaces. "
            "Path traversal prevented."
        )

    if not is_output and not p.exists():
        raise FileNotFoundError_(str(path_str))

    return str(p)


def to_safe_relative_path(path_str: str | Path) -> str:
    """Convert a path to a safe workspace-relative path.

    Prevents leaking host machine absolute paths (e.g. system root or user dirs)
    to MCP clients and language models while preserving relative folder hierarchy.
    """
    orig_path = Path(path_str)
    p = orig_path.resolve()

    # Match against configured allowed workspaces (deepest first)
    for ws in config.get_allowed_workspaces():
        try:
            rel = p.relative_to(ws)
            return str(rel)
        except ValueError:
            continue

    # Fallback to current working directory
    try:
        rel = p.relative_to(Path.cwd().resolve())
        return str(rel)
    except ValueError:
        pass

    # Never leak absolute host paths; return only filename
    return p.name


def human_readable_size(size_bytes: int) -> str:
    """Convert bytes to human-readable string (e.g., '1.2 MB')."""
    if size_bytes == 0:
        return "0 B"
    units = ("B", "KB", "MB", "GB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    i = min(i, len(units) - 1)
    size = size_bytes / (1024**i)
    return f"{size:.1f} {units[i]}"


def generate_output_path(
    input_path: str | Path,
    suffix: str = "_processed",
    extension: str | None = None,
) -> Path:
    """Generate an output file path based on the input path.

    Args:
        input_path: Original file path.
        suffix: Suffix to append before extension (e.g., '_nobg').
        extension: New extension (without dot). None keeps original.

    Returns:
        New Path with suffix and/or changed extension.
    """
    p = Path(input_path)
    ext = f".{extension}" if extension else p.suffix
    return p.parent / f"{p.stem}{suffix}{ext}"


def ensure_parent_dir(path: str | Path) -> Path:
    """Ensure the parent directory of a path exists."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def calculate_reduction(original_bytes: int, new_bytes: int) -> float:
    """Calculate size reduction as percentage."""
    if original_bytes == 0:
        return 0.0
    return round((1 - new_bytes / original_bytes) * 100, 2)


def copy_file_safe(source_path: str | Path, target_path: str | Path) -> Path:
    """Safely copy a file between paths within allowed workspaces.

    Preserves zero-binary rule by performing OS-level copy on disk.
    """
    import shutil

    src = Path(resolve_safe_path(source_path, is_output=False))
    dst = Path(resolve_safe_path(target_path, is_output=True))
    ensure_parent_dir(dst)

    # If target is a directory, preserve original file name
    if dst.is_dir() or str(target_path).endswith("/") or str(target_path).endswith("\\"):
        dst.mkdir(parents=True, exist_ok=True)
        dst = dst / src.name

    shutil.copy2(src, dst)
    return dst
