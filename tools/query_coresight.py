#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
query_coresight.py — CoreSight component register field and access queries.

Queries the CoreSight cache built by build_coresight_index.py.

Usage:
    query_coresight.py etm TRCPRGCTLR              # all fields with bit ranges and access types
    query_coresight.py etm TRCPRGCTLR EN           # single field detail
    query_coresight.py cti CTICONTROL              # CTI register lookup
    query_coresight.py --component etm             # all registers in a component
    query_coresight.py --component cti             # all CTI registers
    query_coresight.py --list-components           # list all known component types
    query_coresight.py --list CTRL                 # register names matching pattern
    query_coresight.py --id-block                  # common identification block registers

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

CS_CACHE   = CACHE_DIR / 'coresight'
META_PATH  = CS_CACHE / 'cs_meta.json'

COMPONENT_PATHS = {
    'ETM':      CS_CACHE / 'ETM.json',
    'CTI':      CS_CACHE / 'CTI.json',
    'STM':      CS_CACHE / 'STM.json',
    'ITM':      CS_CACHE / 'ITM.json',
    'ID_BLOCK': CS_CACHE / 'ID_BLOCK.json',
}

# Human-readable component descriptions
COMPONENT_TITLES = {
    'ETM':      'Embedded Trace Macrocell (ETMv4/ETE)',
    'CTI':      'Cross-Trigger Interface',
    'STM':      'System Trace Macrocell',
    'ITM':      'Instrumentation Trace Macrocell',
    'ID_BLOCK': 'Common Identification Block',
}

# ---------------------------------------------------------------------------
# Cache loading
# ---------------------------------------------------------------------------

def _cache_missing() -> bool:
    return not META_PATH.exists()


def load_meta() -> dict:
    if _cache_missing():
        print('CoreSight cache not found. Run: python3 tools/build_coresight_index.py',
              file=sys.stderr)
        sys.exit(1)
    with open(META_PATH) as f:
        return json.load(f)


