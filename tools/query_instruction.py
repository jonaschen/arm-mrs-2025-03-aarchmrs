#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
query_instruction.py - Instruction encoding and operation queries against the MRS cache.

Usage:
    query_instruction.py ADC            # title, brief, all encoding variants
    query_instruction.py ADC --enc      # encoding bit fields for all variants
    query_instruction.py ADC --op       # ASL pseudocode (decode + operation blocks)
    query_instruction.py --list ADD     # all operation_ids matching the pattern

Environment:
    ARM_MRS_CACHE_DIR  Override cache directory (default: <repo_root>/cache)

Exit codes:
    0  success
    1  operation not found or cache missing
"""

import argparse
import json
import re
import sys
from pathlib import Path

from cache_utils import CACHE_DIR, ARM_ARM_CACHE, check_staleness

OP_DIR     = CACHE_DIR / 'operations'
T32_OP_DIR = ARM_ARM_CACHE / 't32_operations'
A32_OP_DIR = ARM_ARM_CACHE / 'a32_operations'

DEFAULT_OP_LINES = 60

VALID_ISA = ('a64', 't32', 'a32')

# ---------------------------------------------------------------------------
# Cache loading
# ---------------------------------------------------------------------------

def _builder_script(isa: str) -> str:
    """Return the name of the cache builder script for the given ISA."""
    return 'tools/build_arm_arm_index.py' if isa in ('t32', 'a32') else 'tools/build_index.py'


def get_op_dir(isa: str) -> Path:
    """Return the operations cache directory for the given ISA."""
    isa = isa.lower()
    if isa == 't32':
        return T32_OP_DIR
    if isa == 'a32':
        return A32_OP_DIR
    return OP_DIR


def op_index(isa: str = 'a64') -> list:
    op_dir = get_op_dir(isa)
    if not op_dir.exists():
        print(
            f'Cache not found for {isa.upper()}. '
            f'Run: python3 {_builder_script(isa)}',
            file=sys.stderr,
        )
        sys.exit(1)
    return sorted(p.stem for p in op_dir.iterdir() if p.suffix == '.json')


def load_op(op_id: str, isa: str = 'a64') -> dict:
    path = get_op_dir(isa) / f'{op_id}.json'
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Assembly rendering
# ---------------------------------------------------------------------------

def render_assembly(symbols: list) -> str:
    """Render assembly symbol list to a human-readable template string."""
    parts = []
    for s in symbols:
        t = s.get('_type', '')
        if t == 'Instruction.Symbols.Literal':
            parts.append(s['value'])
        elif t == 'Instruction.Symbols.RuleReference':
            rule = s['rule_id']
            # Strip trailing __N disambiguation suffixes for display
            base = re.sub(r'__\d+$', '', rule)
            parts.append(f'<{base}>')
        elif t == 'Instruction.Symbols.Optional':
            inner = render_assembly(s.get('symbols', []))
            parts.append(f'{{{inner}}}')
        else:
            parts.append(f'[{t}]')
    return ''.join(parts)

# ---------------------------------------------------------------------------
# Encoding rendering
# ---------------------------------------------------------------------------

def render_encoding_table(fields: list) -> str:
    """Render 32-bit encoding fields as a compact table."""
    lines = []
    # Header
    lines.append(f"  {'Bits':8}  {'Name':12}  {'Value':12}  Kind")
    lines.append(f"  {'-'*8}  {'-'*12}  {'-'*12}  ----")
    for f in sorted(fields, key=lambda x: -x['start']):
        start = f['start']
        width = f['width']
        end   = start + width - 1
        brange = f'[{end}:{start}]' if width > 1 else f'[{start}]'
        name  = f.get('name') or ''
        value = f.get('value') or ''
        kind  = f.get('kind') or ''
        lines.append(f"  {brange:8}  {name:12}  {value:12}  {kind}")
    return '\n'.join(lines)

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_lookup(op: dict) -> int:
    """Display summary for an operation."""
    op_id = op['operation_id']
    isa   = op.get('isa', 'A64').upper()
    title = op.get('title') or '(not available in BSD MRS release)'
    brief = op.get('brief') or '(not available in BSD MRS release)'
    if brief == '.':
        brief = '(not available in BSD MRS release)'

    print(f"Operation    : {op_id}")
    print(f"ISA          : {isa}")
    print(f"Title        : {title}")
    print(f"Brief        : {brief}")
    print()

    variants = op.get('instruction_variants') or []
    if not variants:
        print("No instruction variants found.")
        return 0

    print(f"Variants ({len(variants)}):")
    for iv in variants:
        name = iv['name']
        syms = iv.get('assembly', {}).get('symbols') or []
        asm  = render_assembly(syms) if syms else '(no assembly template)'
        print(f"  {name}")
        print(f"    asm: {asm}")
    print()
    if isa == 'A64':
        print("Note: Descriptions are not available in the BSD MRS release.")
    return 0


def cmd_enc(op: dict) -> int:
    """Display encoding bit fields for all variants."""
    op_id    = op['operation_id']
    isa      = op.get('isa', 'A64').upper()
    variants = op.get('instruction_variants') or []

    print(f"Operation : {op_id}  ISA: {isa}  ({len(variants)} variants)\n")

    for iv in variants:
        name   = iv['name']
        enc    = iv.get('encoding') or {}
        width  = enc.get('width', 32)
        fields = enc.get('fields') or []
        syms   = iv.get('assembly', {}).get('symbols') or []
        asm    = render_assembly(syms) if syms else '(no assembly template)'

        print(f"[{name}]")
        print(f"  asm   : {asm}")
        print(f"  width : {width} bits")
        if fields:
            print(render_encoding_table(fields))
        else:
            print("  (no encoding fields)")
        print()

    return 0


def cmd_op(op: dict, full: bool, max_lines: int) -> int:
    """Display ASL pseudocode blocks."""
    op_id   = op['operation_id']
    decode  = op.get('decode')
    operation = op.get('operation') or ''

    print(f"Operation : {op_id}\n")

    if decode:
        lines = decode.splitlines()
        print(f"--- Decode ({len(lines)} lines) ---")
        shown = lines if full else lines[:max_lines]
        print('\n'.join(shown))
        if not full and len(lines) > max_lines:
            print(f"... ({len(lines) - max_lines} lines omitted — use --full to show all)")
        print()
    else:
        print("--- Decode ---")
        print("(not available in BSD MRS release)")
        print()

    if operation and operation != '// Not specified':
        lines = operation.splitlines()
        print(f"--- Operation ({len(lines)} lines) ---")
        shown = lines if full else lines[:max_lines]
        print('\n'.join(shown))
        if not full and len(lines) > max_lines:
            print(f"... ({len(lines) - max_lines} lines omitted — use --full to show all)")
    else:
        print("--- Operation ---")
        print("(not available in BSD MRS release)")

    return 0


def cmd_list(pattern: str, index: list, isa: str = 'a64') -> int:
    """List operation_id values matching a pattern."""
    upper = pattern.upper()
    matches = [op_id for op_id in index if upper in op_id.upper()]
    if not matches:
        print(f"No {isa.upper()} operations matching '{pattern}'.", file=sys.stderr)
        return 1
    for m in matches:
        print(m)
    print(f"\n({len(matches)} results)")
    return 0

# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def resolve_op(name: str, index: list, isa: str = 'a64') -> dict:
    """Find and load an operation by exact or case-insensitive match."""
    upper = name.upper()
    # Exact match
    if name in index:
        return load_op(name, isa)
    # Case-insensitive
    for op_id in index:
        if op_id.upper() == upper:
            return load_op(op_id, isa)
    # Partial — suggest
    suggestions = [op_id for op_id in index if upper in op_id.upper()]
    print(f"{isa.upper()} operation '{name}' not found.", file=sys.stderr)
    if suggestions:
        print(f"Similar: {', '.join(suggestions[:10])}", file=sys.stderr)
        print(f"Use --list {name} to see all matches.", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Query ARM instruction encoding and operations from the MRS cache.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  query_instruction.py ADC
  query_instruction.py ADC --enc
  query_instruction.py ADC --op
  query_instruction.py ADC --op --full
  query_instruction.py --list ADD
  query_instruction.py LDR --isa t32
  query_instruction.py LDR --isa a32 --enc
  query_instruction.py --list LDR --isa t32
""",
    )
    parser.add_argument('operation', nargs='?',          help='Operation ID (e.g. ADC, ADD_addsub_imm, LDR)')
    parser.add_argument('--enc',     action='store_true', help='Show encoding bit fields for all variants')
    parser.add_argument('--op',      action='store_true', help='Show ASL pseudocode blocks')
    parser.add_argument('--full',    action='store_true', help='Show full pseudocode (no line cap)')
    parser.add_argument('--list',    metavar='PATTERN',   help='List operation_ids matching pattern')
    parser.add_argument(
        '--isa',
        metavar='ISA',
        default='a64',
        choices=VALID_ISA,
        help='Instruction set architecture: a64 (default), t32, a32',
    )
    args = parser.parse_args()

    isa = args.isa.lower()
    check_staleness(isa)
    index = op_index(isa)

    if args.list:
        return cmd_list(args.list, index, isa)

    if not args.operation:
        parser.print_help()
        return 0

    op = resolve_op(args.operation, index, isa)

    if args.enc:
        return cmd_enc(op)
    if args.op:
        return cmd_op(op, args.full, DEFAULT_OP_LINES)
    return cmd_lookup(op)


if __name__ == '__main__':
    sys.exit(main())
