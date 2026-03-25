import time
import sys
from query_feature import load_features

def main():
    start_time = time.perf_counter()
    for _ in range(100):
        features = load_features()
    end_time = time.perf_counter()
    print(f"Elapsed time for 100 load_features calls: {end_time - start_time:.4f} seconds")

if __name__ == '__main__':
    main()
