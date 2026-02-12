"""Extract a single participant's data from the monolithic fitbit.bson.

Usage:
    python scripts/extract_participant.py [PARTICIPANT_ID]

If no ID is given, lists all participant IDs found in the first 50k docs
and asks you to choose. Writes output to:
    scripts/rais_anonymized/mongo_rais_anonymized/participant_<ID>.bson

This small file can be pushed to GitHub (no LFS needed if < 100MB)
and downloaded on Railway for streaming.
"""
from __future__ import annotations

import sys
import struct
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
RAIS = SCRIPT_DIR / "rais_anonymized" / "mongo_rais_anonymized"
PARTS_DIR = RAIS / "fitbit_parts"
FULL_BSON = RAIS / "fitbit.bson"
OUTPUT_DIR = RAIS


def reassemble_if_needed() -> Path:
    """Reassemble fitbit.bson from parts if it doesn't exist."""
    if FULL_BSON.exists() and FULL_BSON.stat().st_size > 1_000_000:
        return FULL_BSON
    parts = sorted(PARTS_DIR.glob("fitbit.bson.part*"))
    if not parts:
        print(f"ERROR: No .bson or .part files in {RAIS}")
        sys.exit(1)
    print(f"Reassembling {len(parts)} parts -> {FULL_BSON} ...")
    with open(FULL_BSON, "wb") as out:
        for p in parts:
            print(f"  {p.name} ({p.stat().st_size / 1024 / 1024:.0f} MB)")
            with open(p, "rb") as inp:
                while chunk := inp.read(64 * 1024 * 1024):
                    out.write(chunk)
    print(f"Done: {FULL_BSON.stat().st_size / 1024 / 1024:.0f} MB")
    return FULL_BSON


def scan_participants(bson_path: Path, max_docs: int = 100_000) -> dict[str, int]:
    """Quick scan to find participant IDs and doc counts."""
    import bson as bson_lib

    counts: dict[str, int] = {}
    print(f"Scanning first {max_docs:,} docs for participant IDs...")
    with open(bson_path, "rb") as f:
        for i, doc in enumerate(bson_lib.decode_file_iter(f)):
            pid = str(doc.get("id", ""))
            if pid:
                counts[pid] = counts.get(pid, 0) + 1
            if i >= max_docs:
                break
    return counts


def extract_participant(
    bson_path: Path,
    participant_id: str,
    max_docs: int = 0,
) -> Path:
    """Extract all docs for one participant into a separate BSON file.
    
    Optimized: stops early once we've found the participant's block
    and hit a different participant (file is sorted by participant).
    If max_docs > 0, stops after that many docs for the participant.
    """
    import bson as bson_lib

    output = OUTPUT_DIR / f"participant_{participant_id}.bson"
    print(f"\nExtracting participant {participant_id} from {bson_path.name}...")
    if max_docs:
        print(f"  Limit: {max_docs:,} docs")
    print(f"Output: {output}")
    sys.stdout.flush()

    count = 0
    written_bytes = 0
    found_participant = False

    with open(bson_path, "rb") as fin, open(output, "wb") as fout:
        for doc in bson_lib.decode_file_iter(fin):
            pid = str(doc.get("id", ""))
            if pid == participant_id:
                found_participant = True
                raw = bson_lib.BSON.encode(doc)
                fout.write(raw)
                count += 1
                written_bytes += len(raw)
                if count % 10_000 == 0:
                    print(f"  {count:,} docs ({written_bytes / 1024 / 1024:.1f} MB)...")
                    sys.stdout.flush()
                if max_docs and count >= max_docs:
                    print(f"  Reached max_docs limit ({max_docs:,}), stopping.")
                    break
            elif found_participant:
                # We've passed the participant's block — stop early
                print(f"  Hit different participant ({pid}), stopping early.")
                break

    size_mb = output.stat().st_size / 1024 / 1024
    print(f"\nDone: {count:,} documents, {size_mb:.1f} MB -> {output}")

    if size_mb > 90:
        print(f"WARNING: File is {size_mb:.0f} MB — too large for GitHub without LFS.")
        print("Consider using LFS or picking a participant with less data.")
    elif size_mb < 50:
        print(f"File is {size_mb:.1f} MB — small enough for direct GitHub push (no LFS needed).")

    return output


def main() -> None:
    bson_path = reassemble_if_needed()

    # Parse args: extract_participant.py [PARTICIPANT_ID] [--max-docs N]
    args = sys.argv[1:]
    max_docs = 0
    pid = ""

    i = 0
    while i < len(args):
        if args[i] == "--max-docs" and i + 1 < len(args):
            max_docs = int(args[i + 1])
            i += 2
        else:
            pid = args[i]
            i += 1

    if not pid:
        # Scan and let user choose
        counts = scan_participants(bson_path)
        print(f"\nFound {len(counts)} participants:")
        for pid, cnt in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"  {pid}: ~{cnt:,} docs")
        print()
        pid = input("Enter participant ID to extract: ").strip()
        if not pid:
            print("No ID provided. Exiting.")
            sys.exit(0)

    extract_participant(bson_path, pid, max_docs=max_docs)


if __name__ == "__main__":
    main()
