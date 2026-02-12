"""Extract a single participant from the LifeSnaps BSON file."""
import bson
import sys
from pathlib import Path

# Config
TARGET_PARTICIPANT = "621e2e8e67b776a24055b564"
LIMIT_DOCS = 200_000
INPUT_FILE = Path("scripts/rais_anonymized/mongo_rais_anonymized/fitbit.bson")
OUTPUT_FILE = Path(f"scripts/rais_anonymized/mongo_rais_anonymized/participant_{TARGET_PARTICIPANT}.bson")

def main():
    if not INPUT_FILE.exists():
        print(f"Error: Input file {INPUT_FILE} not found.")
        sys.exit(1)

    print(f"Extracting up to {LIMIT_DOCS:,} docs for {TARGET_PARTICIPANT}...")
    print(f"  Input: {INPUT_FILE} ({INPUT_FILE.stat().st_size / 1024 / 1024:.0f} MB)")
    
    count = 0
    total_scanned = 0
    extracted_size = 0
    
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    with open(INPUT_FILE, "rb") as fin, open(OUTPUT_FILE, "wb") as fout:
        # BSON decode_file_iter reads one doc at a time
        try:
            for doc in bson.decode_file_iter(fin):
                total_scanned += 1
                if total_scanned == 1:
                    first_id = doc.get("id")
                    print(f"  First doc ID found: {first_id!r} (type: {type(first_id)})")
                    print(f"  Target: {TARGET_PARTICIPANT!r}")

                if str(doc.get("id")) == TARGET_PARTICIPANT:
                    data = bson.encode(doc)
                    fout.write(data)
                    count += 1
                    extracted_size += len(data)
                    
                    if count % 1000 == 0:
                        print(f"  Extracted {count:,} docs ({extracted_size / 1024 / 1024:.1f} MB)...")
                        sys.stdout.flush()
                    
                    if count >= LIMIT_DOCS:
                        break
                
                if total_scanned % 10_000 == 0:
                     # Only print if we are skipping (i.e. not extracting) so we know it's alive
                     if count == 0: 
                        print(f"  Scanned {total_scanned:,} docs (No match yet)...")
                        sys.stdout.flush()

        except Exception as e:
            print(f"\nError during extraction: {e}")
            pass

    print(f"\nDone! Extracted {count:,} documents.")
    if count > 0:
        print(f"Output: {OUTPUT_FILE} ({OUTPUT_FILE.stat().st_size / 1024 / 1024:.1f} MB)")
    else:
        print("Warning: No documents extracted.")

if __name__ == "__main__":
    main()
