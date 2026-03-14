#!/usr/bin/env python3
"""
query_allowlist.py — Feature-qualified instruction allowlist and register availability.

Given a target architecture version and optional explicit feature flags, produces:
  - Allowed instruction operation_ids (those whose feature conditions are satisfied)
  - Prohibited register names (those whose feature conditions are NOT satisfied)
  - Allowed register names (those whose conditions are satisfied or have none)

Usage:
    query_allowlist.py --arch v9Ap4
    query_allowlist.py --arch v9Ap4 --feat FEAT_SVE2
    query_allowlist.py --arch v9Ap4 --feat FEAT_SVE2 FEAT_SME --output json
    query_allowlist.py --arch v9Ap4 --summary
    query_allowlist.py --list-features v9Ap4

Environment:
    ARM_MRS_CACHE_DIR  Override cache directory (default: <repo_root>/cache)

Exit codes:
    0  success
    1  unknown arch version, missing cache, or invalid arguments

Output schema (--output json):
    {
      "schema_version": "1.0",
      "query": {
        "arch": "v9Ap4",
        "features": ["FEAT_AdvSIMD", "FEAT_FP", ..., "FEAT_SVE2"],
        "explicit_features": ["FEAT_SVE2"]
      },
      "stats": {
        "total_operations": 2262,
        "allowed_operations": 1234,
        "prohibited_operations": 1028,
        "total_registers": 1607,
        "allowed_registers": 987,
        "prohibited_registers": 620
      },
      "allowed_operations": ["ADC", "ADD_addsub_imm", ...],
      "prohibited_operations": ["add_z_p_zz", ...],
      "allowed_registers": [{"name": "SCTLR_EL1", "state": "AArch64"}, ...],
      "prohibited_registers": [{"name": "ZCR_EL1", "state": "AArch64",
                                "reason": "IsFeatureImplemented(FEAT_SVE)"}]
    }
"""

import argparse
import json
import sys
from pathlib import Path

from cache_utils import CACHE_DIR, check_staleness

FEATURES_CACHE  = CACHE_DIR / 'features.json'
REG_META_CACHE  = CACHE_DIR / 'registers_meta.json'
OP_DIR          = CACHE_DIR / 'operations'
REG_DIR         = CACHE_DIR / 'registers'

SCHEMA_VERSION  = '1.0'

VERSION_ORDER = [
    'v8Ap0', 'v8Ap1', 'v8Ap2', 'v8Ap3', 'v8Ap4', 'v8Ap5',
    'v8Ap6', 'v8Ap7', 'v8Ap8', 'v8Ap9',
    'v9Ap0', 'v9Ap1', 'v9Ap2', 'v9Ap3', 'v9Ap4', 'v9Ap5', 'v9Ap6',
]
VERSION_INDEX = {v: i for i, v in enumerate(VERSION_ORDER)}
VERSION_SET   = set(VERSION_ORDER)

# Sentinel index for any unknown version string — guaranteed to exceed all
# real version indices so features with unrecognized min_version strings are
# never included in the active feature set.
_UNKNOWN_VERSION_INDEX = 999


# ---------------------------------------------------------------------------
# Cache loading
# ---------------------------------------------------------------------------

def _require_cache(path: Path, builder: str) -> None:
    if not path.exists():
        print(f'Cache not found: {path}', file=sys.stderr)
        print(f'Run: python3 {builder}', file=sys.stderr)
        sys.exit(1)


def load_features() -> list:
    _require_cache(FEATURES_CACHE, 'tools/build_index.py')
    with open(FEATURES_CACHE) as f:
        return json.load(f)


def load_reg_meta() -> dict:
    _require_cache(REG_META_CACHE, 'tools/build_index.py')
    with open(REG_META_CACHE) as f:
        return json.load(f)


def load_op(op_id: str) -> dict:
    path = OP_DIR / f'{op_id}.json'
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def load_reg(cache_key: str) -> dict:
    path = REG_DIR / f'{cache_key}.json'
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def list_op_ids() -> list:
    _require_cache(OP_DIR, 'tools/build_index.py')
    return sorted(p.stem for p in OP_DIR.iterdir() if p.suffix == '.json')


# ---------------------------------------------------------------------------
# Feature set derivation
# ---------------------------------------------------------------------------

