#!/usr/bin/env python3
"""
build_pmu_index.py — Cache builder for ARM PMU event data.

Reads all pmu/*.json files from the repository's pmu/ directory (sourced from
ARM-software/data, Apache 2.0) and writes per-CPU cache files to cache/pmu/:

  cache/pmu/<cpu-slug>.json      — one file per CPU with all events
  cache/pmu_meta.json            — cpu_slug → {cpu_name, file, event_count, architecture}
  cache/pmu_events_flat.json     — flat cross-CPU event search index

Also updates cache/manifest.json with SHA-256 hashes of all pmu/*.json source files.

Usage:
    python tools/build_pmu_index.py

Environment:
    ARM_MRS_CACHE_DIR  Override cache output directory (default: <repo_root>/cache)
    PMU_SRC_DIR        Override pmu/ source directory (default: <repo_root>/pmu)

Source files:
    pmu/*.json  (one per CPU, ARM-software/data format)

Output:
    cache/pmu/<cpu-slug>.json  (one per CPU)
    cache/pmu_meta.json
    cache/pmu_events_flat.json
    cache/manifest.json  (updated)

Requirements:
    Python 3.8+, stdlib only.
"""

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT  = SCRIPT_DIR.parent
CACHE_DIR  = Path(os.environ.get('ARM_MRS_CACHE_DIR', str(REPO_ROOT / 'cache')))
PMU_DIR    = Path(os.environ.get('PMU_SRC_DIR',        str(REPO_ROOT / 'pmu')))

PMU_CACHE  = CACHE_DIR / 'pmu'
META_FILE  = CACHE_DIR / 'pmu_meta.json'
FLAT_FILE  = CACHE_DIR / 'pmu_events_flat.json'

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, separators=(',', ':'))


def log(msg: str = '') -> None:
    print(msg, flush=True)


def cpu_slug(cpu_name: str) -> str:
    """
    Convert a CPU name to a filesystem-safe slug.
    e.g. 'Cortex-A710' → 'cortex-a710', 'Neoverse N1' → 'neoverse-n1'
    """
    slug = cpu_name.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug


# ---------------------------------------------------------------------------
# Cache building
# ---------------------------------------------------------------------------

def build_cpu_cache(src_data: dict, src_file: str) -> dict:
    """
    Build a cache entry for a single CPU.

    Returns a dict suitable for writing to cache/pmu/<cpu-slug>.json.
    """
    cpu_name     = src_data.get('cpu', src_file)
    architecture = src_data.get('architecture', '')
    pmu_arch     = src_data.get('pmu_architecture', '')
    counters     = src_data.get('counters', 0)
    cpuid        = src_data.get('cpuid', '')
    events       = src_data.get('events', [])

    # Normalise events: ensure code is always present, sort by code
    normalised = []
    for ev in events:
        entry = {
            'name':           ev.get('name', ''),
            'code':           ev.get('code', 0),
            'description':    ev.get('description', ''),
            'architectural':  ev.get('architectural', False),
            'type':           ev.get('type', ''),
        }
        # Optional fields
        if ev.get('subtype'):
            entry['subtype'] = ev['subtype']
        if ev.get('component'):
            entry['component'] = ev['component']
        if ev.get('impdef'):
            entry['impdef'] = ev['impdef']
        normalised.append(entry)

    # Sort events by code
    normalised.sort(key=lambda e: e['code'])

    return {
        'cpu':              cpu_name,
        'cpu_slug':         cpu_slug(cpu_name),
        'cpuid':            cpuid,
        'architecture':     architecture,
        'pmu_architecture': pmu_arch,
        'counters':         counters,
        'generated_at':     time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'source_file':      src_file,
        'event_count':      len(normalised),
        'events':           normalised,
    }


def build_meta(cpu_caches: dict) -> dict:
    """
    Build pmu_meta.json: a cpu_slug → metadata lookup for all CPUs.
    """
    meta: dict = {
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'cpu_count':    len(cpu_caches),
        'cpus':         {},
    }
    for slug, cache in sorted(cpu_caches.items()):
        meta['cpus'][slug] = {
            'cpu_name':         cache['cpu'],
            'cpuid':            cache['cpuid'],
            'architecture':     cache['architecture'],
            'pmu_architecture': cache['pmu_architecture'],
            'counters':         cache['counters'],
            'event_count':      cache['event_count'],
            'file':             f'pmu/{slug}.json',
        }
    return meta


def build_flat_index(cpu_caches: dict) -> dict:
    """
    Build pmu_events_flat.json: a cross-CPU event name → list of {cpu_slug, code, description}.

    This enables efficient cross-CPU searches for event names like L1D_CACHE_REFILL.
    """
    # event_name → list of {cpu_slug, cpu_name, code, description, architectural}
    event_index: dict = {}

    for slug, cache in sorted(cpu_caches.items()):
        cpu_name = cache['cpu']
        for ev in cache['events']:
            name = ev['name']
            if name not in event_index:
                event_index[name] = []
            event_index[name].append({
                'cpu_slug':     slug,
                'cpu_name':     cpu_name,
                'code':         ev['code'],
                'description':  ev['description'],
                'architectural': ev.get('architectural', False),
                'type':         ev.get('type', ''),
            })

    return {
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'event_count':  len(event_index),
        'events':       event_index,
    }


