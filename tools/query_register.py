#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
query_register.py - Register field, value, and access queries against the MRS cache.

Usage:
    query_register.py SCTLR_EL1                   # all fields with bit ranges and types
    query_register.py SCTLR_EL1 UCI               # single field detail
    query_register.py SCTLR_EL1 UCI --values       # full value enumeration
    query_register.py SCTLR_EL1 --access           # all accessor encodings
    query_register.py --list EL1                   # name pattern search
    query_register.py --list EL1 --state AArch64   # with state filter

Environment:
    ARM_MRS_CACHE_DIR  Override cache directory (default: <repo_root>/cache)

Exit codes:
    0  success
    1  register not found, cache missing, or ambiguous
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT  = SCRIPT_DIR.parent
CACHE_DIR  = Path(os.environ.get('ARM_MRS_CACHE_DIR', str(REPO_ROOT / 'cache')))
REG_DIR    = CACHE_DIR / 'registers'
META_PATH  = CACHE_DIR / 'registers_meta.json'

# ---------------------------------------------------------------------------
# AST renderer (shared with query_feature.py)
# ---------------------------------------------------------------------------

def render_ast(node) -> str:
    if not isinstance(node, dict):
        return str(node)
    t = node.get('_type', '')
    if t == 'AST.Identifier':
        return node.get('value', '?')
    if t == 'AST.Bool':
        return str(node.get('value', '?')).lower()
    if t == 'AST.Integer':
        return str(node.get('value', '?'))
    if t == 'AST.BinaryOp':
        left  = render_ast(node.get('left',  {}))
        right = render_ast(node.get('right', {}))
        op    = node.get('op', '?')
        return f'({left} {op} {right})'
    if t == 'AST.UnaryOp':
        expr = node.get('expr') or node.get('operand', {})
        return f'({node.get("op","?")} {render_ast(expr)})'
    if t == 'AST.Function':
        args = ', '.join(render_ast(a) for a in node.get('arguments', []))
        return f'{node.get("name","?")}({args})'
    if t == 'Types.Field':
        v = node.get('value', {})
        return f'{v.get("name","?")}.{v.get("field","?")}'
    if t == 'AST.DotAtom':
        vals = node.get('values', [])
        return '.'.join(render_ast(v) for v in vals)
    if t == 'AST.Set':
        vals = node.get('values', [])
        return '{' + ', '.join(render_ast(v) for v in vals) + '}'
    if t in ('Values.Value', 'Values.Group'):
        return node.get('value', '?')
    return f'[{t}]'

# ---------------------------------------------------------------------------
# Cache loading
# ---------------------------------------------------------------------------

def load_meta() -> dict:
    if not META_PATH.exists():
        print('Cache not found. Run: python tools/build_index.py', file=sys.stderr)
        sys.exit(1)
    with open(META_PATH) as f:
        return json.load(f)


