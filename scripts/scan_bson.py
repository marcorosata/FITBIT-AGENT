"""Quick scan of fitbit.bson to count docs per participant."""
import bson
from pathlib import Path
import sys

bson_path = Path("scripts/rais_anonymized/mongo_rais_anonymized/fitbit.bson")
if not bson_path.exists():
    print(f"Not found: {bson_path}")
    sys.exit(1)

print(f"Scanning {bson_path} ({bson_path.stat().st_size / 1024 / 1024:.0f} MB)...")
sys.stdout.flush()

counts: dict[str, int] = {}
total = 0

with open(bson_path, "rb") as f:
    for doc in bson.decode_file_iter(f):
        pid = str(doc.get("id", ""))
        counts[pid] = counts.get(pid, 0) + 1
        total += 1
        if total % 500_000 == 0:
            print(f"  {total:,} docs, {len(counts)} participants...")
            sys.stdout.flush()

print(f"\nTotal: {total:,} docs, {len(counts)} participants\n")
print("Top 20 participants by doc count:")
for pid, cnt in sorted(counts.items(), key=lambda x: -x[1])[:20]:
    pct = cnt / total * 100
    est_mb = cnt / total * 2158  # rough estimate based on total file size
    print(f"  {pid}: {cnt:>10,} docs ({pct:5.1f}%) ~{est_mb:.0f} MB")