def features_for_arch(arch_version: str, features: list) -> set:
    """
    Return the set of FEAT_* names that are available at or before arch_version.

    A feature is included if its min_version <= arch_version (by VERSION_ORDER).
    Features with no min_version are always included (baseline features).
    """
    if arch_version not in VERSION_SET:
        print(f"Unknown architecture version '{arch_version}'.", file=sys.stderr)
        print(f"Known versions: {', '.join(VERSION_ORDER)}", file=sys.stderr)
        sys.exit(1)

    ceiling = VERSION_INDEX[arch_version]
    result = set()

    for feat in features:
        name = feat.get('name', '')
        if not name.startswith('FEAT_'):
            continue
        min_ver = feat.get('min_version')
        if min_ver is None:
            # Feature with no version constraint: always available
            result.add(name)
        elif VERSION_INDEX.get(min_ver, _UNKNOWN_VERSION_INDEX) <= ceiling:
            result.add(name)

    return result


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------

def _eval_condition(node, feature_set: set) -> bool:
    """
    Evaluate an AST condition node against a feature set.
    Returns True if the condition is satisfied, False otherwise.

    Supported node types:
      - AST.Bool          → literal bool value
      - AST.Function(IsFeatureImplemented, [FEAT_X]) → True if FEAT_X in feature_set
      - AST.BinaryOp(&&)  → left && right
      - AST.BinaryOp(||)  → left || right
      - AST.UnaryOp(!)    → not operand
      - anything else     → True (unknown = assume available; conservative approach)
    """
    if node is None:
        return True
    if not isinstance(node, dict):
        return True

    t = node.get('_type', '')

    if t == 'AST.Bool':
        return bool(node.get('value', True))

    if t == 'AST.Function':
        name = node.get('name', '')
        if name == 'IsFeatureImplemented':
            args = node.get('arguments', [])
            if args and isinstance(args[0], dict):
                feat_name = args[0].get('value', '')
                return feat_name in feature_set
        # Unknown function: assume True (conservative)
        return True

    if t == 'AST.BinaryOp':
        op    = node.get('op', '')
        left  = node.get('left',  {})
        right = node.get('right', {})
        if op == '&&':
            return _eval_condition(left, feature_set) and _eval_condition(right, feature_set)
        if op == '||':
            return _eval_condition(left, feature_set) or _eval_condition(right, feature_set)
        # Other binary ops (-->, <->, comparisons): assume True
        return True

    if t == 'AST.UnaryOp':
        op      = node.get('op', '')
        operand = node.get('expr') or node.get('operand', {})
        if op == '!':
            return not _eval_condition(operand, feature_set)
        return True

    # Unknown node type: assume available (conservative)
    return True


def condition_to_readable(node) -> str:
    """Convert a condition AST node to a short human-readable string."""
    if node is None:
        return '(none)'
    if not isinstance(node, dict):
        return str(node)
    t = node.get('_type', '')
    if t == 'AST.Bool':
        return str(node.get('value', '?')).lower()
    if t == 'AST.Function':
        def _arg_str(a):
            if not isinstance(a, dict):
                return str(a)
            val = a.get('value')
            if isinstance(val, str):
                return val
            if isinstance(val, dict):
                # Nested value (e.g. Types.Field) — show type tag
                return a.get('_type', '?')
            return str(val) if val is not None else a.get('_type', '?')
        args = ', '.join(_arg_str(a) for a in (node.get('arguments') or []))
        return f"{node.get('name', '?')}({args})"
    if t == 'AST.BinaryOp':
        left  = condition_to_readable(node.get('left',  {}))
        right = condition_to_readable(node.get('right', {}))
        return f'({left} {node.get("op", "?")} {right})'
    if t == 'AST.UnaryOp':
        operand = node.get('expr') or node.get('operand', {})
        return f'({node.get("op", "?")} {condition_to_readable(operand)})'
    if t == 'AST.Identifier':
        return node.get('value', '?')
    return f'[{t}]'


# ---------------------------------------------------------------------------
# Allowlist / blocklist computation
# ---------------------------------------------------------------------------

