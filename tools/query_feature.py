#!/usr/bin/env python3
"""
query_feature.py — Feature / extension queries against the MRS cache.

Usage:
    query_feature.py FEAT_SVE                   # feature entry + rendered constraints
    query_feature.py FEAT_SVE --deps FEAT_FP16  # yes/no dependency check + tree
    query_feature.py --version v9Ap2            # features at or before this version
    query_feature.py --list SVE                 # names matching a pattern

Environment:
    ARM_MRS_CACHE_DIR  Override cache directory (default: <repo_root>/cache)

Exit codes:
    0  success
    1  feature/version not found, or cache missing
"""

import argparse
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT  = SCRIPT_DIR.parent
CACHE_DIR  = Path(os.environ.get('ARM_MRS_CACHE_DIR', str(REPO_ROOT / 'cache')))
FEATURES_CACHE = CACHE_DIR / 'features.json'

VERSION_ORDER = [
    'v8Ap0', 'v8Ap1', 'v8Ap2', 'v8Ap3', 'v8Ap4', 'v8Ap5',
    'v8Ap6', 'v8Ap7', 'v8Ap8', 'v8Ap9',
    'v9Ap0', 'v9Ap1', 'v9Ap2', 'v9Ap3', 'v9Ap4', 'v9Ap5', 'v9Ap6',
]
VERSION_INDEX = {v: i for i, v in enumerate(VERSION_ORDER)}
VERSION_SET   = set(VERSION_ORDER)

# ---------------------------------------------------------------------------
# Cache loading
# ---------------------------------------------------------------------------

def load_features() -> list:
    if not FEATURES_CACHE.exists():
        print('Cache not found. Run: python tools/build_index.py', file=sys.stderr)
        sys.exit(1)
    with open(FEATURES_CACHE) as f:
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
        pass  # staleness check is advisory only

# ---------------------------------------------------------------------------
# AST renderer
# ---------------------------------------------------------------------------

def render_ast(node) -> str:
    """Render an AST node as a compact human-readable expression."""
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
        return f'({node.get("op","?")} {render_ast(node.get("operand", {}))})'
    if t == 'AST.Function':
        args = ', '.join(render_ast(a) for a in node.get('arguments', []))
        return f'{node.get("name","?")}({args})'
    if t == 'Types.Field':
        v = node.get('value', {})
        return f'{v.get("name","?")}.{v.get("field","?")}'
    # Fallback: show type tag
    return f'[{t}]'

# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _collect_implications(node, subject: str, found: list) -> None:
    """
    Recursively walk an AST node.
    Collect all BinaryOp nodes where `subject` appears on either side.
    """
    if not isinstance(node, dict):
        return
    if node.get('_type') == 'AST.BinaryOp':
        expr = render_ast(node)
        if subject in expr:
            found.append(expr)
            return  # don't recurse into sub-expressions that already match
    for v in node.values():
        if isinstance(v, dict):
            _collect_implications(v, subject, found)
        elif isinstance(v, list):
            for item in v:
                _collect_implications(item, subject, found)


def _ast_contains(node, target: str) -> bool:
    """Return True if `target` appears as an AST.Identifier anywhere in node."""
    if not isinstance(node, dict):
        return False
    if node.get('_type') == 'AST.Identifier' and node.get('value') == target:
        return True
    for v in node.values():
        if isinstance(v, dict) and _ast_contains(v, target):
            return True
        if isinstance(v, list):
            for item in v:
                if isinstance(item, dict) and _ast_contains(item, target):
                    return True
    return False


def _check_dep(feat_name: str, target: str, features: list) -> tuple:
    """
    Check whether feat_name requires target.

    Returns (result, explanation) where result is:
      'yes'         — feat_name --> RHS and target is in RHS (sole LHS)
      'conditional' — (feat_name && OTHER) --> target (compound LHS)
      'no'          — target does not appear in any implication from feat_name
    """
    feat = next((f for f in features if f['name'] == feat_name), None)
    if not feat:
        return ('no', f"Feature '{feat_name}' not found.")

    yes_exprs         = []
    conditional_exprs = []

    for c in (feat.get('constraints') or []):
        if not isinstance(c, dict):
            continue
        if c.get('_type') != 'AST.BinaryOp' or c.get('op') != '-->':
            continue
        left  = c.get('left',  {})
        right = c.get('right', {})

        lhs_is_sole = (left.get('_type') == 'AST.Identifier'
                       and left.get('value') == feat_name)
        target_in_rhs = _ast_contains(right, target)
        target_in_lhs = _ast_contains(left, target)

        if lhs_is_sole and target_in_rhs:
            yes_exprs.append(render_ast(c))
        elif target_in_lhs or target_in_rhs:
            conditional_exprs.append(render_ast(c))

    if yes_exprs:
        return ('yes', yes_exprs[0])
    if conditional_exprs:
        return ('conditional', conditional_exprs[0])
    return ('no', '')

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_lookup(feat_name: str, features: list) -> int:
    """Show a single feature entry with rendered constraints."""
    feat = next((f for f in features if f['name'] == feat_name), None)
    if not feat:
        close = [f['name'] for f in features if feat_name.lower() in f['name'].lower()]
        print(f"Feature '{feat_name}' not found.", file=sys.stderr)
        if close:
            print(f"Similar names: {', '.join(close[:10])}", file=sys.stderr)
        return 1

    print(f"Feature      : {feat['name']}")
    print(f"Type         : {feat['type']}")
    print(f"Min version  : {feat['min_version'] or '(no version constraint)'}")
    print()

    constraints = feat.get('constraints') or []
    if constraints:
        print(f"Constraints ({len(constraints)}):")
        for c in constraints:
            print(f"  {render_ast(c)}")
    else:
        print("Constraints  : (none)")

    print()
    print("Note: description is not available in the BSD MRS release.")
    return 0


