#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
query_pmu.py — ARM PMU event code and description queries.

Queries the PMU cache built by build_pmu_index.py.

Usage:
    query_pmu.py cortex-a710                   # all events with codes and descriptions
    query_pmu.py cortex-a710 CPU_CYCLES        # single event full detail
    query_pmu.py --search L1D_CACHE            # cross-CPU event name search
    query_pmu.py --list                        # all CPUs with event counts
    query_pmu.py --list cortex                 # CPUs matching pattern

Environment:
    ARM_MRS_CACHE_DIR  Override cache directory (default: <repo_root>/cache)

Exit codes:
    0  success
    1  CPU/event not found, or cache missing
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT  = SCRIPT_DIR.parent
CACHE_DIR  = Path(os.environ.get('ARM_MRS_CACHE_DIR', str(REPO_ROOT / 'cache')))

PMU_CACHE  = CACHE_DIR / 'pmu'
META_PATH  = CACHE_DIR / 'pmu_meta.json'
FLAT_PATH  = CACHE_DIR / 'pmu_events_flat.json'

# ---------------------------------------------------------------------------
# Cache loading
# ---------------------------------------------------------------------------

def _cache_missing() -> bool:
    return not META_PATH.exists()


def load_meta() -> dict:
    if _cache_missing():
        print('PMU cache not found. Run: python3 tools/build_pmu_index.py', file=sys.stderr)
        sys.exit(1)
    with open(META_PATH) as f:
        return json.load(f)


