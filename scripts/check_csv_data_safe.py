"""Check ALL data columns for the target participant in CSV files (using csv module)."""
import csv
from pathlib import Path
import sys
from collections import defaultdict

# Config
TARGET_PARTICIPANT = "621e2e8e67b776a24055b564"
CSV_DIR = Path("scripts/rais_anonymized/csv_rais_anonymized")
DAILY_FILE = CSV_DIR / "daily_fitbit_sema_df_unprocessed.csv"
HOURLY_FILE = CSV_DIR / "hourly_fitbit_sema_df_unprocessed.csv"

def analyze_file(fpath: Path, label: str):
    if not fpath.exists():
        # Try alternate location
        alt = Path("data/lifesnaps/rais_anonymized/csv_rais_anonymized") / fpath.name
        if alt.exists():
            print(f"Found {label} at alternate location: {alt}")
            fpath = alt
        else:
            print(f"Error: {label} file not found at {fpath}")
            return

    print(f"\nScanning {label} file: {fpath}...")
    
    total_records = 0
    column_counts = defaultdict(int)
    header = []
    id_col_idx = -1

    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            try:
                header = next(reader)
            except StopIteration:
                print("Empty file")
                return

            # Find ID column
            for i, col in enumerate(header):
                if col.lower() == 'id':
                    id_col_idx = i
                    break
            
            if id_col_idx == -1:
                print("Error: 'id' column not found.")
                return

            print(f"Found {len(header)} columns.")

            for row in reader:
                if len(row) <= id_col_idx: continue
                
                pid = row[id_col_idx]
                if pid == TARGET_PARTICIPANT:
                    total_records += 1
                    for i, val in enumerate(row):
                        if i < len(header) and val and val.strip(): # Non-empty
                             column_counts[header[i]] += 1

        print(f"\nParticipant {TARGET_PARTICIPANT} in {label}:")
        print(f"  Total records: {total_records}")
        print("  Available columns with data:")
        
        # Sort by count desc
        sorted_cols = sorted(column_counts.items(), key=lambda x: x[1], reverse=True)
        for col, count in sorted_cols:
            pct = (count / total_records) * 100 if total_records > 0 else 0
            print(f"    - {col}: {count} ({pct:.1f}%)")
            
    except Exception as e:
        print(f"Error analyzing {label} CSV: {e}")

def main():
    analyze_file(DAILY_FILE, "DAILY")
    analyze_file(HOURLY_FILE, "HOURLY")

if __name__ == "__main__":
    main()
