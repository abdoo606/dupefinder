from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .report import delete, human_size, to_human, to_json, to_shell_script
from .scanner import find_duplicates


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dupefinder", description="Find duplicate files by content hash.")
    p.add_argument("paths", nargs="+", help="directories or files to scan")
    p.add_argument("--min-size", type=int, default=1, help="ignore files smaller than N bytes")
    p.add_argument("--json", action="store_true", help="machine readable output")
    p.add_argument("--script", action="store_true", help="emit a reviewable 'rm' shell script")
    p.add_argument("--delete", action="store_true", help="actually delete (default is a dry run)")
    p.add_argument("--limit", type=int, default=50)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    roots = [Path(p) for p in args.paths]
    missing = [p for p in roots if not p.exists()]
    if missing:
        print(f"error: no such path: {missing[0]}", file=sys.stderr)
        return 2

    groups = find_duplicates(roots, min_size=args.min_size)

    if args.delete:
        removed = delete(groups, dry_run=False)
        print(f"removed {len(removed)} duplicate files, freed {human_size(sum(g.wasted_bytes for g in groups))}")
        return 0

    if args.json:
        print(to_json(groups))
    elif args.script:
        print(to_shell_script(groups))
    else:
        print(to_human(groups, limit=args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