def load_cpu(slug: str) -> dict:
    path = PMU_CACHE / f'{slug}.json'
    if not path.exists():
        print(f'PMU cache for "{slug}" not found. Run: python3 tools/build_pmu_index.py',
              file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def load_flat() -> dict:
    if not FLAT_PATH.exists():
        print('PMU flat index not found. Run: python3 tools/build_pmu_index.py',
              file=sys.stderr)
        sys.exit(1)
    with open(FLAT_PATH) as f:
        return json.load(f)

# ---------------------------------------------------------------------------
# CPU slug resolution
# ---------------------------------------------------------------------------

def _normalise_slug(name: str) -> str:
    """Convert user input to a lowercase hyphenated slug for cache lookup."""
    slug = name.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug


def resolve_cpu(name: str, meta: dict) -> str | None:
    """
    Find the CPU slug in the cache. Accepts the canonical slug, CPU name, or
    partial matches (e.g. 'a710' → 'cortex-a710').

    Returns the canonical slug or None if no unique match is found.
    """
    cpus = meta.get('cpus', {})

    slug = _normalise_slug(name)

    # Exact slug match
    if slug in cpus:
        return slug

    # CPU name match (case-insensitive)
    for s, info in cpus.items():
        if info.get('cpu_name', '').lower() == name.lower():
            return s

    # Partial slug match
    matches = [s for s in cpus if slug in s]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Ambiguous CPU name '{name}'. Matches: {', '.join(sorted(matches))}", file=sys.stderr)
        return None

    return None

# ---------------------------------------------------------------------------
# Event resolution
# ---------------------------------------------------------------------------

def resolve_event(events: list, name: str) -> dict | None:
    """Find an event by name (case-insensitive)."""
    upper = name.upper()
    for ev in events:
        if ev['name'].upper() == upper:
            return ev
    return None

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _code_hex(code: int) -> str:
    """Format an event code as decimal and hex."""
    return f'{code} (0x{code:03X})'


def _wrap(text: str, width: int = 72, indent: int = 13) -> str:
    """Wrap a long description string."""
    if not text:
        return ''
    words = text.split()
    lines = []
    current = ''
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = ' ' * indent + word
        else:
            current = (current + ' ' + word).lstrip() if not current else current + ' ' + word
    if current:
        lines.append(current)
    return '\n'.join(lines)

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list_cpus(pattern: str | None, meta: dict) -> int:
    """List all CPUs with event counts, optionally filtered by pattern."""
    cpus = meta.get('cpus', {})

    if pattern:
        pat = _normalise_slug(pattern)
        entries = [(s, info) for s, info in sorted(cpus.items()) if pat in s]
        if not entries:
            # Try matching against cpu_name
            pat_lower = pattern.lower()
            entries = [(s, info) for s, info in sorted(cpus.items())
                       if pat_lower in info.get('cpu_name', '').lower()]
        if not entries:
            print(f"No CPUs matching '{pattern}'.", file=sys.stderr)
            return 1
    else:
        entries = sorted(cpus.items())

    max_slug = max(len(s) for s, _ in entries) if entries else 8
    max_cpu  = max(len(i.get('cpu_name', '')) for _, i in entries) if entries else 12

    print(f"  {'CPU Slug':{max_slug}}  {'CPU Name':{max_cpu}}  {'Arch':<12}  {'PMU Arch':<9}  Events")
    print(f"  {'-'*max_slug}  {'-'*max_cpu}  {'-'*12}  {'-'*9}  ------")
    for slug, info in entries:
        arch = info.get('architecture', '')
        pmu  = info.get('pmu_architecture', '')
        cnt  = info.get('event_count', 0)
        cpu  = info.get('cpu_name', '')
        print(f"  {slug:{max_slug}}  {cpu:{max_cpu}}  {arch:<12}  {pmu:<9}  {cnt}")

    print(f"\n({len(entries)} CPU(s))")
    return 0


def cmd_cpu_events(cpu_data: dict) -> int:
    """Display all events for a CPU with codes and truncated descriptions."""
    print(f"CPU          : {cpu_data['cpu']}")
    print(f"Slug         : {cpu_data['cpu_slug']}")
    print(f"Architecture : {cpu_data['architecture']}")
    print(f"PMU arch     : {cpu_data['pmu_architecture']}")
    print(f"Counters     : {cpu_data['counters']}")
    print(f"Events       : {cpu_data['event_count']}")
    print()

    events = cpu_data.get('events', [])
    if not events:
        print('No events found.')
        return 0

    max_name = max(len(e['name']) for e in events)
    print(f"  {'Name':{max_name}}  {'Code':10}  {'Type':<5}  {'Arch':4}  Description")
    print(f"  {'-'*max_name}  {'-'*10}  {'-'*5}  {'-'*4}  -----------")
    for ev in events:
        code = _code_hex(ev['code'])
        typ  = ev.get('type', '')[:5]
        arch = 'Y' if ev.get('architectural') else ''
        desc = (ev.get('description', '') or '')
        # Truncate description
        if len(desc) > 60:
            desc = desc[:57] + '...'
        print(f"  {ev['name']:{max_name}}  {code:10}  {typ:<5}  {arch:4}  {desc}")

    return 0


def cmd_event_detail(cpu_data: dict, event_name: str) -> int:
    """Display full detail for a single named event."""
    events = cpu_data.get('events', [])
    ev = resolve_event(events, event_name)
    if ev is None:
        # Suggest similar event names
        upper = event_name.upper()
        suggestions = [e['name'] for e in events if upper[:8] in e['name'].upper()][:5]
        print(f"Event '{event_name}' not found for {cpu_data['cpu']}.", file=sys.stderr)
        if suggestions:
            print(f"Similar events: {', '.join(suggestions)}", file=sys.stderr)
        return 1

    print(f"CPU          : {cpu_data['cpu']}")
    print(f"Event        : {ev['name']}")
    print(f"Code         : {_code_hex(ev['code'])}")
    print(f"Type         : {ev.get('type', '?')}")
    if ev.get('subtype'):
        print(f"Subtype      : {ev['subtype']}")
    if ev.get('component'):
        print(f"Component    : {ev['component']}")
    print(f"Architectural: {'Yes' if ev.get('architectural') else 'No'}")
    if ev.get('impdef'):
        print(f"Impl-defined : Yes")

    desc = ev.get('description', '')
    if desc:
        print()
        print(f"Description  : {_wrap(desc)}")

    return 0


def cmd_search(pattern: str, flat: dict) -> int:
    """Cross-CPU search for events matching a name pattern."""
    upper = pattern.upper()
    events_index = flat.get('events', {})

    # Find matching event names
    matches = {name: entries
               for name, entries in events_index.items()
               if upper in name.upper()}

    if not matches:
        print(f"No events matching '{pattern}' found.", file=sys.stderr)
        return 1

    # Sort by name
    for event_name in sorted(matches.keys()):
        entries = matches[event_name]
        arch_marker = ' [architectural]' if any(e.get('architectural') for e in entries) else ''
        print(f"\nEvent: {event_name}{arch_marker}")
        print(f"  Found in {len(entries)} CPU(s):")

        max_slug = max(len(e['cpu_slug']) for e in entries) if entries else 8
        max_cpu  = max(len(e['cpu_name']) for e in entries) if entries else 12
        for e in sorted(entries, key=lambda x: x['cpu_slug']):
            code = _code_hex(e['code'])
            print(f"    {e['cpu_slug']:{max_slug}}  ({e['cpu_name']:{max_cpu}})  code={code}")

        # Show the description (use the first entry; descriptions should be consistent)
        desc = entries[0].get('description', '')
        if desc:
            print(f"  Description: {_wrap(desc, width=72, indent=15)}")

    total_cpus = sum(len(entries) for entries in matches.values())
    print(f"\n({len(matches)} event name(s), {total_cpus} CPU occurrence(s))")
    return 0

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Query ARM PMU event codes and descriptions from the PMU cache.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  query_pmu.py cortex-a710
  query_pmu.py cortex-a710 CPU_CYCLES
  query_pmu.py cortex-a710 L1D_CACHE_REFILL
  query_pmu.py --search L1D_CACHE
  query_pmu.py --search CYCLE
  query_pmu.py --list
  query_pmu.py --list neoverse
  query_pmu.py --list cortex-a7
""",
    )
    parser.add_argument('cpu',   nargs='?', help='CPU slug or name (e.g. cortex-a710, neoverse-n1)')
    parser.add_argument('event', nargs='?', help='Event name (e.g. CPU_CYCLES, L1D_CACHE_REFILL)')
    parser.add_argument('--search', metavar='PATTERN', help='Cross-CPU event name search')
    parser.add_argument('--list',   metavar='PATTERN', nargs='?', const='',
                        help='List all CPUs (optionally filtered by pattern)')
    args = parser.parse_args()

    meta = load_meta()

    if args.list is not None:
        return cmd_list_cpus(args.list if args.list else None, meta)

    if args.search:
        flat = load_flat()
        return cmd_search(args.search, flat)

    if not args.cpu:
        parser.print_help()
        return 0

    slug = resolve_cpu(args.cpu, meta)
    if slug is None:
        normalized = args.cpu.lower()
        all_slugs = sorted(meta.get('cpus', {}).keys())
        suggestions = [s for s in all_slugs if normalized[:4] in s][:5]
        print(f"CPU '{args.cpu}' not found in PMU cache.", file=sys.stderr)
        if suggestions:
            print(f"Similar CPUs: {', '.join(suggestions)}", file=sys.stderr)
        else:
            print(f"Use --list to see all available CPUs.", file=sys.stderr)
        return 1

    cpu_data = load_cpu(slug)

    if args.event:
        return cmd_event_detail(cpu_data, args.event)

    return cmd_cpu_events(cpu_data)


if __name__ == '__main__':
    sys.exit(main())