def compute_operation_lists(op_ids: list, feature_set: set) -> tuple:
    """
    Classify all operation_ids into allowed and prohibited lists.

    An operation is allowed if ANY of its instruction_variants has a condition
    that evaluates to True (or has no conditions).  An operation with no
    variants is allowed by default (baseline instructions).

    Returns (allowed: list[str], prohibited: list[str]).
    """
    allowed     = []
    prohibited  = []

    for op_id in op_ids:
        op = load_op(op_id)
        variants = op.get('instruction_variants', [])

        if not variants:
            # No variants → operation exists but has no feature-gated encoding
            # variants in the cache (e.g. assembly-only aliases). Treat as always
            # allowed: the cache schema guarantees that operations only appear in
            # op_to_paths if at least one instruction leaf references them, so an
            # empty variants list means the cache file exists but was not populated
            # from the instruction tree (should not normally occur in practice).
            allowed.append(op_id)
            continue

        # An operation is allowed if at least one variant is allowed
        op_allowed = False
        for variant in variants:
            cond = variant.get('condition')
            if _eval_condition(cond, feature_set):
                op_allowed = True
                break

        if op_allowed:
            allowed.append(op_id)
        else:
            prohibited.append(op_id)

    return allowed, prohibited


def compute_register_lists(reg_meta: dict, feature_set: set) -> tuple:
    """
    Classify all registers into allowed and prohibited lists.

    A register is prohibited if its condition evaluates to False.

    Returns:
      allowed    = list of {name, state}
      prohibited = list of {name, state, reason}
    """
    allowed     = []
    prohibited  = []

    for reg_name, entries in reg_meta.items():
        for entry in entries:
            state     = entry.get('state', '')
            cache_key = entry.get('cache_key', '')
            reg_data  = load_reg(cache_key)
            cond      = reg_data.get('condition')

            if _eval_condition(cond, feature_set):
                allowed.append({'name': reg_name, 'state': state})
            else:
                prohibited.append({
                    'name':   reg_name,
                    'state':  state,
                    'reason': condition_to_readable(cond),
                })

    return allowed, prohibited


# ---------------------------------------------------------------------------
# Public API  (H1-4: programmatic wrapper for downstream skills H3/H6)
# ---------------------------------------------------------------------------

