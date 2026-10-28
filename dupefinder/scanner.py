"""Duplicate detection: size bucketing first, hashing only where it pays off."""

from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Iterator

CHUNK = 1 << 20  # 1 MiB
# Magic numbers for formats that are already compressed: recompressing them is pointless.
PRECOMPRESSED = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp3", ".mp4", ".zip", ".gz", ".7z"}


@dataclass(slots=True)
class DuplicateGroup:
    digest: str
    size: int
    paths: list[Path] = field(default_factory=list)

    @property
    def wasted_bytes(self) -> int:
        return self.size * (len(self.paths) - 1)

    def keeper(self) -> Path:
        """Keep the oldest file - usually the original, not the copy."""
        return min(self.paths, key=lambda p: (p.stat().st_mtime, str(p)))


def iter_files(roots: Iterable[Path], *, skip_hidden: bool = True, min_size: int = 1) -> Iterator[Path]:
    for root in roots:
        base = Path(root)
        if base.is_file():
            yield base
            continue
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            if skip_hidden:
                dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for name in sorted(filenames):
                if skip_hidden and name.startswith("."):
                    continue
                path = Path(dirpath) / name
                try:
                    if path.is_symlink() or path.stat().st_size < min_size:
                        continue
                except OSError:
                    continue  # broken symlink / permission error: skip quietly
                yield path


def file_digest(path: Path, algo: str = "sha256") -> str:
    h = hashlib.new(algo)
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def find_duplicates(
    roots: Iterable[Path],
    *,
    min_size: int = 1,
    algo: str = "sha256",
    hasher: Callable[[Path, str], str] = file_digest,
) -> list[DuplicateGroup]:
    by_size: dict[int, list[Path]] = defaultdict(list)
    for path in iter_files(roots, min_size=min_size):
        try:
            by_size[path.stat().st_size].append(path)
        except OSError:
            continue

    groups: list[DuplicateGroup] = []
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue  # a unique size can never contain a duplicate
        by_digest: dict[str, list[Path]] = defaultdict(list)
        for path in paths:
            try:
                by_digest[hasher(path, algo)].append(path)
            except OSError:
                continue
        for digest, dupes in by_digest.items():
            if len(dupes) > 1:
                groups.append(DuplicateGroup(digest, size, sorted(dupes)))

    return sorted(groups, key=lambda g: -g.wasted_bytes)


def plan_deletion(groups: list[DuplicateGroup]) -> list[Path]:
    """Everything except the keeper of each group. Never touches unique files."""
    return [p for g in groups for p in g.paths if p != g.keeper()]