def load_register(cache_key: str) -> dict:
    path = REG_DIR / f'{cache_key}.json'
    if not path.exists():
        print(f'Cache file not found: {path}', file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


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
# Name normalization and resolution
# ---------------------------------------------------------------------------

def normalize_name(name: str) -> str:
    """
    Normalize a parameterized register name for meta lookup.
    Meta keys use <n> notation: DBGBCR2_EL1 -> DBGBCR<n>_EL1
    Only replaces a digit run that follows alpha characters and precedes _LETTER.
    """
    return re.sub(r'(?<=[A-Z])(\d+)(?=_[A-Z])', r'<n>', name)


def resolve_register(name: str, state: str | None, meta: dict) -> tuple:
    """
    Resolve a register name to (cache_key, reg_data, requested_index).

    requested_index: the numeric index parsed from a parameterized name (e.g. 2 for DBGBCR2_EL1),
                     or None if not parameterized.
    """
    upper = name.upper()
    requested_index = None

    # Try exact match first
    entries = meta.get(upper)
    if not entries:
        # Try with <n> normalization (parameterized registers like DBGBCR2_EL1)
        norm = normalize_name(upper)
        entries = meta.get(norm)
        if entries:
            # Extract the requested index from original name (e.g. 2 from DBGBCR2_EL1)
            m = re.search(r'(?<=[A-Z])(\d+)(?=_[A-Z])', upper)
            if m:
                requested_index = int(m.group(1))
        else:
            # Last resort: case-insensitive scan
            for k in meta:
                if k.upper() == upper or k.upper() == norm:
                    entries = meta[k]
                    break

    if not entries:
        print(f"Register '{name}' not found in cache.", file=sys.stderr)
        # Suggest similar names
        pattern = upper.replace('_', '')
        suggestions = [k for k in meta if pattern[:4] in k][:6]
        if suggestions:
            print(f"Similar names: {', '.join(suggestions)}", file=sys.stderr)
        sys.exit(1)

    # Apply state filter
    if state:
        filtered = [e for e in entries if e['state'].lower() == state.lower()]
        if not filtered:
            avail = [e['state'] for e in entries]
            print(f"Register '{name}' not available in state '{state}'. "
                  f"Available: {', '.join(avail)}", file=sys.stderr)
            sys.exit(1)
        entries = filtered

    if len(entries) > 1:
        # Prefer AArch64 by default
        aa64 = [e for e in entries if e['state'] == 'AArch64']
        if aa64:
            entries = aa64
        else:
            # Ambiguous — report
            options = ', '.join(f"{e['cache_key']} ({e['state']})" for e in entries)
            print(f"Multiple matches for '{name}': {options}", file=sys.stderr)
            print("Use --state to select one.", file=sys.stderr)
            sys.exit(1)

    chosen = entries[0]
    return chosen['cache_key'], load_register(chosen['cache_key']), requested_index

# ---------------------------------------------------------------------------
# Field helpers
# ---------------------------------------------------------------------------

def bits_str(bits: list) -> str:
    """Format a list of bit ranges as e.g. [26], [31:16], [7:4, 1:0]."""
    parts = []
    for b in (bits or []):
        start = b['start']
        width = b['width']
        if width == 1:
            parts.append(f'[{start}]')
        else:
            parts.append(f'[{start + width - 1}:{start}]')
    return ', '.join(parts) if parts else '?'


def find_field(fieldsets: list, field_name: str):
    """Find a named field across all fieldsets. Returns (fieldset_idx, field) or (None, None)."""
    for i, fs in enumerate(fieldsets):
        for f in fs.get('fields', []):
            if f['name'].upper() == field_name.upper():
                return i, f
    return None, None

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_lookup(reg: dict, requested_index) -> int:
    """Display all fields for a register."""
    display_name = reg['name']
    if requested_index is not None:
        display_name = display_name.replace('<n>', str(requested_index))

    print(f"Register     : {display_name}")
    print(f"State        : {reg['state']}")
    if reg.get('index_variable') and reg.get('indexes'):
        idx = reg['indexes']
        idx_str = ', '.join(
            f"{iv.get('start',0)}–{iv.get('start',0)+iv.get('width',0)-1}"
            if iv.get('_type') == 'Range' else str(iv)
            for iv in idx
        )
        print(f"Index ({reg['index_variable']}) : {idx_str}")
    if reg.get('condition'):
        print(f"Condition    : {render_ast(reg['condition'])}")
    print()

    fieldsets = reg.get('fieldsets', [])
    if not fieldsets:
        print("No fieldsets found.")
        return 0

    for fi, fs in enumerate(fieldsets):
        cond = fs.get('condition')
        cond_str = render_ast(cond) if cond and not (isinstance(cond, dict) and cond.get('value') is True) else None
        header = f"Fieldset {fi + 1}"
        if cond_str and cond_str != 'true':
            header += f" (when {cond_str})"
        if len(fieldsets) > 1 or cond_str:
            print(f"{header}:")

        fields = fs.get('fields', [])
        if not fields:
            print("  (no fields)")
            continue

        # Column widths
        max_name = max((len(f['name']) for f in fields), default=8)
        print(f"  {'Field':{max_name}}  {'Bits':12}  {'Type':20}  Values")
        print(f"  {'-'*max_name}  {'-'*12}  {'-'*20}  ------")
        for f in fields:
            bstr   = bits_str(f.get('bits'))
            ftype  = (f.get('type') or '').replace('Fields.', '')
            nvals  = len(f.get('values') or [])
            val_hint = f"{nvals} defined" if nvals else "(none)"
            print(f"  {f['name']:{max_name}}  {bstr:12}  {ftype:20}  {val_hint}")
        print()

    other_states = _other_states(reg['name'], reg['state'])
    if other_states:
        print(f"Note: This register also exists in state(s): {', '.join(other_states)}. "
              f"Use --state to query them.")
    print("Note: Field descriptions are not available in the BSD MRS release.")
    return 0


def _other_states(name: str, current_state: str) -> list:
    """Return other states for this register name (requires meta to be available)."""
    # We load meta lazily here to avoid passing it everywhere
    try:
        meta = json.load(open(META_PATH))
        # Normalize the name (strip <n> → _n_ form)
        key = re.sub(r'<[^>]+>', 'n', name).replace('__', '_').upper()
        # Try both the raw name and normalized
        entries = meta.get(name.upper()) or meta.get(key) or []
        return [e['state'] for e in entries if e['state'] != current_state]
    except Exception:
        return []


def cmd_field(reg: dict, field_name: str, show_values: bool) -> int:
    """Display detail for a single named field."""
    fieldsets = reg.get('fieldsets', [])
    fi, f = find_field(fieldsets, field_name)
    if f is None:
        all_names = [fld['name'] for fs in fieldsets for fld in fs.get('fields', [])]
        print(f"Field '{field_name}' not found in {reg['name']}.", file=sys.stderr)
        print(f"Available fields: {', '.join(all_names)}", file=sys.stderr)
        return 1

    print(f"Register : {reg['name']}  ({reg['state']})")
    print(f"Field    : {f['name']}")
    print(f"Bits     : {bits_str(f.get('bits'))}")
    ftype = (f.get('type') or '').replace('Fields.', '')
    print(f"Type     : {ftype}")

    values = f.get('values') or []
    if show_values:
        if values:
            print(f"\nValues ({len(values)}):")
            for v in values:
                meaning = v.get('meaning') or '(no description in BSD MRS release)'
                print(f"  {v.get('value','?'):10}  {meaning}")
        else:
            print("\nValues: (none defined)")
    else:
        if values:
            print(f"Values   : {len(values)} defined (use --values to expand)")
        else:
            print("Values   : (none defined)")

    print()
    print("Note: Field descriptions are not available in the BSD MRS release.")
    return 0


def _render_access_type(access) -> str:
    """Render an access permission node compactly."""
    if not isinstance(access, dict):
        return str(access)
    t = access.get('_type', '')
    if t == 'Accessors.Permission.AccessTypes.Memory.ReadWriteAccess':
        return f"R={access.get('read','?')} W={access.get('write','?')}"
    if t == 'Accessors.Permission.AccessTypes.Memory.ImplementationDefined':
        return 'IMPLEMENTATION_DEFINED'
    if t in ('AST.Function', 'AST.Assignment', 'AST.BinaryOp', 'AST.Identifier'):
        return render_ast(access)
    # Nested permission node — show summary
    if isinstance(access, list):
        return f'[{len(access)} conditional branches]'
    return render_ast(access) if isinstance(access, dict) else str(access)


def _summarise_access(access_node, prefix: str = '') -> list:
    """
    Flatten a nested Accessors.Permission.* tree into (condition_str, action_str) pairs.
    prefix accumulates parent conditions so each leaf entry is fully qualified.
    """
    if not isinstance(access_node, dict):
        return []
    cond = access_node.get('condition')
    inner = access_node.get('access')
    cond_str = render_ast(cond) if cond else None

    # Build the combined condition for this level
    if cond_str and cond_str != 'true':
        combined = f"{prefix} && {cond_str}".lstrip(' & ') if prefix else cond_str
    else:
        combined = prefix

    # If inner is a list, recurse into each element
    if isinstance(inner, list):
        results = []
        for item in inner:
            results.extend(_summarise_access(item, combined))
        return results

    # Leaf: inner is an action dict or something renderable
    if inner is not None:
        action_str = _render_access_type(inner)
        label = f"when {combined}" if combined else 'always'
        return [(label, action_str)]

    return []


def cmd_access(reg: dict) -> int:
    """Display all accessor encodings for a register."""
    print(f"Register  : {reg['name']}  ({reg['state']})")
    accessors = reg.get('accessors') or []
    if not accessors:
        print("No accessors defined.")
        return 0

    print(f"Accessors : {len(accessors)}\n")

    for i, acc in enumerate(accessors):
        atype = acc.get('type', '?').replace('Accessors.', '')
        aname = acc.get('name') or ''
        enc   = acc.get('encoding') or []

        print(f"[{i+1}] {atype}  {aname}")

        if enc:
            for e in enc:
                asmval = e.get('asmvalue', '')
                encodings = e.get('encodings', {})
                fields_str = '  '.join(
                    f"{k}={render_ast(v)}" for k, v in sorted(encodings.items())
                )
                print(f"    asm: {asmval}")
                if fields_str:
                    print(f"    enc: {fields_str}")
        else:
            print(f"    (no encoding)")

        # Show condensed access summary (top-level only to avoid overwhelming output)
        access_node = acc.get('access')
        if access_node:
            pairs = _summarise_access(access_node)
            if pairs:
                print(f"    access rules ({len(pairs)}):")
                for cond, action in pairs[:8]:  # cap at 8 rules
                    print(f"      {cond}: {action}")
                if len(pairs) > 8:
                    print(f"      ... ({len(pairs) - 8} more rules omitted)")
        print()

    return 0


def cmd_list(pattern: str, state_filter: str | None, meta: dict) -> int:
    """List register names matching a pattern, with optional state filter."""
    upper = pattern.upper()
    results = []
    for name, entries in meta.items():
        if upper in name.upper():
            if state_filter:
                entries = [e for e in entries if e['state'].lower() == state_filter.lower()]
            for e in entries:
                results.append((name, e['state']))

    if not results:
        msg = f"No registers matching '{pattern}'"
        if state_filter:
            msg += f" in state '{state_filter}'"
        print(msg + '.', file=sys.stderr)
        return 1

    results.sort()
    max_name = max(len(r[0]) for r in results)
    for name, state in results:
        print(f"  {name:{max_name}}  {state}")
    print(f"\n({len(results)} results)")
    return 0

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Query ARM architecture registers from the MRS cache.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  query_register.py SCTLR_EL1
  query_register.py SCTLR_EL1 UCI
  query_register.py SCTLR_EL1 UCI --values
  query_register.py SCTLR_EL1 --access
  query_register.py DBGBCR2_EL1
  query_register.py --list EL1
  query_register.py --list EL1 --state AArch64
""",
    )
    parser.add_argument('register',  nargs='?',         help='Register name (e.g. SCTLR_EL1)')
    parser.add_argument('field',     nargs='?',         help='Field name (e.g. UCI)')
    parser.add_argument('--values',  action='store_true', help='Show all field values and meanings')
    parser.add_argument('--access',  action='store_true', help='Show accessor encodings')
    parser.add_argument('--state',   metavar='STATE',   help='State filter: AArch64, AArch32, ext')
    parser.add_argument('--list',    metavar='PATTERN', help='List register names matching pattern')
    args = parser.parse_args()

    check_staleness()
    meta = load_meta()

    if args.list:
        return cmd_list(args.list, args.state, meta)

    if not args.register:
        parser.print_help()
        return 0

    cache_key, reg, req_idx = resolve_register(args.register, args.state, meta)

    if args.access:
        return cmd_access(reg)

    if args.field:
        return cmd_field(reg, args.field, args.values)

    return cmd_lookup(reg, req_idx)


if __name__ == '__main__':
    sys.exit(main())
