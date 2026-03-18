import time
from query_pmu import load_meta, load_cpu, load_flat

def run_bench():
    # Load many times to simulate heavy usage
    start = time.time()
    for _ in range(1000):
        load_meta()
        load_cpu('cortex-a710') # need a valid cpu if it exists
        load_flat()
    print(f"Time taken: {time.time() - start:.4f}s")

if __name__ == '__main__':
    run_bench()
