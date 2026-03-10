#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
query_search.py - Cross-cutting keyword search across registers and operations.

Usage:
    query_search.py TCR                     # search registers + operations
    query_search.py --reg EL2              # registers only
    query_search.py --reg EL2 --state AArch64  # registers in a specific state
    query_search.py --op ADD               # operations only

Environment:
    ARM_MRS_CACHE_DIR  Override cache directory (default: <repo_root>/cache)

Exit codes:
    0  success (results found)
    1  no results or cache missing
"""

import argparse
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT  = SCRIPT_DIR.parent
CACHE_DIR  = Path(os.environ.get('ARM_MRS_CACHE_DIR', str(REPO_ROOT / 'cache')))
META_PATH  = CACHE_DIR / 'registers_meta.json'
OP_DIR     = CACHE_DIR / 'operations'

# ---------------------------------------------------------------------------
# Cache loading
# ---------------------------------------------------------------------------

def load_meta() -> dict:
    if not META_PATH.exists():
        print('Cache not found. Run: python3 tools/build_index.py', file=sys.stderr)
        sys.exit(1)
    with open(META_PATH) as f:
        return json.load(f)


def load_op_index() -> list:
    """Return sorted list of all operation_id strings from the operations directory."""
    if not OP_DIR.exists():
        return []
    return sorted(p.stem for p in OP_DIR.iterdir() if p.suffix == '.json')


def check_staleness() -> None:
    manifest_path = CACHE_DIR / 'manifest.json'
    if not manifest_path.exists():
        return
    try:
        import hashlib
        with open(manifest_path) as f:
            manifest = json.load(f)
        for fname, info in manifest.get('sources', {}).items():
            src = Path(info.get('path', REPO_ROOT / fname))
            if not src.exists():
                continue
            h = hashlib.sha256()
            with open(src, 'rb') as fh:
                for chunk in iter(lambda: fh.read(65536), b''):
                    h.update(chunk)
            if h.hexdigest() != info.get('sha256'):
                print(f'Warning: {fname} has changed since cache was built. '
                      f'Consider re-running tools/build_index.py', file=sys.stderr)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Search functions
# ---------------------------------------------------------------------------

def search_registers(pattern: str, state_filter: str | None, meta: dict) -> list:
    upper = pattern.upper()
    results = []
    for name, entries in meta.items():
        if upper in name.upper():
            for e in entries:
                if state_filter and e['state'].lower() != state_filter.lower():
                    continue
                results.append({'type': 'register', 'name': name, 'state': e['state']})
    return results


def search_operations(pattern: str, op_index: list) -> list:
    upper = pattern.upper()
    return [
        {'type': 'operation', 'name': op_id}
        for op_id in op_index
        if upper in op_id.upper()
    ]

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_results(results: list, query: str) -> None:
    reg_results = [r for r in results if r['type'] == 'register']
    op_results  = [r for r in results if r['type'] == 'operation']

    print(f"Search: {query!r}  ({len(results)} results)\n")

    if reg_results:
        print(f"Registers ({len(reg_results)}):")
        max_name = max(len(r['name']) for r in reg_results)
        for r in sorted(reg_results, key=lambda x: (x['name'], x['state'])):
            print(f"  {r['name']:{max_name}}  {r['state']}")
        print()

    if op_results:
        print(f"Operations ({len(op_results)}):")
        for r in op_results:
            print(f"  {r['name']}")
        print()

    if not results:
        print("  (no matches)")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Cross-cutting keyword search across ARM MRS registers and operations.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  query_search.py TCR
  query_search.py --reg EL2
  query_search.py --reg EL2 --state AArch64
  query_search.py --op ADD
""",
    )
    parser.add_argument('query',   nargs='?',         help='Search pattern (registers + operations)')
    parser.add_argument('--reg',   metavar='PATTERN', help='Search registers only')
    parser.add_argument('--op',    metavar='PATTERN', help='Search operations only')
    parser.add_argument('--state', metavar='STATE',   help='State filter for register search: AArch64, AArch32, ext')
    args = parser.parse_args()

    if not (args.query or args.reg or args.op):
        parser.print_help()
        return 0

    check_staleness()
    meta     = load_meta()
    op_index = load_op_index()

    results = []

    if args.reg:
        results = search_registers(args.reg, args.state, meta)
        query_str = args.reg
    elif args.op:
        results = search_operations(args.op, op_index)
        query_str = args.op
    else:
        # Combined search
        results = (
            search_registers(args.query, args.state, meta)
            + search_operations(args.query, op_index)
        )
        query_str = args.query

    print_results(results, query_str)
    return 0 if results else 1


if __name__ == '__main__':
    sys.exit(main())
