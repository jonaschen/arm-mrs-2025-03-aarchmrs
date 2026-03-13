#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
query_search.py - Cross-cutting keyword search across registers and operations.

Usage:
    query_search.py TCR                     # search registers + operations
    query_search.py --reg EL2              # registers only
    query_search.py --reg EL2 --state AArch64  # registers in a specific state
    query_search.py --op ADD               # operations only
    query_search.py EnableGrp1             # also searches GIC registers when GIC cache is present
    query_search.py --spec gic EnableGrp1  # GIC register names only
    query_search.py --spec aarchmrs TCR    # AARCHMRS registers and operations only
    query_search.py --spec pmu CPU_CYCLES  # PMU event names only

Environment:
    ARM_MRS_CACHE_DIR  Override cache directory (default: <repo_root>/cache)

Exit codes:
    0  success (results found)
    1  no results or cache missing
"""

import argparse
import json
import sys

from cache_utils import CACHE_DIR, ARM_ARM_CACHE, check_staleness

META_PATH  = CACHE_DIR / 'registers_meta.json'
OP_DIR     = CACHE_DIR / 'operations'
T32_OP_DIR = ARM_ARM_CACHE / 't32_operations'
A32_OP_DIR = ARM_ARM_CACHE / 'a32_operations'
GIC_META_PATH  = CACHE_DIR / 'gic' / 'gic_meta.json'
CS_META_PATH   = CACHE_DIR / 'coresight' / 'cs_meta.json'
PMU_FLAT_PATH  = CACHE_DIR / 'pmu_events_flat.json'

# ---------------------------------------------------------------------------
# Cache loading
# ---------------------------------------------------------------------------

def load_meta() -> dict | None:
    if not META_PATH.exists():
        return None
    with open(META_PATH) as f:
        return json.load(f)


def load_op_index() -> list:
    """Return sorted list of all A64 operation_id strings from the operations directory."""
    if not OP_DIR.exists():
        return []
    return sorted(p.stem for p in OP_DIR.iterdir() if p.suffix == '.json')


def load_t32_op_index() -> list:
    """Return sorted list of all T32 operation_id strings (empty if cache absent)."""
    if not T32_OP_DIR.exists():
        return []
    return sorted(p.stem for p in T32_OP_DIR.iterdir() if p.suffix == '.json')


def load_a32_op_index() -> list:
    """Return sorted list of all A32 operation_id strings (empty if cache absent)."""
    if not A32_OP_DIR.exists():
        return []
    return sorted(p.stem for p in A32_OP_DIR.iterdir() if p.suffix == '.json')


def load_gic_meta() -> dict | None:
    """Load GIC metadata (name index). Returns None if GIC cache not built."""
    if not GIC_META_PATH.exists():
        return None
    with open(GIC_META_PATH) as f:
        return json.load(f)


def load_cs_meta() -> dict | None:
    """Load CoreSight metadata (name index). Returns None if CoreSight cache not built."""
    if not CS_META_PATH.exists():
        return None
    with open(CS_META_PATH) as f:
        return json.load(f)


def load_pmu_flat() -> dict | None:
    """Load PMU flat event index. Returns None if PMU cache not built."""
    if not PMU_FLAT_PATH.exists():
        return None
    with open(PMU_FLAT_PATH) as f:
        return json.load(f)

# ---------------------------------------------------------------------------
# Search functions
# ---------------------------------------------------------------------------

def search_registers(pattern: str, state_filter: str | None, meta: dict | None) -> list:
    if not meta:
        return []
    upper = pattern.upper()
    results = []
    for name, entries in meta.items():
        if upper in name.upper():
            for e in entries:
                if state_filter and e['state'].lower() != state_filter.lower():
                    continue
                results.append({'type': 'register', 'name': name, 'state': e['state']})
    return results


def search_operations(pattern: str, op_index: list, isa: str = 'a64') -> list:
    upper = pattern.upper()
    return [
        {'type': 'operation', 'name': op_id, 'isa': isa.upper()}
        for op_id in op_index
        if upper in op_id.upper()
    ]


def search_gic_registers(pattern: str, gic_meta: dict | None) -> list:
    """Search GIC register names and field names (GICD/GICR/GITS) for a pattern."""
    if not gic_meta:
        return []
    upper  = pattern.upper()
    idx    = gic_meta.get('name_index', {})
    fidx   = gic_meta.get('field_index', {})
    seen   = set()
    results = []

    # Search register names
    for name, info in idx.items():
        if upper in name.upper() and name not in seen:
            seen.add(name)
            results.append({
                'type':  'gic_register',
                'name':  name,
                'block': info.get('block', ''),
            })

    # Search field names — return the register(s) that contain the field
    for fname, reg_names in fidx.items():
        if upper in fname.upper():
            for reg_name in reg_names:
                if reg_name not in seen:
                    seen.add(reg_name)
                    info = idx.get(reg_name, {})
                    results.append({
                        'type':  'gic_register',
                        'name':  reg_name,
                        'block': info.get('block', ''),
                    })

    return results


def search_cs_registers(pattern: str, cs_meta: dict | None) -> list:
    """Search CoreSight register names and field names (ETM/CTI/STM/ITM/ID_BLOCK) for a pattern."""
    if not cs_meta:
        return []
    upper  = pattern.upper()
    idx    = cs_meta.get('name_index', {})
    fidx   = cs_meta.get('field_index', {})
    seen   = set()
    results = []

    # Search register names
    for name, info in idx.items():
        if upper in name.upper() and name not in seen:
            seen.add(name)
            results.append({
                'type':      'cs_register',
                'name':      name,
                'component': info.get('component', ''),
            })

    # Search field names — return the register(s) that contain the field
    for fname, reg_names in fidx.items():
        if upper in fname.upper():
            for reg_name in reg_names:
                if reg_name not in seen:
                    seen.add(reg_name)
                    info = idx.get(reg_name, {})
                    results.append({
                        'type':      'cs_register',
                        'name':      reg_name,
                        'component': info.get('component', ''),
                    })

    return results


def search_pmu_events(pattern: str, pmu_flat: dict | None) -> list:
    """Search PMU event names across all CPUs for a pattern."""
    if not pmu_flat:
        return []
    upper = pattern.upper()
    events_index = pmu_flat.get('events', {})
    results = []
    for name, entries in events_index.items():
        if upper in name.upper():
            cpu_slugs = [e['cpu_slug'] for e in entries]
            results.append({
                'type':         'pmu_event',
                'name':         name,
                'cpus':         cpu_slugs,
                'cpu_count':    len(cpu_slugs),
                'architectural': any(e.get('architectural') for e in entries),
            })
    return results

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_results(results: list, query: str) -> None:
    reg_results = [r for r in results if r['type'] == 'register']
    op_results  = [r for r in results if r['type'] == 'operation']
    gic_results = [r for r in results if r['type'] == 'gic_register']
    cs_results  = [r for r in results if r['type'] == 'cs_register']
    pmu_results = [r for r in results if r['type'] == 'pmu_event']

    print(f"Search: {query!r}  ({len(results)} results)\n")

    if reg_results:
        print(f"Registers ({len(reg_results)}):")
        max_name = max(len(r['name']) for r in reg_results)
        for r in sorted(reg_results, key=lambda x: (x['name'], x['state'])):
            print(f"  {r['name']:{max_name}}  {r['state']}")
        print()

    if gic_results:
        print(f"GIC Registers ({len(gic_results)}):")
        max_name = max(len(r['name']) for r in gic_results)
        for r in sorted(gic_results, key=lambda x: (x['block'], x['name'])):
            print(f"  {r['name']:{max_name}}  {r['block']}")
        print()
        print("  -> Use: python3 tools/query_gic.py <register_name>")
        print()

    if cs_results:
        print(f"CoreSight Registers ({len(cs_results)}):")
        max_name = max(len(r['name']) for r in cs_results)
        for r in sorted(cs_results, key=lambda x: (x['component'], x['name'])):
            print(f"  {r['name']:{max_name}}  {r['component']}")
        print()
        print("  -> Use: python3 tools/query_coresight.py <component> <register_name>")
        print()

    if pmu_results:
        print(f"PMU Events ({len(pmu_results)}):")
        for r in sorted(pmu_results, key=lambda x: x['name']):
            arch_marker = ' [arch]' if r.get('architectural') else ''
            cpu_slugs = sorted(r['cpus'])
            cpu_preview = ', '.join(cpu_slugs[:3])
            if len(cpu_slugs) > 3:
                cpu_preview += f', ... (+{len(cpu_slugs) - 3})'
            print(f"  {r['name']}{arch_marker}  ({r['cpu_count']} CPU(s): {cpu_preview})")
        print()
        print("  -> Use: python3 tools/query_pmu.py <cpu_slug> <event_name>")
        print()

    if op_results:
        # Group by ISA for cleaner output
        by_isa: dict = {}
        for r in op_results:
            isa = r.get('isa', 'A64')
            by_isa.setdefault(isa, []).append(r['name'])
        for isa in sorted(by_isa.keys()):
            names = by_isa[isa]
            print(f"Operations/{isa} ({len(names)}):")
            for name in names:
                print(f"  {name}")
            print()

    if not results:
        print("  (no matches)")

# ---------------------------------------------------------------------------
# Entry point

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
  query_search.py --op LDR --isa t32
  query_search.py --op LDR --isa all
  query_search.py EnableGrp1
  query_search.py --spec gic EnableGrp1
  query_search.py TRC
  query_search.py --spec coresight TRC
  query_search.py --spec aarchmrs TCR
  query_search.py --spec pmu CPU_CYCLES
""",
    )
    parser.add_argument('query',   nargs='?',         help='Search pattern (registers + operations + GIC + CoreSight + PMU)')
    parser.add_argument('--reg',   metavar='PATTERN', help='Search registers only')
    parser.add_argument('--op',    metavar='PATTERN', help='Search operations only')
    parser.add_argument('--state', metavar='STATE',   help='State filter for register search: AArch64, AArch32, ext')
    parser.add_argument(
        '--isa',
        metavar='ISA',
        default='all',
        choices=('a64', 't32', 'a32', 'all'),
        help='ISA filter for operation search: a64, t32, a32, all (default: all)',
    )
    parser.add_argument(
        '--spec',
        metavar='SPEC',
        choices=('aarchmrs', 'gic', 'coresight', 'pmu'),
        help='Restrict search to a specific spec database: aarchmrs, gic, coresight, pmu',
    )
    args = parser.parse_args()

    if not (args.query or args.reg or args.op):
        parser.print_help()
        return 0

    check_staleness()
    meta         = load_meta()
    a64_op_index = load_op_index()
    t32_op_index = load_t32_op_index()
    a32_op_index = load_a32_op_index()
    gic_meta     = load_gic_meta()
    cs_meta      = load_cs_meta()
    pmu_flat     = load_pmu_flat()

    # Warn if register search requested but A64 cache is absent
    if (args.reg or args.query) and meta is None and not args.spec:
        print(
            'Warning: register cache not found (A64 cache absent). '
            'Run: python3 tools/build_index.py',
            file=sys.stderr,
        )

    isa_filter = args.isa.lower()

    def collect_op_results(pattern: str) -> list:
        """Collect operation results across selected ISAs."""
        results = []
        if isa_filter in ('a64', 'all'):
            results += search_operations(pattern, a64_op_index, 'a64')
        if isa_filter in ('t32', 'all'):
            results += search_operations(pattern, t32_op_index, 't32')
        if isa_filter in ('a32', 'all'):
            results += search_operations(pattern, a32_op_index, 'a32')
        return results

    results = []

    if args.spec == 'aarchmrs':
        # AARCHMRS-only: registers + operations (no GIC/CoreSight/PMU)
        pattern   = args.query or args.reg or args.op or ''
        results   = search_registers(pattern, args.state, meta) + collect_op_results(pattern)
        query_str = pattern
    elif args.spec == 'gic':
        # GIC-only search
        pattern   = args.query or args.reg or args.op or ''
        results   = search_gic_registers(pattern, gic_meta)
        query_str = pattern
    elif args.spec == 'coresight':
        # CoreSight-only search
        pattern   = args.query or args.reg or args.op or ''
        results   = search_cs_registers(pattern, cs_meta)
        query_str = pattern
    elif args.spec == 'pmu':
        # PMU-only: event names across CPUs
        pattern   = args.query or args.reg or args.op or ''
        results   = search_pmu_events(pattern, pmu_flat)
        query_str = pattern
    elif args.reg:
        results = search_registers(args.reg, args.state, meta)
        query_str = args.reg
    elif args.op:
        results = collect_op_results(args.op)
        query_str = args.op
    else:
        # Combined search: AARCHMRS registers + operations + GIC registers + CoreSight registers + PMU events
        results = (
            search_registers(args.query, args.state, meta)
            + collect_op_results(args.query)
            + search_gic_registers(args.query, gic_meta)
            + search_cs_registers(args.query, cs_meta)
            + search_pmu_events(args.query, pmu_flat)
        )
        query_str = args.query

    print_results(results, query_str)
    return 0 if results else 1


if __name__ == '__main__':
    sys.exit(main())
