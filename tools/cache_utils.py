#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cache_utils.py -- Shared cache path resolution, staleness checking, and AST rendering.

All query_*.py scripts import from this module to avoid duplication.

Environment:
    ARM_MRS_CACHE_DIR  Override cache directory (default: <repo_root>/cache)
"""

import hashlib
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT  = SCRIPT_DIR.parent
CACHE_DIR  = Path(os.environ.get('ARM_MRS_CACHE_DIR', str(REPO_ROOT / 'cache')))

ARM_ARM_CACHE = CACHE_DIR / 'arm_arm'

# ---------------------------------------------------------------------------
# Staleness checking
# ---------------------------------------------------------------------------

def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def check_staleness(isa: str = 'a64') -> None:
    """
    Check whether any source files have changed since the cache was built.
    Prints a warning to stderr for each stale file; never raises.

    For T32/A32 ISAs, the arm_arm manifest is consulted if it exists; otherwise
    the main manifest is used as a fallback.
    """
    manifest_path = CACHE_DIR / 'manifest.json'
    if not manifest_path.exists():
        return
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)

        if isa in ('t32', 'a32'):
            arm_arm_manifest_path = ARM_ARM_CACHE / 'manifest.json'
            if arm_arm_manifest_path.exists():
                with open(arm_arm_manifest_path) as f:
                    sources = json.load(f).get('sources', {})
            else:
                sources = manifest.get('sources', {})
        else:
            sources = manifest.get('sources', {})

        for fname, info in sources.items():
            src = Path(info.get('path', str(REPO_ROOT / fname)))
            if not src.exists():
                continue
            if _hash_file(src) != info.get('sha256'):
                builder = 'tools/build_arm_arm_index.py' if isa in ('t32', 'a32') else 'tools/build_index.py'
                print(
                    f'Warning: {fname} has changed since cache was built. '
                    f'Consider re-running {builder}',
                    file=sys.stderr,
                )
    except Exception:
        pass  # staleness check is advisory only


# ---------------------------------------------------------------------------
# AST renderer
# ---------------------------------------------------------------------------

def render_ast(node) -> str:
    """Convert a nested AST dict (from Features.json / Registers.json) to a
    human-readable expression string."""
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
        return f'({node.get("op", "?")} {render_ast(expr)})'
    if t == 'AST.Function':
        args = ', '.join(render_ast(a) for a in node.get('arguments', []))
        return f'{node.get("name", "?")}({args})'
    if t == 'Types.Field':
        v = node.get('value', {})
        return f'{v.get("name", "?")}.{v.get("field", "?")}'
    if t == 'AST.DotAtom':
        vals = node.get('values', [])
        return '.'.join(render_ast(v) for v in vals)
    if t == 'AST.Set':
        vals = node.get('values', [])
        return '{' + ', '.join(render_ast(v) for v in vals) + '}'
    if t in ('Values.Value', 'Values.Group'):
        return node.get('value', '?')
    return f'[{t}]'
