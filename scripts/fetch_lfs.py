"""Download LFS files from GitHub if they are just pointers.

Called during Railway build to replace LFS pointer files with actual
content. Uses streaming download to avoid loading large files into memory.
Only downloads CSVs by default; BSON parts are optional (set FETCH_BSON=1).
"""
from __future__ import annotations

import os
import shutil
import sys
import urllib.request
import urllib.error
from pathlib import Path

REPO = "marcorosata/FITBIT-AGENT"
BRANCH = "main"

# CSV files (~55 MB total) — always downloaded
CSV_FILES = [
    "scripts/rais_anonymized/csv_rais_anonymized/daily_fitbit_sema_df_unprocessed.csv",
    "scripts/rais_anonymized/csv_rais_anonymized/hourly_fitbit_sema_df_unprocessed.csv",
]

# Single-participant BSON (~64 MB) — always downloaded
BSON_FILES = [
    "scripts/rais_anonymized/mongo_rais_anonymized/participant_621e2e8e67b776a24055b564.bson",
]

MAX_POINTER_SIZE = 200  # LFS pointer files are ~130 bytes


def is_lfs_pointer(filepath: Path) -> bool:
    """Check if a file is an LFS pointer."""
    if not filepath.exists():
        return False
    if filepath.stat().st_size > MAX_POINTER_SIZE:
        return False
    try:
        text = filepath.read_text(encoding="utf-8", errors="ignore")
        return text.startswith("version https://git-lfs.github.com/spec/v1")
    except Exception:
        return False


def download_lfs_file(rel_path: str) -> bool:
    """Stream-download LFS file content from GitHub media CDN."""
    filepath = Path(rel_path)
    url = f"https://media.githubusercontent.com/media/{REPO}/{BRANCH}/{rel_path}"

    print(f"  Downloading: {rel_path}")
    print(f"  URL: {url}")
    sys.stdout.flush()

    try:
        req = urllib.request.Request(url)
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            req.add_header("Authorization", f"token {token}")

        # Stream to file in chunks to avoid OOM
        with urllib.request.urlopen(req, timeout=600) as resp:
            with open(filepath, "wb") as f:
                shutil.copyfileobj(resp, f, length=1024 * 1024)  # 1 MB chunks

        size_mb = filepath.stat().st_size / 1024 / 1024
        print(f"  OK: {size_mb:.1f} MB")
        sys.stdout.flush()
        return True
    except urllib.error.HTTPError as e:
        print(f"  HTTP ERROR {e.code}: {e.reason}")
        return False
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def main() -> None:
    print("=== LFS File Fetch (Railway Build) ===")
    print(f"  CWD: {Path.cwd()}")
    print(f"  Python: {sys.executable}")
    sys.stdout.flush()

    files_to_fetch = list(CSV_FILES) + list(BSON_FILES)

    downloaded = 0
    skipped = 0
    failed = 0

    for rel_path in files_to_fetch:
        filepath = Path(rel_path)
        if not filepath.exists():
            print(f"\n  MISSING: {rel_path}")
            filepath.parent.mkdir(parents=True, exist_ok=True)
            if download_lfs_file(rel_path):
                downloaded += 1
            else:
                failed += 1
        elif is_lfs_pointer(filepath):
            print(f"\n  POINTER: {rel_path} ({filepath.stat().st_size}B)")
            if download_lfs_file(rel_path):
                downloaded += 1
            else:
                failed += 1
        else:
            size_mb = filepath.stat().st_size / 1024 / 1024
            print(f"  OK: {rel_path} ({size_mb:.1f} MB)")
            skipped += 1

    print(f"\n=== Summary: {downloaded} downloaded, {skipped} ok, {failed} failed ===")
    if failed:
        print("WARNING: Some files failed — app will start but data may be incomplete")


if __name__ == "__main__":
    main()
