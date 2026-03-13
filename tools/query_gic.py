#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
query_gic.py — GIC register field, version, and cross-reference queries.

Queries the GIC cache built by build_gic_index.py.

Usage:
    query_gic.py GICD_CTLR                         # all fields with bit ranges, access types, reset values
    query_gic.py GICD_CTLR EnableGrp0              # single field detail
    query_gic.py GICD_CTLR --version v3            # fields for a specific GIC version
    query_gic.py --block GICD                      # all registers in a component block
    query_gic.py --block GICR                      # all GICR registers
    query_gic.py --block GITS                      # all GITS registers
    query_gic.py --list CTLR                       # register names matching pattern
    query_gic.py --icc-xref ICC_IAR1_EL1           # cross-reference to AARCHMRS system register

Environment:
    ARM_MRS_CACHE_DIR  Override cache directory (default: <repo_root>/cache)

Exit codes:
    0  success
    1  register/field not found, or cache missing
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

GIC_CACHE   = CACHE_DIR / 'gic'
GICD_PATH   = GIC_CACHE / 'GICD.json'
GICR_PATH   = GIC_CACHE / 'GICR.json'
GITS_PATH   = GIC_CACHE / 'GITS.json'
META_PATH   = GIC_CACHE / 'gic_meta.json'

BLOCK_PATHS = {
    'GICD': GICD_PATH,
    'GICR': GICR_PATH,
    'GITS': GITS_PATH,
}

# ---------------------------------------------------------------------------
# Cache loading
# ---------------------------------------------------------------------------

def _cache_missing() -> bool:
    return not META_PATH.exists()


def load_meta() -> dict:
    if _cache_missing():
        print('GIC cache not found. Run: python3 tools/build_gic_index.py', file=sys.stderr)
        sys.exit(1)
    with open(META_PATH) as f:
        return json.load(f)