def load_component(component: str) -> dict:
    path = COMPONENT_PATHS.get(component.upper())
    if not path or not path.exists():
        print(f'CoreSight cache component "{component}" not found. '
              f'Run: python3 tools/build_coresight_index.py',
              file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def load_all_registers() -> list:
    """Load all registers from all component caches."""
    regs = []
    for comp in ('ETM', 'CTI', 'STM', 'ITM', 'ID_BLOCK'):
        data = load_component(comp)
        regs.extend(data.get('registers', []))
    return regs

# ---------------------------------------------------------------------------
# Register resolution
# ---------------------------------------------------------------------------

def _candidate_keys(name: str) -> list:
    """
    Return a list of candidate lookup keys for a register name, in order of preference.
    Handles parameterized names (e.g. CTIINEN0 → CTIINEN<n>).
    """
    upper = name.upper()
    candidates = [upper, name]
    # Strip trailing digits to handle CTIINEN0 → CTIINEN
    stripped = re.sub(r'\d+$', '', upper)
    if stripped != upper:
        candidates.append(stripped)
        candidates.append(stripped + '<n>')
        candidates.append(stripped + '<N>')
    return candidates


def resolve_register(name: str, component_hint: str | None, meta: dict) -> dict | None:
    """
    Find a register by name (case-insensitive, with <n> normalisation).
    If component_hint is provided, search only that component.
    Returns the register dict or None if not found.
    """
    idx = meta.get('name_index', {})

    # Try each candidate key in the index
    entry = None
    for key in _candidate_keys(name):
        entry = idx.get(key)
        if entry:
            break

    # Last-resort: scan the full index
    if not entry:
        upper = name.upper()
        for ikey, ival in idx.items():
            ikey_norm = ikey.upper().replace('<N>', '')
            if ikey_norm == upper or ikey.upper() == upper:
                entry = ival
                break

    if not entry:
        return None

    # If a component hint is given, verify the match
    comp = entry.get('component', '').upper()
    if component_hint and comp != component_hint.upper():
        # Try to find the same register in the specified component
        return _scan_component_for_register(name, component_hint)

    comp_data  = load_component(comp)
    registers  = comp_data.get('registers', [])
    upper_name = name.upper()

    for reg in registers:
        reg_name_upper = reg['name'].upper().replace('<N>', '')
        if reg_name_upper == upper_name or reg['name'].upper() == upper_name:
            return reg
        # Parameterized: CTIINEN<n> vs CTIINEN0
        base = reg['name'].upper().replace('<N>', '')
        if upper_name.startswith(base) or base.startswith(upper_name.rstrip('0123456789')):
            return reg

    return None


def _scan_component_for_register(name: str, component: str) -> dict | None:
    """Scan a specific component cache for a register name."""
    try:
        data = load_component(component)
    except SystemExit:
        return None
    upper_name = name.upper()
    for reg in data.get('registers', []):
        reg_name_upper = reg['name'].upper().replace('<N>', '')
        if reg_name_upper == upper_name or reg['name'].upper() == upper_name:
            return reg
        base = reg['name'].upper().replace('<N>', '')
        if upper_name.startswith(base) or base.startswith(upper_name.rstrip('0123456789')):
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

def cmd_lookup(reg: dict) -> int:
    """Display all fields for a register."""
    print(f"Register   : {reg['name']}")
    print(f"Component  : {reg['component']}  ({COMPONENT_TITLES.get(reg['component'], reg['component'])})")
    print(f"Offset     : {reg.get('offset', '?')}")
    print(f"Width      : {reg.get('width', 32)}-bit")
    cs_vers = reg.get('cs_arch_versions', [])
    if cs_vers:
        print(f"CS Arch    : {', '.join(cs_vers)}")
    print(f"Title      : {reg.get('title', '')}")
    brief = reg.get('brief')
    if brief:
        print(f"Brief      : {brief}")
    print()

    fieldsets = reg.get('fieldsets', [])
    if not fieldsets:
        print('No fieldsets found.')
        return 0

    for fi, fs in enumerate(fieldsets):
        cond = fs.get('condition')
        if len(fieldsets) > 1 or cond:
            header = f'Fieldset {fi + 1}'
            if cond:
                header += f' (when {cond})'
            print(f'{header}:')

        fields = fs.get('fields', [])
        if not fields:
            print('  (no fields)')
            continue

        max_name = max((len(f['name']) for f in fields), default=8)
        print(f"  {'Field':{max_name}}  {'Bits':12}  {'Access':8}  {'Reset':6}  Brief")
        print(f"  {'-'*max_name}  {'-'*12}  {'-'*8}  {'-'*6}  -----")
        for f in fields:
            bstr  = _bits_str(f.get('bits'))
            acc   = f.get('access', '')
            rst   = f.get('reset') or ''
            brief = (f.get('brief') or '')[:60]
            if len(f.get('brief') or '') > 60:
                brief += '...'
            print(f"  {f['name']:{max_name}}  {bstr:12}  {acc:8}  {rst:6}  {brief}")
        print()

    return 0


def cmd_field(reg: dict, field_name: str) -> int:
    """Display detail for a single named field."""
    fieldsets = reg.get('fieldsets', [])
    fs, f = _find_field(fieldsets, field_name)
    if f is None:
        all_names = [fld['name'] for fset in fieldsets for fld in fset.get('fields', [])]
        unique_names = list(dict.fromkeys(all_names))
        print(f"Field '{field_name}' not found in {reg['name']}.", file=sys.stderr)
        print(f"Available fields: {', '.join(unique_names)}", file=sys.stderr)
        return 1

    cond = fs.get('condition') if fs else None

    print(f"Register  : {reg['name']}  ({reg['component']})")
    print(f"Field     : {f['name']}")
    print(f"Bits      : {_bits_str(f.get('bits'))}")
    print(f"Access    : {f.get('access', '?')}")
    print(f"Reset     : {f.get('reset', '?')}")
    if cond:
        print(f"Condition : {cond}")
    if f.get('brief'):
        print(f"\nBrief: {f['brief']}")
    return 0


def cmd_component(component_name: str) -> int:
    """List all registers in a component."""
    comp_upper = component_name.upper()
    if comp_upper not in COMPONENT_PATHS:
        valid = ', '.join(COMPONENT_PATHS.keys())
        print(f"Unknown component '{component_name}'. Valid components: {valid}.", file=sys.stderr)
        return 1

    data      = load_component(comp_upper)
    registers = data.get('registers', [])
    meta_info = data.get('meta', {})

    print(f"Component  : {comp_upper}  ({COMPONENT_TITLES.get(comp_upper, comp_upper)})")
    print(f"Spec       : {meta_info.get('spec_version', '')}")
    print(f"Registers  : {len(registers)}")
    print()

    max_name = max((len(r['name']) for r in registers), default=8) if registers else 8
    max_off  = max((len(r.get('offset', '')) for r in registers), default=6) if registers else 6
    print(f"  {'Name':{max_name}}  {'Offset':{max_off}}  {'Width':5}  Title")
    print(f"  {'-'*max_name}  {'-'*max_off}  {'-'*5}  -----")
    for reg in registers:
        print(f"  {reg['name']:{max_name}}  {reg.get('offset','?'):{max_off}}  "
              f"{reg.get('width',32):5}  {reg.get('title','')}")

    return 0


def cmd_list_components() -> int:
    """List all known component types."""
    print('CoreSight component types:')
    print()
    for comp, title in COMPONENT_TITLES.items():
        print(f"  {comp:<10}  {title}")
    print()
    print(f'Total: {len(COMPONENT_TITLES)} components')
    print()
    print('Use --component <NAME> to list all registers in a component.')
    return 0


def cmd_list(pattern: str, meta: dict) -> int:
    """List register names matching a pattern across all components."""
    upper  = pattern.upper()
    idx    = meta.get('name_index', {})
    all_entries = [
        (name, info.get('component', ''), info.get('title', ''))
        for name, info in idx.items()
        if upper in name.upper()
    ]

    # De-duplicate (canonical names only — skip the normalised <n>→n entries)
    seen  = set()
    final = []
    for name, comp, title in sorted(all_entries):
        if name not in seen:
            seen.add(name)
            final.append((name, comp, title))

    if not final:
        print(f"No CoreSight registers matching '{pattern}'.", file=sys.stderr)
        return 1

    max_name = max(len(r[0]) for r in final)
    max_comp = max(len(r[1]) for r in final) if final else 8
    for name, comp, title in final:
        print(f"  {name:{max_name}}  {comp:{max_comp}}  {title}")
    print(f"\n({len(final)} results)")
    return 0


def cmd_id_block() -> int:
    """Show all common identification block registers."""
    return cmd_component('ID_BLOCK')

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Query ARM CoreSight component registers from the CoreSight cache.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  query_coresight.py etm TRCPRGCTLR
  query_coresight.py etm TRCPRGCTLR EN
  query_coresight.py cti CTICONTROL GLBEN
  query_coresight.py --component etm
  query_coresight.py --component cti
  query_coresight.py --list-components
  query_coresight.py --list TRC
  query_coresight.py --list CTRL
  query_coresight.py --id-block
""",
    )
    parser.add_argument('component_or_reg', nargs='?',
                        help='Component name (etm, cti, stm, itm) OR register name for --list/--id-block')
    parser.add_argument('register',         nargs='?',
                        help='Register name (e.g. TRCPRGCTLR) when first arg is a component')
    parser.add_argument('field',            nargs='?',
                        help='Field name (e.g. EN) for single-field detail')
    parser.add_argument('--component',  metavar='COMP',
                        help='List all registers in component: ETM, CTI, STM, ITM, ID_BLOCK')
    parser.add_argument('--list-components', action='store_true',
                        help='List all known CoreSight component types')
    parser.add_argument('--list',       metavar='PATTERN',
                        help='List register names matching pattern across all components')
    parser.add_argument('--id-block',   action='store_true',
                        help='Show common identification block registers')
    args = parser.parse_args()

    meta = load_meta()

    if args.list_components:
        return cmd_list_components()

    if args.id_block:
        return cmd_id_block()

    if args.list:
        return cmd_list(args.list, meta)

    if args.component:
        return cmd_component(args.component)

    # Positional: first arg is a component name if it matches a known component
    component_hint = None
    reg_name       = None

    if args.component_or_reg:
        upper_first = args.component_or_reg.upper()
        if upper_first in COMPONENT_PATHS:
            # e.g. query_coresight.py etm TRCPRGCTLR [EN]
            component_hint = upper_first
            reg_name       = args.register
        else:
            # e.g. query_coresight.py TRCPRGCTLR [EN]  (no component prefix)
            reg_name = args.component_or_reg
            # shift field arg
            if args.field is None and args.register is not None:
                args.field = args.register

    if not reg_name:
        parser.print_help()
        return 0

    reg = resolve_register(reg_name, component_hint, meta)
    if reg is None:
        print(f"Register '{reg_name}' not found in CoreSight cache.", file=sys.stderr)
        upper = reg_name.upper()
        idx = meta.get('name_index', {})
        suggestions = [n for n in idx if upper[:6] in n.upper()][:5]
        if suggestions:
            print(f"Similar names: {', '.join(suggestions)}", file=sys.stderr)
        return 1

    if args.field:
        return cmd_field(reg, args.field)

    return cmd_lookup(reg)


if __name__ == '__main__':
    sys.exit(main())
