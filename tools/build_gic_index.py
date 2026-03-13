#!/usr/bin/env python3
"""
build_gic_index.py — Cache builder for GIC (Generic Interrupt Controller) data.

Reads gic/GIC.json and writes per-block cache files to cache/gic/:
  cache/gic/GICD.json      — all GICD (Distributor) registers
  cache/gic/GICR.json      — all GICR (Redistributor) registers
  cache/gic/GITS.json      — all GITS (Interrupt Translation Service) registers
  cache/gic/gic_meta.json  — name-to-block lookup index and ICC cross-reference list

Also updates cache/manifest.json with the SHA-256 of gic/GIC.json.

Usage:
    python tools/build_gic_index.py

Environment:
    ARM_MRS_CACHE_DIR  Override cache output directory (default: <repo_root>/cache)
    GIC_SRC_DIR        Override gic/ source directory (default: <repo_root>/gic)

Source files:
    gic/GIC.json

Output:
    cache/gic/GICD.json
    cache/gic/GICR.json
    cache/gic/GITS.json
    cache/gic/gic_meta.json
    cache/manifest.json  (updated)

Requirements:
    Python 3.8+, stdlib only.
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT  = SCRIPT_DIR.parent
CACHE_DIR  = Path(os.environ.get('ARM_MRS_CACHE_DIR', str(REPO_ROOT / 'cache')))
GIC_DIR    = Path(os.environ.get('GIC_SRC_DIR',        str(REPO_ROOT / 'gic')))

GIC_JSON   = GIC_DIR / 'GIC.json'
GIC_CACHE  = CACHE_DIR / 'gic'

BLOCK_FILES = {
    'GICD': GIC_CACHE / 'GICD.json',
    'GICR': GIC_CACHE / 'GICR.json',
    'GITS': GIC_CACHE / 'GITS.json',
}
META_FILE = GIC_CACHE / 'gic_meta.json'

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


# ---------------------------------------------------------------------------
# Cache building
# ---------------------------------------------------------------------------

def build_block_cache(registers: list, src_meta: dict) -> dict:
    """
    Partition registers by block and build per-block cache dicts.

    Returns a dict: block_name -> {meta: ..., registers: [...]}
    """
    blocks: dict = {b: {'meta': {}, 'registers': []} for b in BLOCK_FILES}

    for reg in registers:
        block = reg.get('block')
        if block not in blocks:
            log(f'WARNING: unknown block "{block}" for register {reg.get("name")} — skipping')
            continue
        blocks[block]['registers'].append(reg)

    # Embed source metadata in each block cache
    for block, content in blocks.items():
        content['meta'] = {
            'block':      block,
            'spec':       src_meta.get('source', ''),
            'spec_version': src_meta.get('spec_version', ''),
            'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'count':      len(content['registers']),
        }

    return blocks


def build_meta_index(registers: list, icc_xrefs: list) -> dict:
    """
    Build gic_meta.json: a name-to-block lookup, field name index, and ICC cross-reference list.

    The name_index maps register names (and normalised forms for parameterized registers)
    to their block and title.

    The field_index maps field names to the set of register names that contain them,
    enabling cross-register field searches (e.g. searching for 'EnableGrp1' finds GICD_CTLR).
    """
    name_index: dict = {}
    field_index: dict = {}

    for reg in registers:
        name  = reg.get('name', '')
        block = reg.get('block', '')
        title = reg.get('title', '')
        entry = {'block': block, 'title': title}

        # Store under the canonical name (may contain <n>)
        name_index[name] = entry

        # Also store a normalised form (replace <n> with literal n for searching)
        norm = name.replace('<n>', 'n')
        if norm != name:
            name_index[norm] = entry

        # Build field name index
        for fs in reg.get('fieldsets', []):
            for field in fs.get('fields', []):
                fname = field.get('name', '')
                if not fname or fname.upper().startswith('RES0') or fname.upper().startswith('RES1'):
                    continue
                if fname not in field_index:
                    field_index[fname] = []
                if name not in field_index[fname]:
                    field_index[fname].append(name)

    return {
        'generated_at':         time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'register_count':       len(registers),
        'name_index':           name_index,
        'field_index':          field_index,
        'icc_system_registers': icc_xrefs,
    }


# ---------------------------------------------------------------------------
# Manifest update
# ---------------------------------------------------------------------------

def update_manifest(gic_hash: str) -> None:
    """Update cache/manifest.json with SHA-256 of gic/GIC.json."""
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
    manifest['sources']['GIC.json'] = {
        'sha256': gic_hash,
        'path':   str(GIC_JSON),
    }
    manifest['gic_built_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    write_json(manifest_path, manifest)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log('AArch64 Agent Skills — GIC Cache Builder')
    log(f'Source dir : {GIC_DIR}')
    log(f'Cache dir  : {CACHE_DIR}')
    log()

    # Check source file exists
    if not GIC_JSON.exists():
        log(f'ERROR: Source file not found: {GIC_JSON}')
        log('Run: python tools/fetch_gic.py  or  ensure gic/GIC.json is present.')
        sys.exit(1)

    # Step 1: Compute hash
    log('Step 1/4: Computing source file hash...')
    t0 = time.time()
    print(f'  SHA-256 GIC.json ...', end=' ', flush=True)
    gic_hash = sha256_file(GIC_JSON)
    print(f'done ({time.time() - t0:.2f}s)')

    # Step 2: Load source data
    log('\nStep 2/4: Loading GIC.json...')
    t0 = time.time()
    with open(GIC_JSON) as f:
        gic_data = json.load(f)
    registers  = gic_data.get('registers', [])
    icc_xrefs  = gic_data.get('icc_system_registers', [])
    src_meta   = gic_data.get('_meta', {})
    log(f'  Loaded {len(registers)} registers, {len(icc_xrefs)} ICC cross-references ({time.time() - t0:.2f}s)')

    # Step 3: Build and write per-block cache files
    log('\nStep 3/4: Building per-block cache files...')
    t0 = time.time()
    blocks = build_block_cache(registers, src_meta)

    for block, content in blocks.items():
        out_path = BLOCK_FILES[block]
        write_json(out_path, content)
        log(f'  Written: {out_path.relative_to(REPO_ROOT)}  ({content["meta"]["count"]} registers)')

    # Build and write gic_meta.json
    meta = build_meta_index(registers, icc_xrefs)
    write_json(META_FILE, meta)
    log(f'  Written: {META_FILE.relative_to(REPO_ROOT)}  ({len(meta["name_index"])} index entries)')
    log(f'  ({time.time() - t0:.2f}s)')

    # Step 4: Update manifest
    log('\nStep 4/4: Updating manifest...')
    update_manifest(gic_hash)
    log(f'  cache/manifest.json updated with GIC.json SHA-256.')

    log()
    log('Done. GIC cache is ready.')
    log(f'  Blocks: GICD ({blocks["GICD"]["meta"]["count"]} regs)  '
        f'GICR ({blocks["GICR"]["meta"]["count"]} regs)  '
        f'GITS ({blocks["GITS"]["meta"]["count"]} regs)')


if __name__ == '__main__':
    main()