def load_block(block: str) -> dict:
    path = BLOCK_PATHS.get(block.upper())
    if not path or not path.exists():
        print(f'GIC cache block "{block}" not found. Run: python3 tools/build_gic_index.py',
              file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def load_all_registers() -> list:
    """Load all registers from all block caches."""
    regs = []
    for block in ('GICD', 'GICR', 'GITS'):
        data = load_block(block)
        regs.extend(data.get('registers', []))
    return regs

# ---------------------------------------------------------------------------
# Register resolution
# ---------------------------------------------------------------------------

def _candidate_keys(name: str) -> list:
    """
    Return a list of candidate lookup keys for a register name, in order of preference.
    Handles parameterized names (e.g. GICD_ISENABLER2 → GICD_ISENABLER<n>).
    """
    upper = name.upper()
    candidates = [upper, name]
    # Strip trailing digits from name to handle GICD_ISENABLER2 → GICD_ISENABLER
    stripped = re.sub(r'\d+$', '', upper)
    if stripped != upper:
        candidates.append(stripped)
        candidates.append(stripped + '<n>')
        candidates.append(stripped + '<N>')
    return candidates


def resolve_register(name: str, meta: dict) -> dict | None:
    """
    Find a register by name (case-insensitive, with <n> normalisation).
    Returns the register dict or None if not found.
    """
    idx = meta.get('name_index', {})

    # Try each candidate key in the index
    entry = None
    for key in _candidate_keys(name):
        entry = idx.get(key)
        if entry:
            break

    # Last-resort: scan the full index for any key that normalises to the same string
    if not entry:
        upper = name.upper()
        for ikey, ival in idx.items():
            ikey_norm = ikey.upper().replace('<N>', '')
            if ikey_norm == upper or ikey.upper() == upper:
                entry = ival
                break

    if not entry:
        return None

    block = entry.get('block')
    block_data = load_block(block)
    registers  = block_data.get('registers', [])
    upper      = name.upper()

    for reg in registers:
        reg_name_upper = reg['name'].upper().replace('<N>', '')
        if reg_name_upper == upper or reg['name'].upper() == upper:
            return reg
        # Parameterized: GICD_ISENABLER<n> vs GICD_ISENABLER2
        base = reg['name'].upper().replace('<N>', '')
        if upper.startswith(base) or base.startswith(upper.rstrip('0123456789')):
            return reg

    return None


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _bits_str(bits: list) -> str:
    """Format a bits list as e.g. [0], [7:4], [31:16]."""
    parts = []
    for b in (bits or []):
        start = b['start']
        width = b['width']
        if width == 1:
            parts.append(f'[{start}]')
        else:
            parts.append(f'[{start + width - 1}:{start}]')
    return ', '.join(parts) if parts else '?'


def _filter_fieldsets_by_version(fieldsets: list, version: str | None) -> list:
    """Return fieldsets that match the requested GIC version, or all if None."""
    if not version:
        return fieldsets
    v = version.lower()
    return [fs for fs in fieldsets if v in [gv.lower() for gv in fs.get('gic_versions', [])]]


def _find_field(fieldsets: list, field_name: str):
    """Find a named field across all fieldsets. Returns (fieldset, field) or (None, None)."""
    upper = field_name.upper()
    for fs in fieldsets:
        for f in fs.get('fields', []):
            if f['name'].upper() == upper:
                return fs, f
    return None, None

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_lookup(reg: dict, version: str | None) -> int:
    """Display all fields for a register (optionally filtered by GIC version)."""
    print(f"Register     : {reg['name']}")
    print(f"Block        : {reg['block']}")
    print(f"Offset       : {reg.get('offset', '?')}")
    print(f"Width        : {reg.get('width', 32)}-bit")
    print(f"GIC versions : {', '.join(reg.get('gic_versions', []))}")
    print(f"Title        : {reg.get('title', '')}")
    brief = reg.get('brief')
    if brief:
        print(f"Brief        : {brief}")
    print()

    fieldsets = reg.get('fieldsets', [])
    fieldsets = _filter_fieldsets_by_version(fieldsets, version)

    if not fieldsets:
        print(f"No fieldsets found for version '{version}'." if version else "No fieldsets found.")
        return 0

    for fi, fs in enumerate(fieldsets):
        cond = fs.get('condition')
        versions_str = ', '.join(fs.get('gic_versions', []))
        header = f"Fieldset {fi + 1}"
        if cond:
            header += f" (when {cond})"
        if version:
            header += f" [GIC{version}]"
        elif versions_str:
            header += f" [{versions_str}]"

        if len(fieldsets) > 1 or cond:
            print(f"{header}:")

        fields = fs.get('fields', [])
        if not fields:
            print("  (no fields)")
            continue

        max_name = max((len(f['name']) for f in fields), default=8)
        print(f"  {'Field':{max_name}}  {'Bits':12}  {'Access':8}  {'Reset':6}  Brief")
        print(f"  {'-'*max_name}  {'-'*12}  {'-'*8}  {'-'*6}  -----")
        for f in fields:
            bstr  = _bits_str(f.get('bits'))
            acc   = f.get('access', '')
            rst   = f.get('reset', '')
            brief = (f.get('brief') or '')[:60]
            if len(f.get('brief') or '') > 60:
                brief += '...'
            print(f"  {f['name']:{max_name}}  {bstr:12}  {acc:8}  {rst:6}  {brief}")
        print()

    return 0


def cmd_field(reg: dict, field_name: str, version: str | None) -> int:
    """Display detail for a single named field."""
    fieldsets = reg.get('fieldsets', [])
    if version:
        fieldsets = _filter_fieldsets_by_version(fieldsets, version)

    fs, f = _find_field(fieldsets, field_name)
    if f is None:
        all_names = [fld['name'] for fset in reg.get('fieldsets', []) for fld in fset.get('fields', [])]
        unique_names = list(dict.fromkeys(all_names))
        print(f"Field '{field_name}' not found in {reg['name']}.", file=sys.stderr)
        print(f"Available fields: {', '.join(unique_names)}", file=sys.stderr)
        return 1

    cond = fs.get('condition') if fs else None

    print(f"Register : {reg['name']}  ({reg['block']})")
    print(f"Field    : {f['name']}")
    print(f"Bits     : {_bits_str(f.get('bits'))}")
    print(f"Access   : {f.get('access', '?')}")
    print(f"Reset    : {f.get('reset', '?')}")
    if cond:
        print(f"Condition: {cond}")
    if f.get('brief'):
        print(f"\nBrief: {f['brief']}")
    return 0


def cmd_block(block_name: str, version: str | None) -> int:
    """List all registers in a component block."""
    block_upper = block_name.upper()
    if block_upper not in BLOCK_PATHS:
        print(f"Unknown block '{block_name}'. Valid blocks: GICD, GICR, GITS.", file=sys.stderr)
        return 1

    data      = load_block(block_upper)
    registers = data.get('registers', [])
    meta_info = data.get('meta', {})

    print(f"Block    : {block_upper}")
    print(f"Spec     : {meta_info.get('spec_version', '')}")
    if version:
        print(f"Filter   : GIC{version}")
    print(f"Registers: {len(registers)}")
    print()

    max_name = max((len(r['name']) for r in registers), default=8)
    max_off  = max((len(r.get('offset', '')) for r in registers), default=6)
    print(f"  {'Name':{max_name}}  {'Offset':{max_off}}  {'Width':5}  Title")
    print(f"  {'-'*max_name}  {'-'*max_off}  {'-'*5}  -----")
    for reg in registers:
        if version:
            if not any(v.lower() == version.lower() for v in reg.get('gic_versions', [])):
                continue
        print(f"  {reg['name']:{max_name}}  {reg.get('offset','?'):{max_off}}  {reg.get('width',32):5}  {reg.get('title','')}")

    return 0


def cmd_list(pattern: str, meta: dict) -> int:
    """List register names matching a pattern."""
    upper   = pattern.upper()
    idx     = meta.get('name_index', {})
    results = [(name, info.get('block',''), info.get('title',''))
               for name, info in idx.items()
               if upper in name.upper() and '<n>' not in name.lower().replace('<n>','')]

    # Also include parameterized names
    results_all = [(name, info.get('block',''), info.get('title',''))
                   for name, info in idx.items()
                   if upper in name.upper()]
    # De-duplicate (canonical names only)
    seen  = set()
    final = []
    for name, block, title in sorted(results_all):
        if name not in seen:
            seen.add(name)
            final.append((name, block, title))

    if not final:
        print(f"No GIC registers matching '{pattern}'.", file=sys.stderr)
        return 1

    max_name  = max(len(r[0]) for r in final)
    max_block = 4
    for name, block, title in final:
        print(f"  {name:{max_name}}  {block:{max_block}}  {title}")
    print(f"\n({len(final)} results)")
    return 0


def cmd_icc_xref(icc_name: str, meta: dict) -> int:
    """Show cross-reference info for an ICC_* system register."""
    icc_list = meta.get('icc_system_registers', [])
    upper    = icc_name.upper()

    matches = [r for r in icc_list if r['name'].upper() == upper or upper in r['name'].upper()]
    if not matches:
        print(f"ICC register '{icc_name}' not found in cross-reference list.", file=sys.stderr)
        all_names = [r['name'] for r in icc_list]
        print(f"Known ICC registers: {', '.join(all_names)}", file=sys.stderr)
        return 1

    print(f"ICC Cross-Reference: {icc_name}")
    print()
    for r in matches:
        print(f"  Name  : {r['name']}")
        if r.get('brief'):
            print(f"  Brief : {r['brief']}")
        print(f"  Note  : This is a system register (MRS/MSR). Field data is in AARCHMRS.")
        print(f"  Query : python3 tools/query_register.py {r['name']}")
        print()
    return 0

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Query ARM GIC registers from the GIC cache.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  query_gic.py GICD_CTLR
  query_gic.py GICD_CTLR EnableGrp0
  query_gic.py GICD_CTLR EnableGrp1S --version v3
  query_gic.py --block GICD
  query_gic.py --block GICR
  query_gic.py --block GITS
  query_gic.py --list CTLR
  query_gic.py --icc-xref ICC_IAR1_EL1
""",
    )
    parser.add_argument('register', nargs='?',         help='Register name (e.g. GICD_CTLR)')
    parser.add_argument('field',    nargs='?',         help='Field name (e.g. EnableGrp0)')
    parser.add_argument('--version', metavar='VER',    help='Filter by GIC version: v3, v4')
    parser.add_argument('--block',   metavar='BLOCK',  help='List all registers in block: GICD, GICR, GITS')
    parser.add_argument('--list',    metavar='PATTERN',help='List register names matching pattern')
    parser.add_argument('--icc-xref',metavar='REG',    help='Show ICC_* cross-reference for a system register')
    args = parser.parse_args()

    meta = load_meta()

    if args.icc_xref:
        return cmd_icc_xref(args.icc_xref, meta)

    if args.list:
        return cmd_list(args.list, meta)

    if args.block:
        return cmd_block(args.block, args.version)

    if not args.register:
        parser.print_help()
        return 0

    reg = resolve_register(args.register, meta)
    if reg is None:
        print(f"Register '{args.register}' not found in GIC cache.", file=sys.stderr)
        # Suggest
        upper = args.register.upper()
        suggestions = [n for n in meta.get('name_index', {}) if upper[:6] in n][:5]
        if suggestions:
            print(f"Similar names: {', '.join(suggestions)}", file=sys.stderr)
        return 1

    if args.field:
        return cmd_field(reg, args.field, args.version)

    return cmd_lookup(reg, args.version)


if __name__ == '__main__':
    sys.exit(main())
