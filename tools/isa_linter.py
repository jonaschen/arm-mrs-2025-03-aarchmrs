#!/usr/bin/env python3
"""
isa_linter.py — Linter-in-the-loop for AArch64 assembly (Milestone H7).

Provides 50 AArch64-specific lint rules sourced from H6 security patterns
and the ARM Architecture Reference Manual.  Supports an optional VIXL
external linter backend and includes an auto-repair suggestion generator.

Usage:
    isa_linter.py --lint FILE [--arch VERSION] [--category CAT] [--output json|text]
    isa_linter.py --lint-stdin [--arch VERSION] [--category CAT] [--output json|text]
    isa_linter.py --list-rules [--category CAT] [--output json|text]
    isa_linter.py --check-vixl
    isa_linter.py --lint-green FILE [--arch VERSION]

Exit codes:
    0  success / lint-green pass
    1  invalid arguments or lint-green failure (errors found)
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Import H6 (isa_optimize) security rules and H1 (query_allowlist) APIs
# ---------------------------------------------------------------------------

_TOOLS_DIR = Path(__file__).parent.resolve()
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from isa_optimize import (                # noqa: E402
    SECURITY_RULES,
    list_security_rules,
)
from query_allowlist import (             # noqa: E402
    VERSION_ORDER,
    VERSION_SET,
)

SCHEMA_VERSION = '1.0'

# AArch64 SP alignment requirement (bytes)
SP_ALIGNMENT = 16

# Maximum distance (in instructions) between flag-setting instruction and
# conditional branch before triggering a stale-flags warning (L34).
MAX_FLAG_DISTANCE = 5

# Never-match regex — used for security rules that are advisory-only and
# have no simple line-level pattern (they require whole-function analysis).
_NEVER_MATCH = r'^\b$'

# ---------------------------------------------------------------------------
# Architecture version helpers (re-used from H1)
# ---------------------------------------------------------------------------

VERSION_INDEX = {v: i for i, v in enumerate(VERSION_ORDER)}


def _arch_at_or_above(target: str, minimum: str) -> bool:
    """Return True if *target* is at or above *minimum* in VERSION_ORDER."""
    t = VERSION_INDEX.get(target)
    m = VERSION_INDEX.get(minimum)
    if t is None or m is None:
        return True  # if unknown, do not filter
    return t >= m


# Pre-compiled regex for conditional branch detection (used in hot loop)
_RE_COND_BRANCH = re.compile(r'(?i)^b\.\w+')


# ═══════════════════════════════════════════════════════════════════════════
# LINT RULE DEFINITIONS  (H7-2)
# ═══════════════════════════════════════════════════════════════════════════

# Map H6 security rule IDs → lint rule IDs
_H6_TO_LINT = {
    'R01': 'L01', 'R02': 'L02', 'R03': 'L03', 'R04': 'L04', 'R05': 'L05',
    'R06': 'L06', 'R07': 'L07', 'R08': 'L08', 'R09': 'L09', 'R10': 'L10',
    'R11': 'L11', 'R12': 'L12', 'R13': 'L13', 'R14': 'L14', 'R15': 'L15',
    'R16': 'L16', 'R17': 'L17', 'R18': 'L18',
}

# Category mapping from H6 categories to lint severity
_H6_CAT_SEVERITY = {
    'pac': 'warning',
    'bti': 'warning',
    'mte': 'warning',
    'general': 'info',
}

# Regex patterns for security rules: detect non-leaf functions without PAC/BTI
_SECURITY_PATTERNS = {
    'L01': r'(?i)^\s*(?:stp\s+x29\s*,\s*x30|push\s)',
    'L02': r'(?i)^\s*ret\b',
    'L03': r'(?i)^\s*(?:pacibsp|pacda|pacdb)\b',
    'L04': r'(?i)^\s*(?:ldr|ldp)\s+x\d+.*(?:blr|br)\s',
    'L05': r'(?i)^\s*(?:retaa|retab)\b',
    'L06': r'(?i)^\s*(?:bti\s+c|bti\s+jc)\b',
    'L07': r'(?i)^\s*(?:bti\s+j)\b',
    'L08': r'(?i)^\s*\..*gp\b',
    'L09': r'(?i)^\s*paciasp\b',
    'L10': r'(?i)^\s*(?:bti\s+c|bti\s+j|bti\s+jc)\b',
    'L11': r'(?i)^\s*(?:irg|stg)\b',
    'L12': r'(?i)^\s*(?:stg|st2g)\b',
    'L13': r'(?i)^\s*stg\b',
    'L14': r'(?i)^\s*msr\s+sctlr_el1\b',
    'L15': r'(?i)^\s*addg\b',
    'L16': r'(?i)^\s*(?:irg|stg)\b.*(?:sp|stack)',
    'L17': r'(?i)^\s*(?:paciasp|bti|irg|stg)\b',
    'L18': r'(?i)^\s*paciasp\b',
}


def _build_security_lint_rules() -> list[dict]:
    """Convert H6 SECURITY_RULES into lint rule format."""
    rules = []
    for sr in SECURITY_RULES:
        lid = _H6_TO_LINT[sr['id']]
        cat = sr['category']
        rules.append({
            'id': lid,
            'category': 'security',
            'title': sr['title'],
            'description': sr['description'],
            'pattern': _SECURITY_PATTERNS.get(lid, _NEVER_MATCH),
            'repair': f"Apply {sr['instruction']} as recommended by rule {sr['id']}.",
            'severity': _H6_CAT_SEVERITY.get(cat, 'warning'),
            'min_arch': sr['min_arch'],
            'source': f"H6-{sr['id']}",
        })
    return rules


# Category 2: alignment (L19-L26)
_ALIGNMENT_RULES: list[dict] = [
    {
        'id': 'L19',
        'category': 'alignment',
        'title': 'LDP/STP pair must use SP-relative or 16-byte aligned base',
        'description': 'LDP and STP with a non-SP base register should ensure '
                       'the base address is 16-byte aligned to avoid alignment faults.',
        'pattern': r'(?i)^\s*(?:ldp|stp)\s+.*\[\s*x\d+\b',
        'repair': 'Ensure the base register is SP or a 16-byte aligned address.',
        'severity': 'warning',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM C6.2 LDP/STP',
    },
    {
        'id': 'L20',
        'category': 'alignment',
        'title': 'SP modification must maintain 16-byte alignment',
        'description': 'Modifications to SP must keep it 16-byte aligned. '
                       'The immediate offset must be a multiple of 16.',
        'pattern': r'(?i)^\s*(?:sub|add)\s+sp\s*,\s*sp\s*,\s*#\s*(\d+)',
        'repair': 'Use an immediate value that is a multiple of 16 for SP adjustments.',
        'severity': 'error',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM B1.1 SP alignment',
    },
    {
        'id': 'L21',
        'category': 'alignment',
        'title': 'Atomic instructions require naturally aligned address',
        'description': 'LDXR, STXR, CAS, and SWP instructions require the address '
                       'to be naturally aligned to the access size.',
        'pattern': r'(?i)^\s*(?:ldxr|stxr|ldaxr|stlxr|cas[a-z]*|swp[a-z]*)\s+',
        'repair': 'Ensure the target address is naturally aligned for the access size.',
        'severity': 'warning',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM B2.2 Atomicity',
    },
    {
        'id': 'L22',
        'category': 'alignment',
        'title': 'STXR status register must differ from data and address registers',
        'description': 'In STXR Ws, Xt, [Xn], the status register Ws must not be '
                       'the same as the data register Xt or the base register Xn.',
        'pattern': r'(?i)^\s*(?:stxr|stlxr)\s+',
        'repair': 'Use a distinct register for the STXR status result.',
        'severity': 'error',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM C6.2 STXR',
    },
    {
        'id': 'L23',
        'category': 'alignment',
        'title': 'SVE load/store must use governing predicate',
        'description': 'SVE predicated load/store instructions (LD1, ST1 with Z '
                       'registers) require an explicit governing predicate register.',
        'pattern': r'(?i)^\s*(?:ld1|st1)[bhwd]?\s+\{z\d+',
        'repair': 'Add a governing predicate (e.g., p0/z or p0/m) to the SVE load/store.',
        'severity': 'error',
        'min_arch': 'v9Ap0',
        'source': 'ARM ARM C7 SVE',
    },
    {
        'id': 'L24',
        'category': 'alignment',
        'title': 'Stack push should save even number of registers (STP preferred)',
        'description': 'AArch64 requires SP 16-byte alignment. Saving an odd number '
                       'of registers with STR wastes stack space; use STP to push pairs.',
        'pattern': r'(?i)^\s*str\s+x\d+\s*,\s*\[sp\s*,\s*#-\d+\]!',
        'repair': 'Use STP to push register pairs (e.g., stp x29, x30, [sp, #-16]!).',
        'severity': 'warning',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM PCS stack alignment',
    },
    {
        'id': 'L25',
        'category': 'alignment',
        'title': 'SIMD LDn/STn must specify element arrangement',
        'description': 'SIMD multi-element load/store (LD1/LD2/LD3/LD4, ST1/ST2/ST3/ST4) '
                       'must include the element size arrangement specifier.',
        'pattern': r'(?i)^\s*(?:ld[1234]|st[1234])\s+\{v\d+\}\s*,',
        'repair': 'Add element arrangement (e.g., v0.4s, v0.8b) to SIMD load/store.',
        'severity': 'error',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM C7 SIMD LD/ST',
    },
    {
        'id': 'L26',
        'category': 'alignment',
        'title': 'Literal pool LDR must be within ±1 MB range',
        'description': 'LDR Xt, =literal loads from a literal pool with a '
                       '±1 MB PC-relative offset. Ensure the pool is within range.',
        'pattern': r'(?i)^\s*ldr\s+[xw]\d+\s*,\s*=',
        'repair': 'Place the literal pool close to the referencing LDR or use ADRP+LDR.',
        'severity': 'info',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM C6.2 LDR (literal)',
    },
]

# Category 3: register (L27-L36)
_REGISTER_RULES: list[dict] = [
    {
        'id': 'L27',
        'category': 'register',
        'title': 'XZR/WZR must not be used as writeback base register',
        'description': 'Using XZR or WZR as the base register with pre/post-index '
                       'writeback is UNPREDICTABLE because XZR discards writes.',
        'pattern': r'(?i)^\s*(?:ldr|str|ldp|stp)\w*\s+.*\[\s*(?:xzr|wzr)\s*(?:,\s*#-?\d+\s*)?[\]!]',
        'repair': 'Use a general-purpose register (X0-X28) as base instead of XZR.',
        'severity': 'error',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM C6.2 addressing modes',
    },
    {
        'id': 'L28',
        'category': 'register',
        'title': 'SP must not be used as Rm in data-processing register instructions',
        'description': 'SP (X31 when not in the SP context) must not appear as Rm '
                       'in shifted-register data-processing instructions that '
                       'interpret X31 as XZR.',
        'pattern': r'(?i)^\s*(?:add|sub|and|orr|eor|bic)\s+x\d+\s*,\s*x\d+\s*,\s*sp\b',
        'repair': 'Move SP into a general-purpose register first (mov x_tmp, sp).',
        'severity': 'error',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM C1.2 Register usage',
    },
    {
        'id': 'L29',
        'category': 'register',
        'title': 'LDP/STP writeback base must not overlap destination register',
        'description': 'For LDP/STP with pre/post-index writeback, the base register '
                       'must not be the same as any destination register.',
        'pattern': r'(?i)^\s*(?:ldp|stp)\s+',
        'repair': 'Use a different base register that does not appear in the register list.',
        'severity': 'error',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM C6.2 LDP/STP',
    },
    {
        'id': 'L30',
        'category': 'register',
        'title': 'Exclusive monitor register must differ from data and address registers',
        'description': 'In STXR Ws, Xt, [Xn], Ws must not be the same register as '
                       'Xt or Xn (overlaps with L22 for register-focused context).',
        'pattern': r'(?i)^\s*(?:stxr|stlxr)\s+',
        'repair': 'Choose a distinct status register for the exclusive store.',
        'severity': 'error',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM C6.2 STXR register constraints',
    },
    {
        'id': 'L31',
        'category': 'register',
        'title': 'LR (X30) must be saved before use as scratch or BL',
        'description': 'BL overwrites X30 (LR). If X30 holds a live return address, '
                       'it must be saved to the stack (STP x29, x30) before any BL.',
        'pattern': r'(?i)^\s*bl\s+',
        'repair': 'Save LR with stp x29, x30, [sp, #-16]! before calling BL.',
        'severity': 'warning',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM PCS LR usage',
    },
    {
        'id': 'L32',
        'category': 'register',
        'title': 'X18 (platform register) must not be used as scratch',
        'description': 'X18 is reserved as the platform register on many OSes '
                       '(e.g., shadow call stack on Linux). Do not use it as scratch '
                       'without explicit save/restore.',
        'pattern': r'(?i)^\s*(?:mov|add|sub|ldr|str|orr|eor|and)\s+(?:x18|w18)\b',
        'repair': 'Avoid X18 as scratch. If necessary, save and restore it explicitly.',
        'severity': 'warning',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM / AAPCS64 platform register',
    },
    {
        'id': 'L33',
        'category': 'register',
        'title': 'X29 (frame pointer) must be saved/restored when modified',
        'description': 'Functions that modify X29 must save it in the prologue '
                       '(STP x29, x30, ...) and restore it in the epilogue.',
        'pattern': r'(?i)^\s*(?:mov|add|sub)\s+x29\b',
        'repair': 'Ensure X29 is saved with stp x29, x30 in prologue and restored in epilogue.',
        'severity': 'warning',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM / AAPCS64 frame pointer',
    },
    {
        'id': 'L34',
        'category': 'register',
        'title': 'Conditional branch must not depend on stale NZCV flags',
        'description': 'A conditional branch (B.cond) should not depend on flags '
                       'set more than 5 instructions earlier without re-setting, '
                       'as intervening instructions may modify NZCV.',
        'pattern': r'(?i)^\s*b\.\w+\s+',
        'repair': 'Add an explicit CMP/TST/ADDS/SUBS closer to the conditional branch.',
        'severity': 'info',
        'min_arch': 'v8Ap0',
        'source': 'AArch64 best practice — flag liveness',
    },
    {
        'id': 'L35',
        'category': 'register',
        'title': 'LDPSW destination registers must not overlap',
        'description': 'In LDPSW Xt1, Xt2, [Xn], Xt1 and Xt2 must be different '
                       'registers.',
        'pattern': r'(?i)^\s*ldpsw\s+',
        'repair': 'Use distinct destination registers for LDPSW.',
        'severity': 'error',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM C6.2 LDPSW',
    },
    {
        'id': 'L36',
        'category': 'register',
        'title': 'MOVK requires preceding MOVZ or MOV to initialize register',
        'description': 'MOVK inserts a 16-bit immediate into an existing value. '
                       'The register should first be initialized with MOVZ or MOV.',
        'pattern': r'(?i)^\s*movk\s+',
        'repair': 'Precede MOVK with MOVZ (or MOV) to initialize the register.',
        'severity': 'warning',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM C6.2 MOVK',
    },
]

# Category 4: branch (L37-L44)
_BRANCH_RULES: list[dict] = [
    {
        'id': 'L37',
        'category': 'branch',
        'title': 'Dead code after unconditional branch',
        'description': 'Reachable code immediately after an unconditional branch '
                       '(B, RET, BR, BLR) without an intervening label is dead code.',
        'pattern': r'(?i)^\s*(?:b|ret|br|blr)\s',
        'repair': 'Remove unreachable code or add a label before it.',
        'severity': 'warning',
        'min_arch': 'v8Ap0',
        'source': 'AArch64 best practice — dead code',
    },
    {
        'id': 'L38',
        'category': 'branch',
        'title': 'TBZ/TBNZ bit position must match register width',
        'description': 'TBZ/TBNZ bit position must be 0-31 for W registers and '
                       '0-63 for X registers.',
        'pattern': r'(?i)^\s*(?:tbz|tbnz)\s+',
        'repair': 'Use bit position 0-31 for W registers, 0-63 for X registers.',
        'severity': 'error',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM C6.2 TBZ/TBNZ',
    },
    {
        'id': 'L39',
        'category': 'branch',
        'title': 'CBZ/CBNZ must use correct register width',
        'description': 'CBZ/CBNZ should use W registers for 32-bit tests and '
                       'X registers for 64-bit tests to match intended semantics.',
        'pattern': r'(?i)^\s*(?:cbz|cbnz)\s+',
        'repair': 'Use W register for 32-bit and X register for 64-bit comparisons.',
        'severity': 'info',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM C6.2 CBZ/CBNZ',
    },
    {
        'id': 'L40',
        'category': 'branch',
        'title': 'SVC/HVC/SMC immediate must be in range 0-65535',
        'description': 'The immediate operand for SVC, HVC, and SMC must fit in '
                       'a 16-bit unsigned field (0-65535).',
        'pattern': r'(?i)^\s*(?:svc|hvc|smc)\s+#?\s*(\d+)',
        'repair': 'Use an immediate value between 0 and 65535.',
        'severity': 'error',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM C6.2 SVC/HVC/SMC',
    },
    {
        'id': 'L41',
        'category': 'branch',
        'title': 'ISB should follow writes to system registers affecting execution',
        'description': 'After MSR to system registers that affect instruction '
                       'execution (e.g., SCTLR, TCR, VBAR), an ISB is needed to '
                       'synchronize the new context.',
        'pattern': r'(?i)^\s*msr\s+(?:sctlr|tcr|vbar|ttbr|mair|hcr)',
        'repair': 'Add ISB immediately after the MSR instruction.',
        'severity': 'warning',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM D1.2 System register writes',
    },
    {
        'id': 'L42',
        'category': 'branch',
        'title': 'RET should use X30 (LR) unless explicitly documented',
        'description': 'RET defaults to X30. Using RET with an explicit non-X30 '
                       'target is unusual and should be documented.',
        'pattern': r'(?i)^\s*ret\s+x(?!30\b)\d+',
        'repair': 'Use plain RET (defaults to X30) or document why a non-LR target is used.',
        'severity': 'info',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM C6.2 RET',
    },
    {
        'id': 'L43',
        'category': 'branch',
        'title': 'BLR must not target SP or XZR',
        'description': 'BLR Xn should target a register containing a valid code '
                       'address. SP and XZR are not valid branch targets.',
        'pattern': r'(?i)^\s*blr\s+(?:sp|xzr)\b',
        'repair': 'Use a general-purpose register (X0-X30) containing a code address.',
        'severity': 'error',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM C6.2 BLR',
    },
    {
        'id': 'L44',
        'category': 'branch',
        'title': 'Function must not fall through without explicit return',
        'description': 'A function should not fall through from .text into .data '
                       'or the next function without an explicit RET, B, or BR.',
        'pattern': r'(?i)^\s*\.(?:data|bss|rodata|section\s)',
        'repair': 'Add an explicit RET or B at the end of the function before the section directive.',
        'severity': 'warning',
        'min_arch': 'v8Ap0',
        'source': 'AArch64 best practice — fall-through',
    },
]

# Category 5: encoding (L45-L50)
_ENCODING_RULES: list[dict] = [
    {
        'id': 'L45',
        'category': 'encoding',
        'title': 'ADD/SUB immediate must fit in 12-bit unsigned field (0-4095)',
        'description': 'ADD/SUB with immediate operand requires the value to be '
                       '0-4095, optionally with LSL #12.',
        'pattern': r'(?i)^\s*(?:adds?|subs?)\s+[xw]\d+\s*,\s*[xw]\d+\s*,\s*#\s*(\d+)',
        'repair': 'Use an immediate in range 0-4095 or apply LSL #12 for larger values.',
        'severity': 'error',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM C6.2 ADD/SUB (immediate)',
    },
    {
        'id': 'L46',
        'category': 'encoding',
        'title': 'Logical immediate must be a valid bitmask pattern',
        'description': 'AND, ORR, EOR with immediate require a valid bitmask '
                       'immediate (repeating bit pattern). Not all 64-bit values '
                       'are encodable.',
        'pattern': r'(?i)^\s*(?:ands?|orr|eor)\s+[xw]\d+\s*,\s*[xw]\d+\s*,\s*#',
        'repair': 'Verify the immediate is a valid logical bitmask or load the value into a register.',
        'severity': 'warning',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM C6.2 Logical (immediate)',
    },
    {
        'id': 'L47',
        'category': 'encoding',
        'title': 'Shift amount must match register width',
        'description': 'LSL/LSR/ASR shift amount must be 0-63 for X registers '
                       'and 0-31 for W registers.',
        'pattern': r'(?i)^\s*(?:lsl|lsr|asr|ror)\s+[xw]\d+\s*,\s*[xw]\d+\s*,\s*#\s*(\d+)',
        'repair': 'Use shift amount 0-31 for W registers, 0-63 for X registers.',
        'severity': 'error',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM C6.2 shift instructions',
    },
    {
        'id': 'L48',
        'category': 'encoding',
        'title': 'MOVZ/MOVN/MOVK immediate must be 16-bit (0-65535)',
        'description': 'MOVZ, MOVN, and MOVK immediate operand must fit in '
                       'a 16-bit field (0-65535).',
        'pattern': r'(?i)^\s*(?:movz|movn|movk)\s+[xw]\d+\s*,\s*#\s*(\d+)',
        'repair': 'Use an immediate value between 0 and 65535.',
        'severity': 'error',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM C6.2 MOVZ/MOVN/MOVK',
    },
    {
        'id': 'L49',
        'category': 'encoding',
        'title': 'UBFM/SBFM/BFM immr and imms must be in range for register width',
        'description': 'For bitfield instructions, immr and imms must be 0-63 for '
                       'X registers and 0-31 for W registers.',
        'pattern': r'(?i)^\s*(?:ubfm|sbfm|bfm)\s+',
        'repair': 'Use immr/imms 0-31 for W registers, 0-63 for X registers.',
        'severity': 'error',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM C6.2 UBFM/SBFM/BFM',
    },
    {
        'id': 'L50',
        'category': 'encoding',
        'title': 'MSR/MRS system register must be recognized',
        'description': 'MSR and MRS should use recognized AArch64 system register '
                       'names. Unrecognized names may indicate a typo or missing '
                       'feature requirement.',
        'pattern': r'(?i)^\s*(?:msr|mrs)\s+',
        'repair': 'Verify the system register name against the AArch64 system register list.',
        'severity': 'info',
        'min_arch': 'v8Ap0',
        'source': 'ARM ARM D12 System register encoding',
    },
]


def _build_all_lint_rules() -> list[dict]:
    """Assemble the complete list of 50 lint rules."""
    rules: list[dict] = []
    rules.extend(_build_security_lint_rules())
    rules.extend(_ALIGNMENT_RULES)
    rules.extend(_REGISTER_RULES)
    rules.extend(_BRANCH_RULES)
    rules.extend(_ENCODING_RULES)
    return rules


LINT_RULES: list[dict] = _build_all_lint_rules()

# Quick lookup by ID
_RULES_BY_ID: dict[str, dict] = {r['id']: r for r in LINT_RULES}

# All categories
LINT_CATEGORIES = ['security', 'alignment', 'register', 'branch', 'encoding']


def list_lint_rules(category: str | None = None) -> list[dict]:
    """Return lint rules, optionally filtered by category."""
    if category:
        return [r for r in LINT_RULES if r['category'] == category]
    return list(LINT_RULES)


# ═══════════════════════════════════════════════════════════════════════════
# VIXL INTEGRATION INTERFACE  (H7-1)
# ═══════════════════════════════════════════════════════════════════════════

def check_vixl() -> dict:
    """Check for VIXL linter or compatible tools on PATH.

    Returns a dict with 'available', 'version', 'path', and 'tool' keys.
    """
    # Try vixl-lint first
    vixl_path = shutil.which('vixl-lint')
    if vixl_path:
        version = 'unknown'
        try:
            proc = subprocess.run(
                ['vixl-lint', '--version'],
                capture_output=True, text=True, timeout=5,
            )
            version = proc.stdout.strip() or proc.stderr.strip() or 'unknown'
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return {
            'available': True,
            'tool': 'vixl-lint',
            'version': version,
            'path': vixl_path,
        }

    # Fallback: aarch64-linux-gnu-objdump for syntax validation
    objdump_path = shutil.which('aarch64-linux-gnu-objdump')
    if objdump_path:
        version = 'unknown'
        try:
            proc = subprocess.run(
                ['aarch64-linux-gnu-objdump', '--version'],
                capture_output=True, text=True, timeout=5,
            )
            first_line = proc.stdout.split('\n')[0] if proc.stdout else ''
            version = first_line.strip() or 'unknown'
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return {
            'available': True,
            'tool': 'aarch64-linux-gnu-objdump',
            'version': version,
            'path': objdump_path,
        }

    return {
        'available': False,
        'tool': None,
        'version': None,
        'path': None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# ASSEMBLY PARSER & LINTER ENGINE  (H7-2)
# ═══════════════════════════════════════════════════════════════════════════

def _strip_comments(line: str) -> str:
    """Remove assembly comments (// and /* */ inline) from a line."""
    # Remove // style comments
    idx = line.find('//')
    if idx >= 0:
        line = line[:idx]
    # Remove /* */ inline comments
    line = re.sub(r'/\*.*?\*/', '', line)
    return line


def _strip_label(line: str) -> str:
    """Remove leading labels from a line (e.g., 'label:  mov x0, x1')."""
    m = re.match(r'^(\s*\w+\s*:)\s*(.*)', line)
    if m:
        return m.group(2)
    return line


def _extract_mnemonic(line: str) -> str | None:
    """Extract the instruction mnemonic from a cleaned assembly line."""
    stripped = line.strip()
    if not stripped or stripped.startswith('.') or stripped.startswith('#'):
        return None
    m = re.match(r'([a-zA-Z][a-zA-Z0-9_.]*)', stripped)
    return m.group(1).lower() if m else None


def _check_sp_alignment(line: str) -> bool:
    """Check if SP modification uses a non-16-aligned immediate."""
    m = re.match(
        r'(?i)^\s*(?:sub|add)\s+sp\s*,\s*sp\s*,\s*#\s*(\d+)',
        line,
    )
    if m:
        imm = int(m.group(1))
        return (imm % SP_ALIGNMENT) != 0
    return False


def _check_svc_range(line: str) -> bool:
    """Check if SVC/HVC/SMC immediate is out of 16-bit range."""
    m = re.match(r'(?i)^\s*(?:svc|hvc|smc)\s+#?\s*(\d+)', line)
    if m:
        imm = int(m.group(1))
        return imm > 65535
    return False


def _check_add_sub_imm(line: str) -> bool:
    """Check if ADD/SUB immediate exceeds 12-bit range without shift."""
    m = re.match(
        r'(?i)^\s*(?:adds?|subs?)\s+[xw]\d+\s*,\s*(?:[xw]\d+|sp)\s*,\s*#\s*(\d+)(?:\s*,\s*lsl\s*#\s*(\d+))?',
        line,
    )
    if m:
        imm = int(m.group(1))
        shift = int(m.group(2)) if m.group(2) else 0
        if shift == 0:
            return imm > 4095
        elif shift == 12:
            return imm > 4095
        else:
            return True  # invalid shift, only 0 and 12 allowed
    return False


def _check_shift_amount(line: str) -> bool:
    """Check if shift amount exceeds register width."""
    m = re.match(
        r'(?i)^\s*(?:lsl|lsr|asr|ror)\s+([xw])\d+\s*,\s*[xw]\d+\s*,\s*#\s*(\d+)',
        line,
    )
    if m:
        reg_type = m.group(1).lower()
        amount = int(m.group(2))
        max_shift = 63 if reg_type == 'x' else 31
        return amount > max_shift
    return False


def _check_mov_imm(line: str) -> bool:
    """Check if MOVZ/MOVN/MOVK immediate exceeds 16-bit range."""
    m = re.match(
        r'(?i)^\s*(?:movz|movn|movk)\s+[xw]\d+\s*,\s*#\s*(\d+)',
        line,
    )
    if m:
        imm = int(m.group(1))
        return imm > 65535
    return False


def _check_tbz_bit(line: str) -> bool:
    """Check if TBZ/TBNZ bit position exceeds register width."""
    m = re.match(
        r'(?i)^\s*(?:tbz|tbnz)\s+([xw])(\d+)\s*,\s*#?\s*(\d+)',
        line,
    )
    if m:
        reg_type = m.group(1).lower()
        bit_pos = int(m.group(3))
        max_bit = 63 if reg_type == 'x' else 31
        return bit_pos > max_bit
    return False


def _check_stxr_overlap(line: str) -> bool:
    """Check if STXR status register overlaps data or base register."""
    m = re.match(
        r'(?i)^\s*(?:stxr|stlxr)\s+w(\d+)\s*,\s*[xw](\d+)\s*,\s*\[x(\d+)',
        line,
    )
    if m:
        ws = int(m.group(1))
        xt = int(m.group(2))
        xn = int(m.group(3))
        return ws == xt or ws == xn
    return False


def _check_ldpsw_overlap(line: str) -> bool:
    """Check if LDPSW destination registers overlap."""
    m = re.match(
        r'(?i)^\s*ldpsw\s+x(\d+)\s*,\s*x(\d+)',
        line,
    )
    if m:
        return m.group(1) == m.group(2)
    return False


def _check_ldp_writeback_overlap(line: str) -> bool:
    """Check if LDP writeback base overlaps destination registers."""
    m = re.match(
        r'(?i)^\s*ldp\s+x(\d+)\s*,\s*x(\d+)\s*,\s*\[x(\d+)(?:\s*,\s*#-?\d+)?\]!',
        line,
    )
    if m:
        d1, d2, base = m.group(1), m.group(2), m.group(3)
        return base == d1 or base == d2
    return False


def _check_sve_predicate(line: str) -> bool:
    """Check if SVE load/store is missing a governing predicate."""
    m = re.match(
        r'(?i)^\s*(?:ld1|st1)[bhwd]?\s+\{z\d+',
        line,
    )
    if not m:
        return False
    # Look for a predicate register (p0-p15) with qualifier (/z or /m)
    has_predicate = bool(re.search(r'(?i)\bp\d+/[zm]\b', line))
    return not has_predicate


# Semantic validators keyed by rule ID.
# Each callable returns True if the violation is confirmed on the given line.
_SEMANTIC_CHECKS: dict = {
    'L20': _check_sp_alignment,
    'L22': _check_stxr_overlap,
    'L29': _check_ldp_writeback_overlap,
    'L30': _check_stxr_overlap,
    'L35': _check_ldpsw_overlap,
    'L38': _check_tbz_bit,
    'L40': _check_svc_range,
    'L45': _check_add_sub_imm,
    'L47': _check_shift_amount,
    'L48': _check_mov_imm,
}


def lint_assembly(
    text: str,
    arch: str | None = None,
    categories: list[str] | None = None,
) -> list[dict]:
    """Lint AArch64 assembly text and return a list of violations.

    Args:
        text: Assembly source text.
        arch: Target architecture version (e.g. 'v9Ap0'). If given, only
              rules whose min_arch is at or below this version are applied.
        categories: Optional list of categories to check. If None, all
                    categories are checked.

    Returns:
        List of violation dicts with keys: line, column, rule_id,
        severity, message, source_line, repair.
    """
    if arch and arch not in VERSION_SET:
        raise ValueError(f"Unknown architecture version: {arch}")

    # Filter rules
    active_rules = LINT_RULES
    if categories:
        cat_set = set(categories)
        active_rules = [r for r in active_rules if r['category'] in cat_set]
    if arch:
        active_rules = [
            r for r in active_rules
            if _arch_at_or_above(arch, r['min_arch'])
        ]

    lines = text.split('\n')
    violations: list[dict] = []

    # Track state for multi-line rules
    prev_is_unconditional_branch = False
    prev_line_num = 0
    flag_set_distance: dict[int, int] = {}  # line_num of last flag-setting instruction
    last_flag_set_line = -100

    for line_num_0, raw_line in enumerate(lines):
        line_num = line_num_0 + 1
        cleaned = _strip_comments(raw_line)
        instruction_part = _strip_label(cleaned)
        mnemonic = _extract_mnemonic(instruction_part)

        # Track flag-setting instructions for L34
        if mnemonic and re.match(
            r'(?i)(?:adds|subs|ands|bics|cmp|cmn|tst|ccmp|ccmn|adcs|sbcs)',
            mnemonic,
        ):
            last_flag_set_line = line_num

        # L37: Dead code detection (check if previous was unconditional branch)
        if prev_is_unconditional_branch and mnemonic:
            # Current line has an instruction but previous was unconditional branch
            # Check this is not a label line (labels are branch targets)
            is_label_line = bool(re.match(r'^\s*\w+\s*:', raw_line))
            is_directive = instruction_part.strip().startswith('.')
            if not is_label_line and not is_directive:
                l37 = _RULES_BY_ID.get('L37')
                if l37 and l37 in active_rules:
                    violations.append({
                        'line': line_num,
                        'column': 0,
                        'rule_id': 'L37',
                        'severity': l37['severity'],
                        'message': l37['title'],
                        'source_line': raw_line.rstrip(),
                        'repair': l37['repair'],
                    })

        # Update unconditional branch tracking
        if mnemonic:
            stripped_instr = instruction_part.strip()
            is_plain_b = mnemonic == 'b' and not _RE_COND_BRANCH.match(stripped_instr)
            is_ret_or_br = mnemonic in ('ret', 'br')
            prev_is_unconditional_branch = is_plain_b or is_ret_or_br
        else:
            if cleaned.strip():
                prev_is_unconditional_branch = False

        if not mnemonic:
            continue

        # L34: Conditional branch with stale flags
        if _RE_COND_BRANCH.match(mnemonic) or _RE_COND_BRANCH.match(
            instruction_part.strip()
        ):
            distance = line_num - last_flag_set_line
            if distance > MAX_FLAG_DISTANCE:
                l34 = _RULES_BY_ID.get('L34')
                if l34 and l34 in active_rules:
                    violations.append({
                        'line': line_num,
                        'column': 0,
                        'rule_id': 'L34',
                        'severity': l34['severity'],
                        'message': (
                            f'{l34["title"]} '
                            f'(flags set {distance} instructions ago)'
                        ),
                        'source_line': raw_line.rstrip(),
                        'repair': l34['repair'],
                    })

        # Pattern-based rule matching
        for rule in active_rules:
            rid = rule['id']

            # Skip rules already handled by multi-line logic
            if rid in ('L37', 'L34'):
                continue

            pattern = rule['pattern']
            m = re.match(pattern, instruction_part)
            if not m:
                continue

            # If there is a semantic check, run it; only report if confirmed
            semantic_fn = _SEMANTIC_CHECKS.get(rid)
            if semantic_fn is not None:
                if not semantic_fn(instruction_part):
                    continue

            violations.append({
                'line': line_num,
                'column': 0,
                'rule_id': rid,
                'severity': rule['severity'],
                'message': rule['title'],
                'source_line': raw_line.rstrip(),
                'repair': rule['repair'],
            })

    return violations


# ═══════════════════════════════════════════════════════════════════════════
# AUTO-REPAIR SUGGESTION GENERATOR  (H7-3)
# ═══════════════════════════════════════════════════════════════════════════

def suggest_repairs(violations: list[dict]) -> list[dict]:
    """Map lint violations to specific code edit suggestions.

    For each violation, produces a repair dict with 'line', 'rule_id',
    'original', 'suggested', and 'explanation' fields.
    """
    suggestions: list[dict] = []

    for v in violations:
        rule = _RULES_BY_ID.get(v['rule_id'])
        if not rule:
            continue

        original = v.get('source_line', '').rstrip()
        rid = v['rule_id']
        suggested = original
        explanation = rule['description']

        # Generate context-specific suggestions for key rules
        if rid == 'L20':
            # SP alignment: round up to next SP_ALIGNMENT
            m = re.match(
                r'(?i)^(\s*(?:sub|add)\s+sp\s*,\s*sp\s*,\s*#\s*)(\d+)(.*)',
                original,
            )
            if m:
                imm = int(m.group(2))
                aligned = ((imm + SP_ALIGNMENT - 1) // SP_ALIGNMENT) * SP_ALIGNMENT
                suggested = f'{m.group(1)}{aligned}{m.group(3)}  // FIXME: aligned to {SP_ALIGNMENT}'
                explanation = (
                    f'SP must be 16-byte aligned. Original offset {imm} '
                    f'rounded up to {aligned}.'
                )

        elif rid == 'L22' or rid == 'L30':
            # STXR register overlap
            m = re.match(
                r'(?i)^(\s*(?:stxr|stlxr)\s+)w(\d+)(\s*,\s*[xw]\d+\s*,\s*\[x\d+.*)',
                original,
            )
            if m:
                ws = int(m.group(2))
                # Pick a different register (avoid the same register)
                alt = ws + 1 if ws < 29 else 0
                suggested = f'{m.group(1)}w{alt}{m.group(3)}  // FIXME: avoid register overlap'
                explanation = (
                    'STXR status register must differ from data and base registers. '
                    f'Changed w{ws} to w{alt}.'
                )

        elif rid == 'L24':
            # STR to STP conversion
            m = re.match(
                r'(?i)^(\s*)str\s+(x\d+)\s*,\s*\[sp\s*,\s*#(-?\d+)\]!(.*)',
                original,
            )
            if m:
                indent = m.group(1)
                reg = m.group(2)
                suggested = (
                    f'{indent}stp {reg}, xzr, [sp, #-16]!'
                    f'{m.group(4)}  // FIXME: pair with another register'
                )
                explanation = (
                    'Prefer STP to push register pairs for SP alignment. '
                    'Pair with another register instead of XZR if possible.'
                )

        elif rid == 'L27':
            # XZR as base
            suggested = re.sub(
                r'(?i)\bxzr\b', 'x1', original,
            ) + '  // FIXME: replace xzr with valid base register'
            explanation = (
                'XZR always reads as zero; writeback to XZR is '
                'architecturally UNPREDICTABLE.'
            )

        elif rid == 'L35':
            # LDPSW overlap
            m = re.match(
                r'(?i)^(\s*ldpsw\s+x)(\d+)(\s*,\s*x)(\d+)(.*)',
                original,
            )
            if m and m.group(2) == m.group(4):
                reg_num = int(m.group(2))
                alt = reg_num + 1 if reg_num < 29 else 0
                suggested = (
                    f'{m.group(1)}{m.group(2)}{m.group(3)}{alt}'
                    f'{m.group(5)}  // FIXME: use distinct destination registers'
                )
                explanation = 'LDPSW destination registers must not overlap.'

        elif rid == 'L40':
            # SVC range
            m = re.match(
                r'(?i)^(\s*(?:svc|hvc|smc)\s+#?\s*)(\d+)(.*)',
                original,
            )
            if m:
                suggested = f'{m.group(1)}0{m.group(3)}  // FIXME: original {m.group(2)} exceeds 16-bit range'
                explanation = (
                    f'SVC/HVC/SMC immediate must be 0-65535. '
                    f'Original value {m.group(2)} is out of range.'
                )

        elif rid == 'L41':
            # Missing ISB after MSR
            suggested = original + '\n    isb  // FIXME: synchronize system register write'
            explanation = (
                'Writes to system registers that affect instruction '
                'execution require an ISB to synchronize.'
            )

        elif rid == 'L43':
            # BLR to SP/XZR
            suggested = re.sub(
                r'(?i)\b(?:sp|xzr)\b', 'x0', original,
            ) + '  // FIXME: use register with valid code address'
            explanation = 'BLR must target a register containing a valid code address.'

        elif rid == 'L45':
            # ADD/SUB immediate out of range
            m = re.match(
                r'(?i)^(\s*(?:adds?|subs?)\s+[xw]\d+\s*,\s*(?:[xw]\d+|sp)\s*,\s*#\s*)(\d+)(.*)',
                original,
            )
            if m:
                imm = int(m.group(2))
                if imm > 4095 and imm <= (4095 << 12):
                    shifted = imm >> 12
                    suggested = f'{m.group(1)}{shifted}, lsl #12{m.group(3)}  // FIXME: use shifted immediate'
                else:
                    suggested = original + '  // FIXME: load immediate into register first'
                explanation = (
                    f'ADD/SUB immediate {imm} exceeds 12-bit range (0-4095). '
                    'Use LSL #12 shift or load into a register.'
                )

        elif rid == 'L47':
            # Shift amount out of range
            m = re.match(
                r'(?i)^(\s*(?:lsl|lsr|asr|ror)\s+)([xw])(\d+\s*,\s*[xw]\d+\s*,\s*#\s*)(\d+)(.*)',
                original,
            )
            if m:
                reg_type = m.group(2).lower()
                max_val = 63 if reg_type == 'x' else 31
                suggested = (
                    f'{m.group(1)}{m.group(2)}{m.group(3)}{max_val}'
                    f'{m.group(5)}  // FIXME: clamped to max {max_val}'
                )
                explanation = (
                    f'Shift amount for {"X" if reg_type == "x" else "W"} '
                    f'registers must be 0-{max_val}.'
                )

        elif rid == 'L48':
            # MOV immediate out of range
            m = re.match(
                r'(?i)^(\s*(?:movz|movn|movk)\s+[xw]\d+\s*,\s*#\s*)(\d+)(.*)',
                original,
            )
            if m:
                suggested = f'{m.group(1)}0{m.group(3)}  // FIXME: original {m.group(2)} exceeds 16-bit range'
                explanation = (
                    f'MOVZ/MOVN/MOVK immediate must be 0-65535. '
                    f'Original value {m.group(2)} is out of range.'
                )

        else:
            # Generic repair suggestion
            suggested = original + f'  // FIXME: {rule["repair"]}'

        suggestions.append({
            'line': v['line'],
            'rule_id': rid,
            'original': original,
            'suggested': suggested,
            'explanation': explanation,
        })

    return suggestions


# ═══════════════════════════════════════════════════════════════════════════
# LINT-GREEN VERIFICATION GATE  (H7-4)
# ═══════════════════════════════════════════════════════════════════════════

def lint_green(
    text: str,
    arch: str | None = None,
    strict: bool = True,
) -> dict:
    """Run all lint rules and return a pass/fail summary.

    Args:
        text: Assembly source text.
        arch: Target architecture version.
        strict: If True, warnings also count as failures.

    Returns:
        Dict with 'green' (bool), 'errors', 'warnings', 'info' counts.
    """
    violations = lint_assembly(text, arch=arch)

    errors = sum(1 for v in violations if v['severity'] == 'error')
    warnings = sum(1 for v in violations if v['severity'] == 'warning')
    info = sum(1 for v in violations if v['severity'] == 'info')

    if strict:
        green = errors == 0 and warnings == 0
    else:
        green = errors == 0

    return {
        'green': green,
        'errors': errors,
        'warnings': warnings,
        'info': info,
        'violations': violations,
    }


# ═══════════════════════════════════════════════════════════════════════════
# CLI COMMANDS
# ═══════════════════════════════════════════════════════════════════════════

def cmd_lint(
    filepath: str | None,
    arch: str | None,
    category: str | None,
    output: str,
    from_stdin: bool = False,
) -> int:
    """Lint an assembly file or stdin."""
    if from_stdin:
        text = sys.stdin.read()
        display_name = '<stdin>'
    else:
        if not filepath:
            print('ERROR: --lint requires a file path.', file=sys.stderr)
            return 1
        try:
            text = Path(filepath).read_text()
            display_name = filepath
        except FileNotFoundError:
            print(f'ERROR: File not found: {filepath}', file=sys.stderr)
            return 1

    if arch and arch not in VERSION_SET:
        print(f'ERROR: Unknown architecture version: {arch}', file=sys.stderr)
        print(f'Valid versions: {", ".join(VERSION_ORDER)}', file=sys.stderr)
        return 1

    categories = [category] if category else None
    try:
        violations = lint_assembly(text, arch=arch, categories=categories)
    except ValueError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1

    repairs = suggest_repairs(violations)

    if output == 'json':
        result = {
            'schema_version': SCHEMA_VERSION,
            'file': display_name,
            'arch': arch,
            'category': category,
            'violations': violations,
            'repairs': repairs,
            'stats': {
                'errors': sum(1 for v in violations if v['severity'] == 'error'),
                'warnings': sum(1 for v in violations if v['severity'] == 'warning'),
                'info': sum(1 for v in violations if v['severity'] == 'info'),
                'total': len(violations),
            },
        }
        print(json.dumps(result, indent=2))
        return 0

    # Text output
    errors = sum(1 for v in violations if v['severity'] == 'error')
    warnings = sum(1 for v in violations if v['severity'] == 'warning')
    info_count = sum(1 for v in violations if v['severity'] == 'info')

    hdr = f'AArch64 Assembly Linter ({len(LINT_RULES)} rules)'
    if arch:
        hdr += f'\nArchitecture: {arch}'
    if category:
        hdr += f'\nCategory: {category}'
    print(hdr)
    print('-' * 58)

    if not violations:
        print('  No violations found.')
    else:
        for v in violations:
            severity_tag = v['severity'].upper()
            print(
                f"  {display_name}:{v['line']}: [{severity_tag}] "
                f"{v['rule_id']}: {v['message']}"
            )
            print(f"    > {v['source_line']}")
            print(f"    repair: {v['repair']}")
            print()

    print(f'Results: {errors} error{"s" if errors != 1 else ""}, '
          f'{warnings} warning{"s" if warnings != 1 else ""}, '
          f'{info_count} info')
    status = 'PASS' if errors == 0 else 'FAIL (errors found)'
    print(f'Lint status: {status}')
    return 0


def cmd_list_rules(category: str | None, output: str) -> int:
    """List all 50 lint rules."""
    rules = LINT_RULES
    if category:
        rules = [r for r in rules if r['category'] == category]

    if not rules:
        cat_hint = f" in category '{category}'" if category else ''
        print(f'No rules found{cat_hint}.', file=sys.stderr)
        print(f'Available categories: {", ".join(LINT_CATEGORIES)}',
              file=sys.stderr)
        return 1

    if output == 'json':
        print(json.dumps({
            'schema_version': SCHEMA_VERSION,
            'rules': rules,
            'count': len(rules),
        }, indent=2))
        return 0

    hdr = f'AArch64 Lint Rules ({len(rules)} rules)'
    if category:
        hdr += f' (category: {category})'
    print(hdr)
    print('-' * 58)
    for r in rules:
        print(f"  [{r['id']}] ({r['category']}/{r['severity']}) {r['title']}")
        print(f"       {r['description'][:100]}...")
        print(f"       min: {r['min_arch']}  |  source: {r['source']}")
        print()
    print(f'Rules: {len(rules)}')
    return 0


def cmd_check_vixl(output: str) -> int:
    """Check VIXL linter availability."""
    result = check_vixl()

    if output == 'json':
        print(json.dumps(result, indent=2))
        return 0

    print('VIXL Linter Check')
    print('-' * 58)
    if result['available']:
        print(f"  Tool:    {result['tool']}")
        print(f"  Path:    {result['path']}")
        print(f"  Version: {result['version']}")
        print()
        print('Status: AVAILABLE')
    else:
        print('  No VIXL linter or compatible tool found on PATH.')
        print()
        print('  Checked for:')
        print('    - vixl-lint')
        print('    - aarch64-linux-gnu-objdump')
        print()
        print('Status: NOT AVAILABLE (using built-in rule engine)')
    return 0


def cmd_lint_green(filepath: str, arch: str | None, output: str) -> int:
    """Run lint-green verification gate."""
    try:
        text = Path(filepath).read_text()
    except FileNotFoundError:
        print(f'ERROR: File not found: {filepath}', file=sys.stderr)
        return 1

    if arch and arch not in VERSION_SET:
        print(f'ERROR: Unknown architecture version: {arch}', file=sys.stderr)
        return 1

    result = lint_green(text, arch=arch, strict=True)

    if output == 'json':
        out = {
            'schema_version': SCHEMA_VERSION,
            'file': filepath,
            'arch': arch,
            'green': result['green'],
            'errors': result['errors'],
            'warnings': result['warnings'],
            'info': result['info'],
        }
        print(json.dumps(out, indent=2))
        return 0 if result['green'] else 1

    print(f'Lint-Green Gate: {filepath}')
    if arch:
        print(f'Architecture: {arch}')
    print('-' * 58)
    print(f"  Errors:   {result['errors']}")
    print(f"  Warnings: {result['warnings']}")
    print(f"  Info:     {result['info']}")
    print()
    if result['green']:
        print('Result: PASS ✓ (lint-green)')
    else:
        print('Result: FAIL ✗ (errors or warnings found)')
        # Show violations
        for v in result['violations']:
            if v['severity'] in ('error', 'warning'):
                print(
                    f"  line {v['line']}: [{v['severity'].upper()}] "
                    f"{v['rule_id']}: {v['message']}"
                )

    return 0 if result['green'] else 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Linter-in-the-loop for AArch64 assembly (50 rules).',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              isa_linter.py --lint test.s --arch v9Ap0
              isa_linter.py --lint test.s --category alignment --output json
              isa_linter.py --lint-stdin --arch v8Ap0
              isa_linter.py --list-rules
              isa_linter.py --list-rules --category security
              isa_linter.py --check-vixl
              isa_linter.py --lint-green test.s --arch v9Ap4
        """),
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument('--lint', metavar='FILE',
                       help='Lint an assembly file.')
    group.add_argument('--lint-stdin', action='store_true',
                       help='Lint assembly from stdin.')
    group.add_argument('--list-rules', action='store_true',
                       help='List all 50 lint rules.')
    group.add_argument('--check-vixl', action='store_true',
                       help='Check VIXL linter availability.')
    group.add_argument('--lint-green', metavar='FILE',
                       help='Run lint-green gate (exit 0 only if zero errors/warnings).')

    parser.add_argument('--arch', metavar='VERSION',
                        help='Target architecture version (e.g. v9Ap0).')
    parser.add_argument('--category', metavar='CAT',
                        help='Filter rules by category '
                             f'({", ".join(LINT_CATEGORIES)}).')
    parser.add_argument('--output', choices=['text', 'json'], default='text',
                        help='Output format: text (default) or json.')

    args = parser.parse_args()

    # Dispatch
    if args.lint:
        return cmd_lint(args.lint, args.arch, args.category, args.output)

    if args.lint_stdin:
        return cmd_lint(None, args.arch, args.category, args.output,
                        from_stdin=True)

    if args.list_rules:
        return cmd_list_rules(args.category, args.output)

    if args.check_vixl:
        return cmd_check_vixl(args.output)

    if args.lint_green:
        return cmd_lint_green(args.lint_green, args.arch, args.output)

    # No command specified
    parser.print_help()
    return 1


if __name__ == '__main__':
    sys.exit(main())
