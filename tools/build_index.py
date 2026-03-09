#!/usr/bin/env python3
"""
build_index.py — One-time cache builder for the AArch64 agent skills.

Reads the three MRS source files and writes the cache/ directory.
Must be run before any query script or skill can be used.

Usage:
    python tools/build_index.py

Environment:
    ARM_MRS_CACHE_DIR  Override cache output directory (default: <repo_root>/cache)

Requirements:
    Python 3.8+, stdlib only. ~300-600 MB RAM during Instructions.json parsing.
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

FEATURES_PATH     = REPO_ROOT / 'Features.json'
INSTRUCTIONS_PATH = REPO_ROOT / 'Instructions.json'
REGISTERS_PATH    = REPO_ROOT / 'Registers.json'

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VERSION_ORDER = [
    'v8Ap0', 'v8Ap1', 'v8Ap2', 'v8Ap3', 'v8Ap4', 'v8Ap5',
    'v8Ap6', 'v8Ap7', 'v8Ap8', 'v8Ap9',
    'v9Ap0', 'v9Ap1', 'v9Ap2', 'v9Ap3', 'v9Ap4', 'v9Ap5', 'v9Ap6',
]
VERSION_SET   = set(VERSION_ORDER)
VERSION_INDEX = {v: i for i, v in enumerate(VERSION_ORDER)}

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


def progress(i: int, total: int, label: str = '') -> None:
    if total == 0:
        return
    if i % 250 == 0 or i == total - 1:
        pct = (i + 1) * 100 // total
        print(f'\r  {label}: {i + 1}/{total} ({pct}%)', end='', flush=True)
    if i == total - 1:
        print()


def ensure_gitignore(cache_dir: Path, repo_root: Path) -> None:
    """Add cache/ to .gitignore if not already present."""
    try:
        rel = cache_dir.relative_to(repo_root)
    except ValueError:
        return  # cache is outside repo, nothing to do
    entry = str(rel) + '/'
    gitignore = repo_root / '.gitignore'
    if gitignore.exists():
        if entry in gitignore.read_text():
            return
        with open(gitignore, 'a') as f:
            f.write(f'\n# AArch64 agent skills cache (generated)\n{entry}\n')
        log(f'  Updated .gitignore: added {entry}')
    else:
        gitignore.write_text(f'# AArch64 agent skills cache (generated)\n{entry}\n')
        log(f'  Created .gitignore with {entry}')


def check_sources() -> None:
    for path in [FEATURES_PATH, INSTRUCTIONS_PATH, REGISTERS_PATH]:
        if not path.exists():
            log(f'ERROR: Source file not found: {path}')
            sys.exit(1)


# ---------------------------------------------------------------------------
# Step 2: Features
# ---------------------------------------------------------------------------

def _collect_version_implications(node, feat_name: str, result: dict) -> None:
    """
    Recursively walk an AST node looking for BinaryOp patterns:
      FEAT_X --> vNApM  or  vNApM --> FEAT_X
    Record the minimum (earliest) version found for feat_name.
    """
    if not isinstance(node, dict):
        return
    if node.get('_type') == 'AST.BinaryOp' and node.get('op') == '-->':
        left  = node.get('left',  {})
        right = node.get('right', {})
        lval = left.get('value')  if left.get('_type')  == 'AST.Identifier' else None
        rval = right.get('value') if right.get('_type') == 'AST.Identifier' else None

        candidate = None
        if lval == feat_name and rval in VERSION_SET:
            candidate = rval
        elif rval == feat_name and lval in VERSION_SET:
            candidate = lval

        if candidate is not None:
            existing = result.get(feat_name)
            if existing is None or VERSION_INDEX[candidate] < VERSION_INDEX[existing]:
                result[feat_name] = candidate

    for v in node.values():
        if isinstance(v, dict):
            _collect_version_implications(v, feat_name, result)
        elif isinstance(v, list):
            for item in v:
                _collect_version_implications(item, feat_name, result)


def build_features_cache(data: dict) -> list:
    """
    Produce the features cache list from Features.json data.
    Each entry: {name, type, min_version, constraints}
    """
    top_constraints = data.get('constraints') or []
    parameters      = data.get('parameters', [])
    result = []

    for param in parameters:
        name = param['name']
        found = {}
        for c in (param.get('constraints') or []):
            _collect_version_implications(c, name, found)
        for c in top_constraints:
            _collect_version_implications(c, name, found)
        result.append({
            'name':        name,
            'type':        param.get('_type'),
            'min_version': found.get(name),
            'constraints': param.get('constraints'),
        })

    return result


# ---------------------------------------------------------------------------
# Step 3: Registers
# ---------------------------------------------------------------------------

def _sanitize_reg_filename(name: str) -> str:
    """
    Convert a register name to a safe filename component.
    <param> and any immediately following _ are replaced with _param_,
    so DBGBCR<n>_EL1 → DBGBCR_n_EL1 (not DBGBCR_n__EL1).
    Trailing underscores from bare <n> at end of name are stripped.
    """
    return re.sub(r'<(\w+)>_?', r'_\1_', name).rstrip('_')


def _extract_field(raw_field: dict):
    """
    Normalise a raw Fields.* object. Returns None for unnamed fields
    (Reserved, ImplementationDefined, etc. — no useful bit semantics).
    """
    name = raw_field.get('name')
    if not name:
        return None
    rangeset = raw_field.get('rangeset') or []
    bits = [{'start': r['start'], 'width': r['width']} for r in rangeset]
    values_raw = raw_field.get('values')
    values = None
    if isinstance(values_raw, dict):
        values = [
            {'value': v.get('value'), 'meaning': v.get('meaning')}
            for v in values_raw.get('values', [])
        ]
    return {
        'name':   name,
        'type':   raw_field.get('_type', ''),
        'bits':   bits,
        'values': values,
    }


def _extract_accessor(raw_acc: dict) -> dict:
    return {
        'type':     raw_acc.get('_type', ''),
        'name':     raw_acc.get('name'),
        'encoding': raw_acc.get('encoding'),
        'access':   raw_acc.get('access'),
    }


def _extract_register(raw_reg: dict) -> dict:
    fieldsets_out = []
    for fset in raw_reg.get('fieldsets') or []:
        fields_out = [
            f for f in (_extract_field(rf) for rf in fset.get('values') or [])
            if f is not None
        ]
        fieldsets_out.append({
            'condition': fset.get('condition'),
            'width':     fset.get('width'),
            'fields':    fields_out,
        })
    accessors_out = [_extract_accessor(a) for a in raw_reg.get('accessors') or []]
    return {
        'name':           raw_reg.get('name'),
        'state':          raw_reg.get('state'),
        'condition':      raw_reg.get('condition'),
        'index_variable': raw_reg.get('index_variable'),
        'indexes':        raw_reg.get('indexes'),
        'fieldsets':      fieldsets_out,
        'accessors':      accessors_out,
    }


def build_registers_cache(data: list, reg_dir: Path) -> dict:
    """
    Write one JSON file per register×state.
    Returns the registers_meta dict: original_name -> [{state, cache_key}]
    """
    meta = {}
    total = len(data)
    for i, raw_reg in enumerate(data):
        progress(i, total, 'Registers')
        name      = raw_reg.get('name', '')
        state     = raw_reg.get('state', '')
        safe_name = _sanitize_reg_filename(name)
        cache_key = f'{safe_name}__{state}'

        write_json(reg_dir / f'{cache_key}.json', _extract_register(raw_reg))
        meta.setdefault(name, []).append({'state': state, 'cache_key': cache_key})

    return meta


# ---------------------------------------------------------------------------
# Step 4: Operations / Instructions
# ---------------------------------------------------------------------------

def _collect_instruction_paths(node: dict, path: list, results: list) -> None:
    """
    Recursively walk the instruction tree.
    Appends (leaf_node, full_path_from_root) for each leaf instruction node.
    Leaf = any node that is not InstructionSet or InstructionGroup.
    """
    t = node.get('_type', '')
    current_path = path + [node]
    is_group = 'InstructionSet' in t or 'InstructionGroup' in t
    if not is_group:
        results.append((node, current_path))
    for child in node.get('children') or []:
        _collect_instruction_paths(child, current_path, results)


def _resolve_encoding(path: list) -> list:
    """
    Build the complete resolved encoding for one instruction variant by
    merging fields across all levels of the tree path (bottom-up).

    Two-pass algorithm (see DESIGN.md §3 for full rationale):

    Pass 1 — Named fields (bottom-up, bit-range collision avoidance):
      Walk from leaf to root. For each field that has a name, add it to
      named_fields only if none of its bit positions are already claimed.
      This captures the most specific (deepest) definition for each bit range.

    Pass 2 — Fixed bits (bottom-up, per-bit-position):
      Walk from leaf to root. For each bit position that carries a '0' or '1'
      value, record it only if not yet seen. The leaf's discriminating bits
      are recorded first (deepest = most specific).

    Final construction:
      • For each named field: reconstruct its actual value from fixed_bits.
        All-'x' → kind='operand'; any fixed bit → kind='fixed'.
      • For fixed bits NOT covered by any named field: group into contiguous
        ranges → kind='class' (encoding class identifiers, unnamed in source).

    Fields are sorted MSB first (descending start position).
    """
    named_fields = {}   # start -> {name, start, width}
    named_bits   = set()
    fixed_bits   = {}   # bit_pos -> '0' or '1'

    for node in reversed(path):   # leaf first = deepest
        enc = node.get('encoding') or {}
        for ef in enc.get('values') or []:
            r     = ef.get('range') or {}
            start = r.get('start', 0)
            width = r.get('width', 0)
            name  = ef.get('name')
            val_obj = ef.get('value') or {}
            raw_val = val_obj.get('value', '') if val_obj else ''
            val_str = raw_val.strip("'")

            # Pass 1: named field (no overlap with already-named bits)
            if name:
                field_bits = set(range(start, start + width))
                if not (field_bits & named_bits):
                    named_fields[start] = {'name': name, 'start': start, 'width': width}
                    named_bits |= field_bits

            # Pass 2: fixed bit values, per bit position
            for i, bit_char in enumerate(reversed(val_str)):  # index i = bit offset from LSB
                bit_pos = start + i
                if bit_char in ('0', '1') and bit_pos not in fixed_bits:
                    fixed_bits[bit_pos] = bit_char

    result = []
    covered_bits = set()

    # Build named field entries with reconstructed values
    for start in sorted(named_fields.keys(), reverse=True):
        nf    = named_fields[start]
        width = nf['width']
        covered_bits.update(range(start, start + width))
        # Reconstruct value string, MSB first
        val_chars = [fixed_bits.get(p, 'x') for p in range(start + width - 1, start - 1, -1)]
        val_str   = ''.join(val_chars)
        is_all_x  = all(c == 'x' for c in val_str)
        result.append({
            'start': start,
            'width': width,
            'name':  nf['name'],
            'value': f"'{val_str}'",
            'kind':  'operand' if is_all_x else 'fixed',
        })

    # Build unnamed 'class' fields from uncovered fixed bits
    uncovered = sorted(
        [p for p in fixed_bits if p not in covered_bits],
        reverse=True,
    )
    if uncovered:
        ranges = []
        current = [uncovered[0]]
        for pos in uncovered[1:]:
            if pos == current[-1] - 1:
                current.append(pos)
            else:
                ranges.append(current)
                current = [pos]
        ranges.append(current)

        for bit_range in ranges:
            high  = max(bit_range)
            low   = min(bit_range)
            width = high - low + 1
            val_str = ''.join(fixed_bits[p] for p in range(high, low - 1, -1))
            result.append({
                'start': low,
                'width': width,
                'name':  None,
                'value': f"'{val_str}'",
                'kind':  'class',
            })

    result.sort(key=lambda x: -x['start'])
    return result


def build_operations_cache(data: dict, op_dir: Path) -> None:
    """Write one JSON file per operation_id."""
    operations = data['operations']
    tree_roots = data['instructions']   # list with one InstructionSet entry

    # Collect all leaf instruction paths across all roots
    log('  Collecting instruction tree paths...')
    all_paths = []
    for root in tree_roots:
        _collect_instruction_paths(root, [], all_paths)
    log(f'  Found {len(all_paths)} instruction nodes')

    # Group paths by operation_id
    op_to_paths: dict = {}
    for leaf, path in all_paths:
        op_id = leaf.get('operation_id')
        if op_id:
            op_to_paths.setdefault(op_id, []).append((leaf, path))

    # Write one cache file per operation_id
    op_ids = sorted(op_to_paths.keys())
    for i, op_id in enumerate(op_ids):
        progress(i, len(op_ids), 'Operations')
        op = operations.get(op_id) or {}

        variants = []
        for leaf, path in op_to_paths[op_id]:
            raw_enc = leaf.get('encoding') or {}
            variants.append({
                'name':      leaf.get('name'),
                'condition': leaf.get('condition'),
                'assembly':  leaf.get('assembly'),
                'encoding': {
                    'width':  raw_enc.get('width'),
                    'fields': _resolve_encoding(path),
                },
            })

        write_json(op_dir / f'{op_id}.json', {
            'operation_id':         op_id,
            'title':                op.get('title'),
            'brief':                op.get('brief'),
            'description':          op.get('description'),
            'decode':               op.get('decode'),
            'operation':            op.get('operation'),
            'instruction_variants': variants,
        })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log('AArch64 Agent Skills — Cache Builder')
    log(f'Repo root  : {REPO_ROOT}')
    log(f'Cache dir  : {CACHE_DIR}')
    log()

    check_sources()
    ensure_gitignore(CACHE_DIR, REPO_ROOT)

    # Wipe existing cache to avoid stale files from previous runs
    if CACHE_DIR.exists():
        import shutil
        shutil.rmtree(CACHE_DIR)
        log('  Cleared existing cache directory.')
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Step 1: Source file hashes (for manifest)
    # ------------------------------------------------------------------
    log('Step 1/4: Computing source file hashes...')
    hashes = {}
    for path in [FEATURES_PATH, INSTRUCTIONS_PATH, REGISTERS_PATH]:
        t0 = time.time()
        print(f'  SHA-256 {path.name} ...', end=' ', flush=True)
        hashes[path.name] = sha256_file(path)
        print(f'done ({time.time() - t0:.1f}s)')

    # ------------------------------------------------------------------
    # Step 2: Features
    # ------------------------------------------------------------------
    log('\nStep 2/4: Building features cache...')
    t0 = time.time()
    print('  Loading Features.json ...', end=' ', flush=True)
    with open(FEATURES_PATH) as f:
        feat_data = json.load(f)
    print(f'done ({time.time() - t0:.1f}s)')

    features = build_features_cache(feat_data)
    write_json(CACHE_DIR / 'features.json', features)
    log(f'  Written: cache/features.json  ({len(features)} parameters)')

    # ------------------------------------------------------------------
    # Step 3: Registers
    # ------------------------------------------------------------------
    log('\nStep 3/4: Building registers cache...')
    t0 = time.time()
    print('  Loading Registers.json ...', end=' ', flush=True)
    with open(REGISTERS_PATH) as f:
        reg_data = json.load(f)
    print(f'done ({time.time() - t0:.1f}s)')

    reg_dir  = CACHE_DIR / 'registers'
    reg_meta = build_registers_cache(reg_data, reg_dir)
    write_json(CACHE_DIR / 'registers_meta.json', reg_meta)
    log(f'  Written: cache/registers/       ({len(reg_data)} files)')
    log(f'  Written: cache/registers_meta.json  ({len(reg_meta)} unique names)')

    # ------------------------------------------------------------------
    # Step 4: Operations
    # ------------------------------------------------------------------
    log('\nStep 4/4: Building operations cache...')
    t0 = time.time()
    print('  Loading Instructions.json ...', end=' ', flush=True)
    with open(INSTRUCTIONS_PATH) as f:
        instr_data = json.load(f)
    print(f'done ({time.time() - t0:.1f}s)')

    op_dir = CACHE_DIR / 'operations'
    build_operations_cache(instr_data, op_dir)
    log(f'  Written: cache/operations/      ({len(instr_data["operations"])} files)')

    # ------------------------------------------------------------------
    # Manifest
    # ------------------------------------------------------------------
    manifest = {
        'built_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'cache_dir': str(CACHE_DIR),
        'sources': {
            name: {'sha256': sha, 'path': str(REPO_ROOT / name)}
            for name, sha in hashes.items()
        },
    }
    write_json(CACHE_DIR / 'manifest.json', manifest)

    log('\nmanifest.json written.')
    log('Done. Cache is ready for use.')


if __name__ == '__main__':
    main()
