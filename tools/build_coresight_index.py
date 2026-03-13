#!/usr/bin/env python3
"""
build_coresight_index.py — Cache builder for CoreSight component register data.

Reads coresight/CoreSight.json and writes per-component cache files to cache/coresight/:
  cache/coresight/ETM.json       — all ETM (Embedded Trace Macrocell) registers
  cache/coresight/CTI.json       — all CTI (Cross-Trigger Interface) registers
  cache/coresight/STM.json       — all STM (System Trace Macrocell) registers
  cache/coresight/ITM.json       — all ITM (Instrumentation Trace Macrocell) registers
  cache/coresight/ID_BLOCK.json  — common identification block registers
  cache/coresight/cs_meta.json   — name-to-component lookup index and field index

Also updates cache/manifest.json with the SHA-256 of coresight/CoreSight.json.

Usage:
    python tools/build_coresight_index.py

Environment:
    ARM_MRS_CACHE_DIR      Override cache output directory (default: <repo_root>/cache)
    CORESIGHT_SRC_DIR      Override coresight/ source directory (default: <repo_root>/coresight)

Source files:
    coresight/CoreSight.json

Output:
    cache/coresight/ETM.json
    cache/coresight/CTI.json
    cache/coresight/STM.json
    cache/coresight/ITM.json
    cache/coresight/ID_BLOCK.json
    cache/coresight/cs_meta.json
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

SCRIPT_DIR      = Path(__file__).parent.resolve()
REPO_ROOT       = SCRIPT_DIR.parent
CACHE_DIR       = Path(os.environ.get('ARM_MRS_CACHE_DIR',   str(REPO_ROOT / 'cache')))
CORESIGHT_DIR   = Path(os.environ.get('CORESIGHT_SRC_DIR',   str(REPO_ROOT / 'coresight')))

CORESIGHT_JSON  = CORESIGHT_DIR / 'CoreSight.json'
CS_CACHE        = CACHE_DIR / 'coresight'

COMPONENT_FILES = {
    'ETM':      CS_CACHE / 'ETM.json',
    'CTI':      CS_CACHE / 'CTI.json',
    'STM':      CS_CACHE / 'STM.json',
    'ITM':      CS_CACHE / 'ITM.json',
    'ID_BLOCK': CS_CACHE / 'ID_BLOCK.json',
}
META_FILE = CS_CACHE / 'cs_meta.json'

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

def build_component_cache(registers: list, src_meta: dict) -> dict:
    """
    Partition registers by component and build per-component cache dicts.

    Returns a dict: component_name -> {meta: ..., registers: [...]}
    """
    components: dict = {c: {'meta': {}, 'registers': []} for c in COMPONENT_FILES}

    for reg in registers:
        comp = reg.get('component')
        if comp not in components:
            log(f'WARNING: unknown component "{comp}" for register {reg.get("name")} — skipping')
            continue
        components[comp]['registers'].append(reg)

    # Embed source metadata in each component cache
    for comp, content in components.items():
        content['meta'] = {
            'component':    comp,
            'spec':         src_meta.get('source', ''),
            'spec_version': src_meta.get('spec_version', ''),
            'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'count':        len(content['registers']),
        }

    return components


def build_meta_index(registers: list) -> dict:
    """
    Build cs_meta.json: a name-to-component lookup, field name index.

    The name_index maps register names (and normalised forms for parameterized registers)
    to their component and title.

    The field_index maps field names to the set of register names that contain them,
    enabling cross-register field searches (e.g. searching for 'EN' finds TRCPRGCTLR, CTICONTROL).
    """
    name_index: dict = {}
    field_index: dict = {}

    for reg in registers:
        name  = reg.get('name', '')
        comp  = reg.get('component', '')
        title = reg.get('title', '')
        entry = {'component': comp, 'title': title}

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
        'generated_at':   time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'register_count': len(registers),
        'name_index':     name_index,
        'field_index':    field_index,
    }


# ---------------------------------------------------------------------------
# Manifest update
# ---------------------------------------------------------------------------

def update_manifest(cs_hash: str) -> None:
    """Update cache/manifest.json with SHA-256 of coresight/CoreSight.json."""
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
    manifest['sources']['CoreSight.json'] = {
        'sha256': cs_hash,
        'path':   str(CORESIGHT_JSON),
    }
    manifest['coresight_built_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    write_json(manifest_path, manifest)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log('AArch64 Agent Skills — CoreSight Cache Builder')
    log(f'Source dir : {CORESIGHT_DIR}')
    log(f'Cache dir  : {CACHE_DIR}')
    log()

    # Check source file exists
    if not CORESIGHT_JSON.exists():
        log(f'ERROR: Source file not found: {CORESIGHT_JSON}')
        log('Ensure coresight/CoreSight.json is present.')
        sys.exit(1)

    # Step 1: Compute hash
    log('Step 1/4: Computing source file hash...')
    t0 = time.time()
    print(f'  SHA-256 CoreSight.json ...', end=' ', flush=True)
    cs_hash = sha256_file(CORESIGHT_JSON)
    print(f'done ({time.time() - t0:.2f}s)')

    # Step 2: Load source data
    log('\nStep 2/4: Loading CoreSight.json...')
    t0 = time.time()
    with open(CORESIGHT_JSON) as f:
        cs_data = json.load(f)
    registers = cs_data.get('registers', [])
    src_meta  = cs_data.get('_meta', {})
    log(f'  Loaded {len(registers)} registers ({time.time() - t0:.2f}s)')

    # Step 3: Build and write per-component cache files
    log('\nStep 3/4: Building per-component cache files...')
    t0 = time.time()
    components = build_component_cache(registers, src_meta)

    for comp, content in components.items():
        out_path = COMPONENT_FILES[comp]
        write_json(out_path, content)
        log(f'  Written: {out_path.relative_to(REPO_ROOT)}  ({content["meta"]["count"]} registers)')

    # Build and write cs_meta.json
    meta = build_meta_index(registers)
    write_json(META_FILE, meta)
    log(f'  Written: {META_FILE.relative_to(REPO_ROOT)}  ({len(meta["name_index"])} index entries)')
    log(f'  ({time.time() - t0:.2f}s)')

    # Step 4: Update manifest
    log('\nStep 4/4: Updating manifest...')
    update_manifest(cs_hash)
    log(f'  cache/manifest.json updated with CoreSight.json SHA-256.')

    log()
    log('Done. CoreSight cache is ready.')
    counts = '  '.join(
        f'{c} ({components[c]["meta"]["count"]} regs)'
        for c in ('ETM', 'CTI', 'STM', 'ITM', 'ID_BLOCK')
    )
    log(f'  Components: {counts}')


if __name__ == '__main__':
    main()
