"""Download and extract the LifeSnaps dataset from Zenodo.

Usage:
    python scripts/download_lifesnaps.py [--output-dir data/lifesnaps]

Downloads the 615 MB rais_anonymized.zip, extracts its CSV files,
and stores them under the specified output directory.
"""

from __future__ import annotations

import argparse
import io
import zipfile
from pathlib import Path

import httpx

ZENODO_URL = "https://zenodo.org/records/7229547/files/rais_anonymized.zip?download=1"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "data" / "lifesnaps"


def download_and_extract(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading LifeSnaps dataset from Zenodo ({ZENODO_URL}) …")
    with httpx.Client(timeout=600, follow_redirects=True) as client:
        resp = client.get(ZENODO_URL)
        resp.raise_for_status()

    print(f"Downloaded {len(resp.content) / 1_048_576:.1f} MB — extracting …")
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        zf.extractall(output_dir)

    # List what was extracted
    for f in sorted(output_dir.rglob("*")):
        if f.is_file():
            size_mb = f.stat().st_size / 1_048_576
            print(f"  {f.relative_to(output_dir)}  ({size_mb:.1f} MB)")

    print(f"\nDone — files extracted to {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download LifeSnaps dataset")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Directory to extract files into",
    )
    args = parser.parse_args()
    download_and_extract(args.output_dir)