def cmd_deps(feat_name: str, target: str | None, features: list) -> int:
    """
    Show dependency information for a feature.
    If --deps TARGET is given, answer yes/no for the specific edge first.
    """
    feat = next((f for f in features if f['name'] == feat_name), None)
    if not feat:
        print(f"Feature '{feat_name}' not found.", file=sys.stderr)
        return 1

    constraints = feat.get('constraints') or []

    # Collect all constraint expressions that mention this feature
    all_exprs = []
    for c in constraints:
        _collect_implications(c, feat_name, all_exprs)

    if target:
        result, explanation = _check_dep(feat_name, target, features)
        if result == 'yes':
            print(f"Yes: {feat_name} requires {target}.")
            print(f"  via: {explanation}")
        elif result == 'conditional':
            print(f"Conditional: {target} appears in a compound constraint of {feat_name}.")
            print(f"  via: {explanation}")
        else:
            print(f"No: {feat_name} does not constrain {target}.")
        print()

    # Show the full constraint tree
    print(f"All constraints referencing {feat_name} ({len(all_exprs)}):")
    if all_exprs:
        for expr in all_exprs:
            print(f"  {expr}")
    else:
        print("  (none)")

    print()
    print(f"Min version  : {feat['min_version'] or '(no version constraint)'}")
    return 0


def cmd_version(version: str, features: list) -> int:
    """List all features introduced at or before the given version."""
    if version not in VERSION_SET:
        print(f"Unknown version '{version}'.", file=sys.stderr)
        print(f"Known versions: {', '.join(VERSION_ORDER)}", file=sys.stderr)
        return 1

    ceiling = VERSION_INDEX[version]
    in_range = [
        f for f in features
        if f['name'].startswith('FEAT_')
        and f['min_version'] is not None
        and VERSION_INDEX[f['min_version']] <= ceiling
    ]

    # Group by version
    by_version: dict = {}
    for f in in_range:
        by_version.setdefault(f['min_version'], []).append(f['name'])

    total = sum(len(v) for v in by_version.values())
    print(f"Features introduced at or before {version}: {total}\n")

    for ver in VERSION_ORDER:
        if ver not in by_version:
            continue
        names = sorted(by_version[ver])
        print(f"{ver} ({len(names)}):")
        for name in names:
            print(f"  {name}")
        print()

    no_version = [f['name'] for f in features if f['name'].startswith('FEAT_') and not f['min_version']]
    if no_version:
        print(f"Note: {len(no_version)} FEAT_* parameters have no version constraint "
              f"and are not listed above.")
    return 0


def cmd_list(pattern: str, features: list) -> int:
    """List feature names matching a pattern (case-insensitive)."""
    matches = [f['name'] for f in features if pattern.lower() in f['name'].lower()]
    if not matches:
        print(f"No features matching '{pattern}'.", file=sys.stderr)
        return 1
    for name in sorted(matches):
        print(name)
    print(f"\n({len(matches)} results)")
    return 0

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Query ARM architecture features from the MRS cache.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  query_feature.py FEAT_SVE
  query_feature.py FEAT_SVE --deps FEAT_FP16
  query_feature.py --version v9Ap2
  query_feature.py --list SVE
""",
    )
    parser.add_argument('feature',      nargs='?',       help='Feature name (e.g. FEAT_SVE)')
    parser.add_argument('--deps',       metavar='TARGET', help='Check dependency on TARGET feature')
    parser.add_argument('--version',    metavar='VER',    help='List features at or before version')
    parser.add_argument('--list',       metavar='PATTERN',help='List feature names matching pattern')
    args = parser.parse_args()

    check_staleness()
    features = load_features()

    if args.list:
        return cmd_list(args.list, features)

    if args.version:
        return cmd_version(args.version, features)

    if args.feature:
        if args.deps is not None:
            return cmd_deps(args.feature, args.deps, features)
        return cmd_lookup(args.feature, features)

    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
