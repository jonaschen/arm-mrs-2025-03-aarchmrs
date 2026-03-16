import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'tools'))
import query_gic

start = time.time()
for i in range(1000):
    query_gic.load_meta()
    query_gic.load_block('GICD')
    query_gic.load_block('GICR')
    query_gic.load_block('GITS')
print(f"Baseline Time: {time.time() - start:.4f}s")
