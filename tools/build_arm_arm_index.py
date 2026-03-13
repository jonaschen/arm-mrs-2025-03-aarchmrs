#!/usr/bin/env python3
"""
build_arm_arm_index.py — Cache builder for T32 and A32 instruction data.

Reads hand-curated (or licensed) T32/A32 source JSON files from arm-arm/ and
writes per-operation cache files to cache/arm_arm/t32_operations/ and
cache/arm_arm/a32_operations/.  Also records source-file hashes in
cache/manifest.json (updating it if the A64 cache already exists, or creating
a standalone arm_arm manifest otherwise).

Usage:
    python tools/build_arm_arm_index.py

Environment:
    ARM_MRS_CACHE_DIR  Override cache output directory (default: <repo_root>/cache)
    ARM_ARM_SRC_DIR    Override arm-arm/ source directory (default: <repo_root>/arm-arm)

Source files:
    arm-arm/T32Instructions.json
    arm-arm/A32Instructions.json

Output:
    cache/arm_arm/t32_operations/<operation_id>.json  (one file per T32 operation)
    cache/arm_arm/a32_operations/<operation_id>.json  (one file per A32 operation)
    cache/manifest.json                               (updated with T32/A32 source hashes)

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

SCRIPT_DIR  = Path(__file__).parent.resolve()
REPO_ROOT   = SCRIPT_DIR.parent
CACHE_DIR   = Path(os.environ.get('ARM_MRS_CACHE_DIR', str(REPO_ROOT / 'cache')))
ARM_ARM_DIR = Path(os.environ.get('ARM_ARM_SRC_DIR',   str(REPO_ROOT / 'arm-arm')))

T32_SRC  = ARM_ARM_DIR / 'T32Instructions.json'
A32_SRC  = ARM_ARM_DIR / 'A32Instructions.json'

ARM_ARM_CACHE = CACHE_DIR / 'arm_arm'
T32_OP_DIR    = ARM_ARM_CACHE / 't32_operations'
A32_OP_DIR    = ARM_ARM_CACHE / 'a32_operations'

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
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

def build_isa_cache(src_path: Path, op_dir: Path, isa: str) -> int:
    """
    Read a source JSON file (with top-level "operations" array) and write
    one cache file per operation_id to op_dir.  Returns the number of
    operations written.
    """
    with open(src_path) as f:
        data = json.load(f)

    operations = data.get('operations', [])
    if not isinstance(operations, list):
        log(f'ERROR: {src_path.name}: "operations" must be an array')
        sys.exit(1)

    op_dir.mkdir(parents=True, exist_ok=True)

    for i, op in enumerate(operations):
        op_id = op.get('operation_id')
        if not op_id:
            log(f'WARNING: skipping operation at index {i} with no operation_id in {src_path.name}')
            continue
        cache_entry = {
            'operation_id':         op_id,
            'isa':                  isa,
            'title':                op.get('title'),
            'brief':                op.get('brief'),
            'description':          op.get('description'),
            'decode':               op.get('decode'),
            'operation':            op.get('operation'),
            'instruction_variants': op.get('instruction_variants') or [],
        }
        write_json(op_dir / f'{op_id}.json', cache_entry)

    return len(operations)


# ---------------------------------------------------------------------------
# Manifest update
# ---------------------------------------------------------------------------

def update_manifest(t32_hash: str, a32_hash: str) -> None:
    """
    Update cache/manifest.json with T32/A32 source hashes.
    If the main manifest exists, merge in the new entries.
    Otherwise create a standalone arm_arm manifest.
    """
    manifest_path = CACHE_DIR / 'manifest.json'
    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
        except Exception:
            manifest = {}
    else:
        manifest = {
            'built_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'cache_dir': str(CACHE_DIR),
            'sources': {},
        }

    manifest.setdefault('sources', {})
    manifest['sources']['T32Instructions.json'] = {
        'sha256': t32_hash,
        'path':   str(T32_SRC),
    }
    manifest['sources']['A32Instructions.json'] = {
        'sha256': a32_hash,
        'path':   str(A32_SRC),
    }
    manifest['arm_arm_built_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    write_json(manifest_path, manifest)

    # Also write a standalone arm_arm manifest for users who haven't run
    # build_index.py (e.g., using only T32/A32 queries)
    arm_arm_manifest = {
        'built_at': manifest['arm_arm_built_at'],
        'cache_dir': str(ARM_ARM_CACHE),
        'sources': {
            'T32Instructions.json': manifest['sources']['T32Instructions.json'],
            'A32Instructions.json': manifest['sources']['A32Instructions.json'],
        },
    }
    write_json(ARM_ARM_CACHE / 'manifest.json', arm_arm_manifest)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log('AArch64 Agent Skills — ARM ARM Cache Builder (T32/A32)')
    log(f'Source dir : {ARM_ARM_DIR}')
    log(f'Cache dir  : {CACHE_DIR}')
    log()

    # Check source files exist
    missing = [p for p in (T32_SRC, A32_SRC) if not p.exists()]
    if missing:
        for p in missing:
            log(f'ERROR: Source file not found: {p}')
        sys.exit(1)

    # Compute hashes
    log('Step 1/3: Computing source file hashes...')
    t0 = time.time()
    print(f'  SHA-256 {T32_SRC.name} ...', end=' ', flush=True)
    t32_hash = sha256_file(T32_SRC)
    print(f'done ({time.time() - t0:.1f}s)')

    t0 = time.time()
    print(f'  SHA-256 {A32_SRC.name} ...', end=' ', flush=True)
    a32_hash = sha256_file(A32_SRC)
    print(f'done ({time.time() - t0:.1f}s)')

    # Build T32 cache
    log('\nStep 2/3: Building T32 operations cache...')
    t0 = time.time()
    n_t32 = build_isa_cache(T32_SRC, T32_OP_DIR, 'T32')
    log(f'  Written: cache/arm_arm/t32_operations/  ({n_t32} operations, {time.time() - t0:.1f}s)')

    # Build A32 cache
    log('\nStep 3/3: Building A32 operations cache...')
    t0 = time.time()
    n_a32 = build_isa_cache(A32_SRC, A32_OP_DIR, 'A32')
    log(f'  Written: cache/arm_arm/a32_operations/  ({n_a32} operations, {time.time() - t0:.1f}s)')

    # Update manifest
    update_manifest(t32_hash, a32_hash)
    log('\nmanifest.json updated.')
    log('Done. ARM ARM cache is ready.')


if __name__ == '__main__':
    main()