def query_allowlist(
    arch: str,
    extra_features=None,
) -> dict:
    """
    Programmatic entry point for downstream skills (H3, H6).

    Parameters
    ----------
    arch            Architecture version string (e.g. 'v9Ap4').
    extra_features  Additional FEAT_* names to include beyond those implied
                    by the arch version (e.g. ['FEAT_SVE2', 'FEAT_SME']).

    Returns
    -------
    dict with keys:
      schema_version         str
      query                  {arch, features, explicit_features}
      stats                  {total_operations, allowed_operations,
                               prohibited_operations, total_registers,
                               allowed_registers, prohibited_registers}
      allowed_operations     list[str]
      prohibited_operations  list[str]
      allowed_registers      list[{name, state}]
      prohibited_registers   list[{name, state, reason}]
    """
    features_cache = load_features()
    reg_meta       = load_reg_meta()
    op_ids         = list_op_ids()

    # Build the active feature set
    active_features = features_for_arch(arch, features_cache)
    if extra_features:
        active_features = active_features | set(extra_features)

    explicit_feats = sorted(extra_features or [])

    # Compute lists
    allowed_ops, prohibited_ops = compute_operation_lists(op_ids, active_features)
    allowed_regs, prohibited_regs = compute_register_lists(reg_meta, active_features)

    return {
        'schema_version': SCHEMA_VERSION,
        'query': {
            'arch':              arch,
            'features':          sorted(active_features),
            'explicit_features': explicit_feats,
        },
        'stats': {
            'total_operations':    len(op_ids),
            'allowed_operations':  len(allowed_ops),
            'prohibited_operations': len(prohibited_ops),
            'total_registers':     sum(len(v) for v in reg_meta.values()),
            'allowed_registers':   len(allowed_regs),
            'prohibited_registers': len(prohibited_regs),
        },
        'allowed_operations':    allowed_ops,
        'prohibited_operations': prohibited_ops,
        'allowed_registers':     allowed_regs,
        'prohibited_registers':  prohibited_regs,
    }


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_allowlist(arch: str, extra_features: list, output: str, summary: bool) -> int:
    """Compute and display the feature-qualified allowlist."""
    features_cache = load_features()
    reg_meta       = load_reg_meta()
    op_ids         = list_op_ids()

    # Build the active feature set
    active_features = features_for_arch(arch, features_cache)
    if extra_features:
        active_features = active_features | set(extra_features)

    # Compute lists
    allowed_ops, prohibited_ops = compute_operation_lists(op_ids, active_features)
    allowed_regs, prohibited_regs = compute_register_lists(reg_meta, active_features)

    total_ops    = len(op_ids)
    total_regs   = sum(len(v) for v in reg_meta.values())

    result = {
        'schema_version': SCHEMA_VERSION,
        'query': {
            'arch':              arch,
            'features':          sorted(active_features),
            'explicit_features': sorted(extra_features),
        },
        'stats': {
            'total_operations':    total_ops,
            'allowed_operations':  len(allowed_ops),
            'prohibited_operations': len(prohibited_ops),
            'total_registers':     total_regs,
            'allowed_registers':   len(allowed_regs),
            'prohibited_registers': len(prohibited_regs),
        },
        'allowed_operations':    allowed_ops,
        'prohibited_operations': prohibited_ops,
        'allowed_registers':     allowed_regs,
        'prohibited_registers':  prohibited_regs,
    }

    if output == 'json':
        print(json.dumps(result, indent=2))
        return 0

    # Human-readable output
    print(f'ARM AArch64 Feature-Qualified Allowlist')
    print(f'Arch version   : {arch}')
    if extra_features:
        print(f'Extra features : {", ".join(sorted(extra_features))}')
    print(f'Active features: {len(active_features)}')
    print()

    print(f'Operations:  {len(allowed_ops)}/{total_ops} allowed  '
          f'({len(prohibited_ops)} prohibited)')
    print(f'Registers :  {len(allowed_regs)}/{total_regs} allowed  '
          f'({len(prohibited_regs)} prohibited)')

    if not summary:
        print()
        print('--- Allowed operations ---')
        for op_id in allowed_ops:
            print(f'  {op_id}')

        if prohibited_ops:
            print()
            print('--- Prohibited operations ---')
            for op_id in prohibited_ops:
                print(f'  {op_id}')

        print()
        print('--- Prohibited registers ---')
        if prohibited_regs:
            for reg in prohibited_regs:
                print(f'  {reg["name"]}  [{reg["state"]}]  (reason: {reg["reason"]})')
        else:
            print('  (none)')

    return 0


def cmd_list_features(arch: str) -> int:
    """List all features active at the given architecture version."""
    if arch not in VERSION_SET:
        print(f"Unknown architecture version '{arch}'.", file=sys.stderr)
        print(f"Known versions: {', '.join(VERSION_ORDER)}", file=sys.stderr)
        return 1

    features_cache = load_features()
    active = features_for_arch(arch, features_cache)

    print(f'Features active at {arch}: {len(active)}')
    print()
    for name in sorted(active):
        print(f'  {name}')
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Compute a feature-qualified AArch64 instruction allowlist.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  query_allowlist.py --arch v9Ap4
  query_allowlist.py --arch v9Ap4 --feat FEAT_SVE2
  query_allowlist.py --arch v9Ap4 --feat FEAT_SVE2 FEAT_SME --output json
  query_allowlist.py --arch v9Ap4 --summary
  query_allowlist.py --list-features v9Ap4
""",
    )
    parser.add_argument(
        '--arch', metavar='VERSION',
        help='Target architecture version (e.g. v9Ap4). Required unless --list-features.',
    )
    parser.add_argument(
        '--feat', metavar='FEAT', nargs='+', default=[],
        help='Additional FEAT_* flags to include (beyond those implied by --arch).',
    )
    parser.add_argument(
        '--output', choices=['text', 'json'], default='text',
        help='Output format: text (default) or json.',
    )
    parser.add_argument(
        '--summary', action='store_true',
        help='Print only the summary counts; omit the full operation/register lists.',
    )
    parser.add_argument(
        '--list-features', metavar='VERSION',
        help='List all features active at the given arch version and exit.',
    )
    args = parser.parse_args()

    check_staleness()

    if args.list_features:
        return cmd_list_features(args.list_features)

    if not args.arch:
        parser.print_help()
        return 1

    return cmd_allowlist(args.arch, args.feat, args.output, args.summary)


if __name__ == '__main__':
    sys.exit(main())
