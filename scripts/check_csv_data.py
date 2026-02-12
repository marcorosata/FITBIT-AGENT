"""Check for Sleep and Stress data for the target participant in CSV files."""
import pandas as pd
from pathlib import Path
import sys

# Config
TARGET_PARTICIPANT = "621e2e8e67b776a24055b564"
CSV_DIR = Path("scripts/rais_anonymized/csv_rais_anonymized")
DAILY_FILE = CSV_DIR / "daily_fitbit_sema_df_unprocessed.csv"

def main():
    if not DAILY_FILE.exists():
        print(f"Error: CSV file not found at {DAILY_FILE}")
        # Try alternate location
        alt = Path("data/lifesnaps/rais_anonymized/csv_rais_anonymized/daily_fitbit_sema_df_unprocessed.csv")
        if alt.exists():
            print(f"Found at alternate location: {alt}")
            DAILY_FILE = alt  # Just update local reference since we pass it to read_csv later
        else:
            sys.exit(1)

    print(f"Loading {DAILY_FILE}...")
    try:
        df = pd.read_csv(DAILY_FILE)
        
        # Filter for participant
        # ID might be int or str in CSV
        df['id'] = df['id'].astype(str)
        subset = df[df['id'] == TARGET_PARTICIPANT]
        
        print(f"\nParticipant {TARGET_PARTICIPANT}:")
        print(f"  Total daily records: {len(subset)}")
        
        if len(subset) == 0:
            print("  Warning: No records found for this participant in daily CSV.")
            return

        # Check Stress
        # LifeSnaps variable is often 'stress_score' or similar
        stress_cols = [c for c in df.columns if 'stress' in c.lower()]
        print(f"\n  Stress Columns found: {stress_cols}")
        for col in stress_cols:
            valid = subset[col].notna().sum()
            print(f"    - {col}: {valid} valid values")

        # Check Sleep
        # LifeSnaps variable is often 'minutesAsleep', 'sleep_efficiency', etc.
        sleep_cols = [c for c in df.columns if 'sleep' in c.lower()]
        print(f"\n  Sleep Columns found: {sleep_cols}")
        for col in sleep_cols:
            valid = subset[col].notna().sum()
            print(f"    - {col}: {valid} valid values")
            
    except Exception as e:
        print(f"Error analyzing CSV: {e}")

if __name__ == "__main__":
    main()
