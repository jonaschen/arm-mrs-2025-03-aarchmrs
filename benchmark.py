import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent / "tools"))

from query_search import (
    load_meta,
    load_op_index,
    load_t32_op_index,
    load_a32_op_index,
    load_gic_meta,
    load_cs_meta,
    load_pmu_flat,
)

def benchmark():
    start_time = time.time()

    # Simulate a workload that calls these multiple times,
    # e.g., when searching through multiple ISAs or multiple queries in one session.
    # The actual script might be called via CLI for a single query,
    # but `collect_op_results` might call `load_*` multiple times.
    # Actually, in `query_search.py`, `load_*` is called once per `main()` execution.
    # But wait, looking at `main()`:
    # meta         = load_meta()
    # a64_op_index = load_op_index()
    # t32_op_index = load_t32_op_index()
    # a32_op_index = load_a32_op_index()
    # gic_meta     = load_gic_meta()
    # cs_meta      = load_cs_meta()
    # pmu_flat     = load_pmu_flat()

    # If the file is imported and functions are called multiple times, caching helps.
    # E.g. when testing, or when another tool uses query_search.
    iterations = 100
    for _ in range(iterations):
        load_meta()
        load_op_index()
        load_t32_op_index()
        load_a32_op_index()
        load_gic_meta()
        load_cs_meta()
        load_pmu_flat()

    end_time = time.time()

    print(f"Time taken for {iterations} iterations: {end_time - start_time:.4f} seconds")

if __name__ == "__main__":
    benchmark()
