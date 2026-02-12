"""Download LFS files from GitHub if they are just pointers.

This script is called during Railway build to replace LFS pointer files
with the actual content, since Railway's Nixpacks doesn't preserve
the .git directory needed for `git lfs pull`.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = "marcorosata/FITBIT-AGENT"
BRANCH = "main"

# Files tracked by LFS and their expected minimum sizes
LFS_FILES = [
    "scripts/rais_anonymized/csv_rais_anonymized/daily_fitbit_sema_df_unprocessed.csv",
    "scripts/rais_anonymized/csv_rais_anonymized/hourly_fitbit_sema_df_unprocessed.csv",
    "scripts/rais_anonymized/mongo_rais_anonymized/fitbit_parts/fitbit.bson.part001",
    "scripts/rais_anonymized/mongo_rais_anonymized/fitbit_parts/fitbit.bson.part002",
    "scripts/rais_anonymized/mongo_rais_anonymized/fitbit_parts/fitbit.bson.part003",
    "scripts/rais_anonymized/mongo_rais_anonymized/fitbit_parts/fitbit.bson.part004",
    "scripts/rais_anonymized/mongo_rais_anonymized/fitbit_parts/fitbit.bson.part005",
]

# LFS pointer files are typically < 200 bytes
MAX_POINTER_SIZE = 200


def is_lfs_pointer(filepath: Path) -> bool:
    """Check if a file is an LFS pointer (small text starting with 'version')."""
    if not filepath.exists():
        return False
    if filepath.stat().st_size > MAX_POINTER_SIZE:
        return False  # Already real data
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        return content.startswith("version https://git-lfs.github.com/spec/v1")
    except Exception:
        return False


def download_lfs_file(rel_path: str) -> bool:
    """Download actual LFS file content from GitHub."""
    filepath = Path(rel_path)
    url = f"https://media.githubusercontent.com/media/{REPO}/{BRANCH}/{rel_path}"

    # If repo is private, use token for auth
    token = os.environ.get("GITHUB_TOKEN", "")

    print(f"  Downloading {rel_path} from GitHub LFS...")
    try:
        cmd = ["curl", "-fSL", "--retry", "3", "-o", str(filepath)]
        if token:
            cmd += ["-H", f"Authorization: token {token}"]
            print("  (using GITHUB_TOKEN for auth)")
        cmd.append(url)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min timeout for large files
        )
        if result.returncode != 0:
            print(f"  FAILED: {result.stderr.strip()}")
            return False
        size = filepath.stat().st_size
        print(f"  OK: {size / 1024 / 1024:.1f} MB")
        return True
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def main() -> None:
    print("=== LFS File Check ===")
    downloaded = 0
    skipped = 0
    failed = 0

    for rel_path in LFS_FILES:
        filepath = Path(rel_path)
        if not filepath.exists():
            print(f"  MISSING: {rel_path}")
            filepath.parent.mkdir(parents=True, exist_ok=True)
            if download_lfs_file(rel_path):
                downloaded += 1
            else:
                failed += 1
        elif is_lfs_pointer(filepath):
            print(f"  POINTER: {rel_path} ({filepath.stat().st_size}B)")
            if download_lfs_file(rel_path):
                downloaded += 1
            else:
                failed += 1
        else:
            size_mb = filepath.stat().st_size / 1024 / 1024
            print(f"  OK: {rel_path} ({size_mb:.1f} MB)")
            skipped += 1

    print(f"\nSummary: {downloaded} downloaded, {skipped} already ok, {failed} failed")
    if failed:
        print("WARNING: Some LFS files could not be downloaded!")
        sys.exit(1)


if __name__ == "__main__":
    main()
