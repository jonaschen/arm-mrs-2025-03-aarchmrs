import sys
from pathlib import Path

# Add tools to PYTHONPATH so it finds cache_utils
sys.path.append(str(Path(__file__).parent / 'tools'))

import time
from tools.query_instruction import load_op

start = time.time()
for _ in range(10000):
    load_op('ADC')
end = time.time()
print(f"Time taken: {end - start:.4f} seconds")