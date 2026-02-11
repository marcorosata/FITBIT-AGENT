"""Reassemble fitbit.bson from split parts.

Usage:
    python reassemble.py              # Creates fitbit.bson in this directory
    python reassemble.py -o ../       # Creates fitbit.bson in parent directory
"""
from __future__ import annotations

import argparse
from pathlib import Path


def reassemble(output_dir: Path | None = None) -> None:
    parts_dir = Path(__file__).parent
    output_dir = output_dir or parts_dir
    output_file = output_dir / "fitbit.bson"

    parts = sorted(parts_dir.glob("fitbit.bson.part*"))
    if not parts:
        print("No parts found!")
        return

    print(f"Reassembling {len(parts)} parts -> {output_file}")
    with open(output_file, "wb") as out:
        for part in parts:
            print(f"  {part.name} ({part.stat().st_size / 1024 / 1024:.1f} MB)")
            with open(part, "rb") as inp:
                while chunk := inp.read(64 * 1024 * 1024):
                    out.write(chunk)

    total = output_file.stat().st_size
    print(f"Done: {output_file} ({total / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reassemble fitbit.bson")
    parser.add_argument("-o", "--output-dir", type=Path, default=None)
    args = parser.parse_args()
    reassemble(args.output_dir)
