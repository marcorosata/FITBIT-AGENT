
import bson
from collections import Counter
from pathlib import Path
import sys

bson_path = Path("data/lifesnaps/rais_anonymized/mongo_rais_anonymized/fitbit.bson")

try:
    with open(bson_path, 'rb') as f:
        iterator = bson.decode_file_iter(f)
        print("Scanning first 500,000 docs for types...")
        
        counts = Counter()
        
        for i, doc in enumerate(iterator):
            t = doc.get('type')
            counts[t] += 1
            
            if i % 50000 == 0:
                print(f"Scanned {i} docs. Unique types so far: {list(counts.keys())}")
                
            if i >= 500000:
                print("Limit reached.")
                break
        
        print("\nFinal counts:", dict(counts))

except Exception as e:
    print(f"Error: {e}")
