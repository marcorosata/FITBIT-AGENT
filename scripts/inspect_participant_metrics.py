"""Inspect the extracted participant BSON to see available data types."""
import bson
from pathlib import Path
import collections

BSON_FILE = Path("scripts/rais_anonymized/mongo_rais_anonymized/participant_621e2e8e67b776a24055b564.bson")

def main():
    if not BSON_FILE.exists():
        print(f"File not found: {BSON_FILE}")
        return

    counts = collections.Counter()
    
    print(f"Scanning {BSON_FILE}...")
    with open(BSON_FILE, "rb") as f:
        try:
            for doc in bson.decode_file_iter(f):
                dtype = doc.get("type", "unknown")
                counts[dtype] += 1
        except Exception as e:
            print(f"Error reading BSON: {e}")

    print("\nAvailable High-Frequency Metrics (BSON):")
    for dtype, count in counts.most_common():
        print(f"  - {dtype}: {count:,} readings")

if __name__ == "__main__":
    main()