# ---------------------------------------------------------------------------
# Manifest update
# ---------------------------------------------------------------------------

def update_manifest(source_hashes: dict) -> None:
    """Update cache/manifest.json with SHA-256 hashes of all pmu/*.json source files."""
    manifest_path = CACHE_DIR / 'manifest.json'
    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
        except Exception:
            manifest = {}
    else:
        manifest = {
            'built_at':  time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'cache_dir': str(CACHE_DIR),
            'sources':   {},
        }

    manifest.setdefault('sources', {})
    for fname, info in source_hashes.items():
        manifest['sources'][fname] = info

    manifest['pmu_built_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    write_json(manifest_path, manifest)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log('AArch64 Agent Skills — PMU Event Cache Builder')
    log(f'Source dir : {PMU_DIR}')
    log(f'Cache dir  : {CACHE_DIR}')
    log()

    # Check source directory exists
    if not PMU_DIR.exists():
        log(f'ERROR: PMU source directory not found: {PMU_DIR}')
        log('Ensure pmu/ directory exists with CPU JSON files from ARM-software/data.')
        sys.exit(1)

    # Collect all JSON source files (skip pmu-schema.json)
    src_files = sorted([
        p for p in PMU_DIR.glob('*.json')
        if p.name != 'pmu-schema.json'
    ])

    if not src_files:
        log(f'ERROR: No CPU JSON files found in {PMU_DIR}')
        sys.exit(1)

    log(f'Found {len(src_files)} CPU source file(s).')

    # Step 1: Compute hashes
    log('\nStep 1/4: Computing source file hashes...')
    t0 = time.time()
    source_hashes: dict = {}
    for src in src_files:
        h = sha256_file(src)
        rel = f'pmu/{src.name}'
        source_hashes[rel] = {'sha256': h, 'path': str(src)}
        print(f'  SHA-256 {src.name} ... {h[:12]}...')
    log(f'  ({time.time() - t0:.2f}s)')

    # Step 2: Load and normalise all CPU data
    log('\nStep 2/4: Loading and normalising CPU event data...')
    t0 = time.time()
    cpu_caches: dict = {}
    errors: list = []

    for src in src_files:
        try:
            with open(src) as f:
                src_data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            log(f'  WARNING: Cannot read/parse {src.name}: {exc}')
            errors.append(src.name)
            continue

        if src_data.get('_type') != 'Events':
            log(f'  WARNING: {src.name} does not have _type=Events — skipping')
            continue

        cache = build_cpu_cache(src_data, src.name)
        slug  = cache['cpu_slug']

        if not slug:
            log(f'  WARNING: Empty CPU slug for {src.name} — skipping')
            continue

        cpu_caches[slug] = cache
        log(f'  {slug:<25} {cache["event_count"]:>4} events  (cpu={cache["cpu"]})')

    log(f'  Loaded {len(cpu_caches)} CPU(s) ({time.time() - t0:.2f}s)')
    if errors:
        log(f'  Skipped {len(errors)} file(s) with errors: {", ".join(errors)}')

    if not cpu_caches:
        log('ERROR: No valid CPU data found.')
        sys.exit(1)

    # Step 3: Write cache files
    log('\nStep 3/4: Writing cache files...')
    t0 = time.time()

    # Per-CPU cache files
    for slug, cache in sorted(cpu_caches.items()):
        out_path = PMU_CACHE / f'{slug}.json'
        write_json(out_path, cache)
    log(f'  Written {len(cpu_caches)} per-CPU cache file(s) to {PMU_CACHE.relative_to(REPO_ROOT)}/')

    # pmu_meta.json
    meta = build_meta(cpu_caches)
    write_json(META_FILE, meta)
    log(f'  Written: {META_FILE.relative_to(REPO_ROOT)}  ({meta["cpu_count"]} CPUs)')

    # pmu_events_flat.json
    flat = build_flat_index(cpu_caches)
    write_json(FLAT_FILE, flat)
    log(f'  Written: {FLAT_FILE.relative_to(REPO_ROOT)}  ({flat["event_count"]} unique event names)')
    log(f'  ({time.time() - t0:.2f}s)')

    # Step 4: Update manifest
    log('\nStep 4/4: Updating manifest...')
    update_manifest(source_hashes)
    log('  cache/manifest.json updated with PMU source file SHA-256 hashes.')

    log()
    log('Done. PMU cache is ready.')

    # Summary
    total_events = sum(c['event_count'] for c in cpu_caches.values())
    log(f'  CPUs      : {len(cpu_caches)}')
    log(f'  Events    : {total_events} (total across all CPUs)')
    log(f'  Unique    : {flat["event_count"]} (unique event names)')


if __name__ == '__main__':
    main()
