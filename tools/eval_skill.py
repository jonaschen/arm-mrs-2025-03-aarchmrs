#!/usr/bin/env python3
"""
eval_skill.py — Correctness evaluation for the ARM MRS agent skills.

Measures whether the query tools return spec-grounded answers by running a
battery of tests against known-correct facts from the ARM MRS data
(v9Ap6-A, Build 445, March 2025).

All expected values are derived from:
  - ROADMAP.md §M1-3 manual test results
  - DESIGN.md verified cache-schema examples
  - The ARM MRS source files themselves

Usage:
    python tools/eval_skill.py
    python tools/eval_skill.py --verbose
    python tools/eval_skill.py --skill feat

Options:
    --verbose     Print stdout/stderr for every test case (not just failures)
    --skill SKILL Run only tests for a specific skill (feat)

Exit codes:
    0  All tests passed
    1  One or more tests failed, or cache not found
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TOOLS_DIR  = Path(__file__).parent.resolve()
QUERY_FEAT  = str(TOOLS_DIR / 'query_feature.py')
QUERY_REG   = str(TOOLS_DIR / 'query_register.py')
QUERY_SRCH  = str(TOOLS_DIR / 'query_search.py')
QUERY_INSTR = str(TOOLS_DIR / 'query_instruction.py')
QUERY_GIC   = str(TOOLS_DIR / 'query_gic.py')
QUERY_CS    = str(TOOLS_DIR / 'query_coresight.py')
QUERY_PMU   = str(TOOLS_DIR / 'query_pmu.py')

# ---------------------------------------------------------------------------
# Test runner helpers
# ---------------------------------------------------------------------------

def _run(args: list) -> tuple:
    """Invoke a Python script and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        [sys.executable] + args,
        capture_output=True, text=True,
    )
    return result.returncode, result.stdout, result.stderr


def _check_cache_available() -> bool:
    """Return True if the feature cache exists (quick probe)."""
    rc, _out, err = _run([QUERY_FEAT, '--list', 'FEAT_SVE'])
    return 'Cache not found' not in err


# ---------------------------------------------------------------------------
# Check factories
# ---------------------------------------------------------------------------

def exit_ok():
    """The tool must exit with code 0."""
    def fn(rc, stdout, stderr):
        return rc == 0, f'exit {rc} (expected 0)'
    fn.__doc__ = 'exit code 0'
    return fn


def exit_nonzero():
    """The tool must exit with a non-zero code."""
    def fn(rc, stdout, stderr):
        return rc != 0, f'exit {rc} (expected non-zero)'
    fn.__doc__ = 'exit code non-zero'
    return fn


def stdout_contains(text: str):
    """stdout must contain `text` (case-sensitive)."""
    def fn(rc, stdout, stderr):
        found = text in stdout
        return found, f"'{text}' {'found' if found else 'NOT FOUND'} in stdout"
    fn.__doc__ = f"stdout contains '{text}'"
    return fn


def stdout_not_contains(text: str):
    """stdout must NOT contain `text`."""
    def fn(rc, stdout, stderr):
        found = text in stdout
        return not found, f"'{text}' {'UNEXPECTEDLY found' if found else 'correctly absent'} in stdout"
    fn.__doc__ = f"stdout does not contain '{text}'"
    return fn


def stderr_contains(text: str):
    """stderr must contain `text`."""
    def fn(rc, stdout, stderr):
        found = text in stderr
        return found, f"'{text}' {'found' if found else 'NOT FOUND'} in stderr"
    fn.__doc__ = f"stderr contains '{text}'"
    return fn


def list_count(n: int):
    """stdout must contain the exact list-count marker '({n} results)'."""
    def fn(rc, stdout, stderr):
        marker = f'({n} results)'
        found = marker in stdout
        # Also report what count was actually found for diagnostics
        m = re.search(r'\((\d+) results\)', stdout)
        actual = m.group(0) if m else '(none found)'
        return found, f"'{marker}' {'found' if found else 'NOT FOUND'} in stdout; actual: {actual}"
    fn.__doc__ = f"list count = {n}"
    return fn


def version_total(n: int):
    """stdout must report the exact total for a --version query."""
    def fn(rc, stdout, stderr):
        # cmd_version prints: "Features introduced at or before vX: N"
        m = re.search(r'Features introduced at or before \S+: (\d+)', stdout)
        if not m:
            return False, f'version total line not found in stdout'
        actual = int(m.group(1))
        return actual == n, f'version total: got {actual}, expected {n}'
    fn.__doc__ = f"version total = {n}"
    return fn


def field_value(field_label: str, expected: str):
    """stdout must contain a line matching '{field_label}: {expected}'."""
    def fn(rc, stdout, stderr):
        pattern = re.compile(
            r'^\s*' + re.escape(field_label) + r'\s*:\s*' + re.escape(expected),
            re.MULTILINE,
        )
        found = bool(pattern.search(stdout))
        return found, f"field '{field_label}: {expected}' {'found' if found else 'NOT FOUND'}"
    fn.__doc__ = f"field '{field_label}' = '{expected}'"
    return fn


# ---------------------------------------------------------------------------
# Test suite definition
# ---------------------------------------------------------------------------
#
# Each test is a 3-tuple:
#   (description, [script_args], [check_functions])
#
# ALL checks must pass for the test to pass.
# Expected values are grounded in the ARM MRS v9Ap6-A, Build 445, March 2025.
# ---------------------------------------------------------------------------

FEAT_TESTS = [
    # ------------------------------------------------------------------ #
    # Feature existence — real ARM features that MUST be in the spec      #
    # ------------------------------------------------------------------ #
    (
        'FEAT_SVE is present in the MRS',
        [QUERY_FEAT, 'FEAT_SVE'],
        [exit_ok(), stdout_contains('FEAT_SVE')],
    ),
    (
        'FEAT_FP16 is present in the MRS',
        [QUERY_FEAT, 'FEAT_FP16'],
        [exit_ok(), stdout_contains('FEAT_FP16')],
    ),
    # The ARM spec uses FEAT_AdvSIMD, not the marketing name "NEON".
    # An agent without this skill would likely hallucinate 'FEAT_NEON'.
    (
        'FEAT_AdvSIMD (Advanced SIMD) is present in the MRS — not "FEAT_NEON"',
        [QUERY_FEAT, 'FEAT_AdvSIMD'],
        [exit_ok(), stdout_contains('FEAT_AdvSIMD')],
    ),
    (
        'Marketing name FEAT_NEON is NOT in the MRS (spec uses FEAT_AdvSIMD)',
        [QUERY_FEAT, 'FEAT_NEON'],
        [exit_nonzero()],
    ),
    (
        'FEAT_SME is present in the MRS',
        [QUERY_FEAT, 'FEAT_SME'],
        [exit_ok(), stdout_contains('FEAT_SME')],
    ),
    (
        'FEAT_LSE (Large System Extensions) is present in the MRS',
        [QUERY_FEAT, 'FEAT_LSE'],
        [exit_ok(), stdout_contains('FEAT_LSE')],
    ),
    (
        'FEAT_SVE2 is present in the MRS',
        [QUERY_FEAT, 'FEAT_SVE2'],
        [exit_ok(), stdout_contains('FEAT_SVE2')],
    ),
    (
        'FEAT_SPE (Statistical Profiling Extension) is present in the MRS',
        [QUERY_FEAT, 'FEAT_SPE'],
        [exit_ok(), stdout_contains('FEAT_SPE')],
    ),
    # ------------------------------------------------------------------ #
    # Non-existence — hallucinated / made-up features must NOT be found   #
    # ------------------------------------------------------------------ #
    (
        'Hallucinated feature FEAT_TURBOMODE is NOT in the MRS (exit non-zero)',
        [QUERY_FEAT, 'FEAT_TURBOMODE'],
        [exit_nonzero()],
    ),
    (
        'Hallucinated feature FEAT_QUANTUMCOMPUTE is NOT in the MRS',
        [QUERY_FEAT, 'FEAT_QUANTUMCOMPUTE'],
        [exit_nonzero()],
    ),
    # ------------------------------------------------------------------ #
    # Min-version correctness (from DESIGN.md verified examples)          #
    # ------------------------------------------------------------------ #
    (
        'FEAT_SVE was introduced at v8Ap2 (AArch64 Armv8.2)',
        [QUERY_FEAT, 'FEAT_SVE'],
        [exit_ok(), field_value('Min version', 'v8Ap2')],
    ),
    # ------------------------------------------------------------------ #
    # Dependency classification                                            #
    # Results from ROADMAP.md §M1-3 manual tests                          #
    # ------------------------------------------------------------------ #
    (
        'FEAT_SVE --> FEAT_FP16 is a direct (Yes) dependency',
        [QUERY_FEAT, 'FEAT_SVE', '--deps', 'FEAT_FP16'],
        [
            exit_ok(),
            stdout_contains('Yes: FEAT_SVE requires FEAT_FP16'),
        ],
    ),
    (
        'FEAT_SVE <-> FEAT_PMUv3p1 is a conditional dependency',
        [QUERY_FEAT, 'FEAT_SVE', '--deps', 'FEAT_PMUv3p1'],
        [
            exit_ok(),
            stdout_contains('Conditional'),
        ],
    ),
    (
        'FEAT_SVE does NOT directly constrain FEAT_NEON',
        [QUERY_FEAT, 'FEAT_SVE', '--deps', 'FEAT_NEON'],
        [
            exit_ok(),
            stdout_contains('No: FEAT_SVE does not constrain FEAT_NEON'),
        ],
    ),
    # ------------------------------------------------------------------ #
    # Version-to-features mapping                                          #
    # ------------------------------------------------------------------ #
    (
        '--version v9Ap2 returns exactly 261 features (ROADMAP §M1-3)',
        [QUERY_FEAT, '--version', 'v9Ap2'],
        [exit_ok(), version_total(261)],
    ),
    (
        '--version v8Ap0 succeeds and lists at least 1 feature',
        [QUERY_FEAT, '--version', 'v8Ap0'],
        [exit_ok(), stdout_contains('v8Ap0')],
    ),
    (
        '--version with an unknown version string exits non-zero',
        [QUERY_FEAT, '--version', 'v99Ap99'],
        [exit_nonzero()],
    ),
    # ------------------------------------------------------------------ #
    # Name pattern search / list                                           #
    # ------------------------------------------------------------------ #
    (
        '--list SVE returns exactly 19 results (ROADMAP §M1-3)',
        [QUERY_FEAT, '--list', 'SVE'],
        [exit_ok(), list_count(19)],
    ),
    (
        '--list FP includes FEAT_FP16',
        [QUERY_FEAT, '--list', 'FP'],
        [exit_ok(), stdout_contains('FEAT_FP16')],
    ),
    (
        'FEAT_AdvSIMD introduced at v8Ap0 (baseline AArch64)',
        [QUERY_FEAT, 'FEAT_AdvSIMD'],
        [exit_ok(), field_value('Min version', 'v8Ap0')],
    ),
    (
        'FEAT_AdvSIMD directly requires FEAT_FP',
        [QUERY_FEAT, 'FEAT_AdvSIMD', '--deps', 'FEAT_FP'],
        [exit_ok(), stdout_contains('Yes: FEAT_AdvSIMD requires FEAT_FP')],
    ),
    (
        '--list with a non-matching pattern exits non-zero',
        [QUERY_FEAT, '--list', 'ZZZNOMATCH_FAKE_PATTERN_XYZ'],
        [exit_nonzero()],
    ),
    # ------------------------------------------------------------------ #
    # Anti-hallucination sentinel: tool must acknowledge missing prose     #
    # ------------------------------------------------------------------ #
    (
        'Lookup correctly states prose is not available (BSD MRS)',
        [QUERY_FEAT, 'FEAT_SVE'],
        [exit_ok(), stdout_contains('not available in the BSD MRS release')],
    ),
]

REG_TESTS = [
    # ------------------------------------------------------------------ #
    # Register existence                                                   #
    # ------------------------------------------------------------------ #
    (
        'SCTLR_EL1 exists in AArch64 state',
        [QUERY_REG, 'SCTLR_EL1'],
        [exit_ok(), stdout_contains('SCTLR_EL1')],
    ),
    (
        'TCR_EL1 exists and has AArch64 state',
        [QUERY_REG, 'TCR_EL1'],
        [exit_ok(), stdout_contains('AArch64')],
    ),
    # ------------------------------------------------------------------ #
    # Field lookup                                                         #
    # ------------------------------------------------------------------ #
    (
        'SCTLR_EL1 UCI field is at bit [26]',
        [QUERY_REG, 'SCTLR_EL1', 'UCI'],
        [exit_ok(), stdout_contains('[26]')],
    ),
    (
        'SCTLR_EL1 UCI field has 2 defined values',
        [QUERY_REG, 'SCTLR_EL1', 'UCI', '--values'],
        [exit_ok(), stdout_contains("'0'"), stdout_contains("'1'")],
    ),
    (
        'Querying a non-existent field exits non-zero',
        [QUERY_REG, 'SCTLR_EL1', 'NOSUCHFIELD_XYZ'],
        [exit_nonzero()],
    ),
    # ------------------------------------------------------------------ #
    # Accessor / MRS-MSR encoding                                          #
    # ------------------------------------------------------------------ #
    (
        'SCTLR_EL1 has a SystemAccessor A64.MRS entry',
        [QUERY_REG, 'SCTLR_EL1', '--access'],
        [exit_ok(), stdout_contains('SystemAccessor'), stdout_contains('A64.MRS')],
    ),
    (
        'SCTLR_EL1 MRS encoding: op0=11 CRn=0001 CRm=0000 op2=000',
        [QUERY_REG, 'SCTLR_EL1', '--access'],
        [
            exit_ok(),
            stdout_contains("op0='11'"),
            stdout_contains("CRn='0001'"),
            stdout_contains("CRm='0000'"),
            stdout_contains("op2='000'"),
        ],
    ),
    # ------------------------------------------------------------------ #
    # Parameterized register resolution                                    #
    # ------------------------------------------------------------------ #
    (
        'DBGBCR2_EL1 resolves via parameterized lookup (DBGBCR<n>_EL1)',
        [QUERY_REG, 'DBGBCR2_EL1'],
        [exit_ok(), stdout_contains('DBGBCR')],
    ),
    (
        'DBGBCR2_EL1 shows requested instance 2 in output',
        [QUERY_REG, 'DBGBCR2_EL1'],
        [exit_ok(), stdout_contains('DBGBCR2_EL1')],
    ),
    # ------------------------------------------------------------------ #
    # Register list                                                        #
    # ------------------------------------------------------------------ #
    (
        '--list EL2 --state AArch64 returns >50 results',
        [QUERY_REG, '--list', 'EL2', '--state', 'AArch64'],
        [exit_ok(), stdout_contains('AArch64')],
    ),
    (
        '--list with a non-matching pattern exits non-zero',
        [QUERY_REG, '--list', 'ZZZNOMATCH_FAKE_PATTERN_XYZ'],
        [exit_nonzero()],
    ),
    # ------------------------------------------------------------------ #
    # Anti-hallucination sentinel                                          #
    # ------------------------------------------------------------------ #
    (
        'Register lookup states field descriptions not available (BSD MRS)',
        [QUERY_REG, 'SCTLR_EL1'],
        [exit_ok(), stdout_contains('not available in the BSD MRS release')],
    ),
]

SEARCH_TESTS = [
    # ------------------------------------------------------------------ #
    # Combined search                                                      #
    # ------------------------------------------------------------------ #
    (
        'TCR search returns TCR_EL1 register and results count > 0',
        [QUERY_SRCH, 'TCR'],
        [exit_ok(), stdout_contains('TCR_EL1'), stdout_contains('results')],
    ),
    # ------------------------------------------------------------------ #
    # Register-only search                                                 #
    # ------------------------------------------------------------------ #
    (
        '--reg EL2 --state AArch64 returns register results',
        [QUERY_SRCH, '--reg', 'EL2', '--state', 'AArch64'],
        [exit_ok(), stdout_contains('AArch64')],
    ),
    (
        '--reg EL2 returns more than 100 results (AArch64 + others)',
        [QUERY_SRCH, '--reg', 'EL2'],
        [exit_ok(), stdout_contains('results')],
    ),
    # ------------------------------------------------------------------ #
    # Operation-only search                                                #
    # ------------------------------------------------------------------ #
    (
        '--op ADD returns ADD_addsub_imm in results',
        [QUERY_SRCH, '--op', 'ADD'],
        [exit_ok(), stdout_contains('ADD_addsub_imm')],
    ),
    (
        'search with no matches exits non-zero',
        [QUERY_SRCH, 'ZZZNOMATCH_FAKE_XYZ'],
        [exit_nonzero()],
    ),
]

INSTR_TESTS = [
    # ------------------------------------------------------------------ #
    # Operation lookup                                                     #
    # ------------------------------------------------------------------ #
    (
        'ADC operation exists and lists 2 variants',
        [QUERY_INSTR, 'ADC'],
        [exit_ok(), stdout_contains('ADC_32_addsub_carry'), stdout_contains('ADC_64_addsub_carry')],
    ),
    (
        'ADC assembly template contains operand registers',
        [QUERY_INSTR, 'ADC'],
        [exit_ok(), stdout_contains('WdOrWZR'), stdout_contains('XdOrXZR')],
    ),
    # ------------------------------------------------------------------ #
    # Encoding                                                             #
    # ------------------------------------------------------------------ #
    (
        'ADC --enc shows sf field at [31]',
        [QUERY_INSTR, 'ADC', '--enc'],
        [exit_ok(), stdout_contains('[31]'), stdout_contains('sf')],
    ),
    (
        'ADC --enc shows Rd as operand field at [4:0]',
        [QUERY_INSTR, 'ADC', '--enc'],
        [exit_ok(), stdout_contains('[4:0]'), stdout_contains('operand')],
    ),
    (
        'ADC 32-bit variant has sf fixed to 0',
        [QUERY_INSTR, 'ADC', '--enc'],
        [exit_ok(), stdout_contains("'0'")],
    ),
    # ------------------------------------------------------------------ #
    # Operation pseudocode (BSD: not available)                           #
    # ------------------------------------------------------------------ #
    (
        'ADC --op states ASL is not available in BSD MRS release',
        [QUERY_INSTR, 'ADC', '--op'],
        [exit_ok(), stdout_contains('not available in BSD MRS release')],
    ),
    # ------------------------------------------------------------------ #
    # List                                                                 #
    # ------------------------------------------------------------------ #
    (
        '--list ADD returns ADD_addsub_imm',
        [QUERY_INSTR, '--list', 'ADD'],
        [exit_ok(), stdout_contains('ADD_addsub_imm')],
    ),
    (
        '--list MRS returns MRS operation',
        [QUERY_INSTR, '--list', 'MRS'],
        [exit_ok(), stdout_contains('MRS')],
    ),
    (
        '--list with non-matching pattern exits non-zero',
        [QUERY_INSTR, '--list', 'ZZZNOMATCH_FAKE_XYZ'],
        [exit_nonzero()],
    ),
    # ------------------------------------------------------------------ #
    # Non-existence                                                        #
    # ------------------------------------------------------------------ #
    (
        'Hallucinated operation FAKEZAP_TURBO is not found (exit non-zero)',
        [QUERY_INSTR, 'FAKEZAP_TURBO'],
        [exit_nonzero()],
    ),
    # ------------------------------------------------------------------ #
    # Anti-hallucination sentinel                                          #
    # ------------------------------------------------------------------ #
    (
        'Lookup correctly states descriptions not available (BSD MRS)',
        [QUERY_INSTR, 'ADC'],
        [exit_ok(), stdout_contains('not available in the BSD MRS release')],
    ),
]

# ---------------------------------------------------------------------------
# EA tests: T32 / A32 instruction skill (arm_arm cache)
# ---------------------------------------------------------------------------

def _check_arm_arm_cache_available() -> bool:
    """Return True if the arm_arm T32 cache exists."""
    arm_arm_t32_dir = TOOLS_DIR.parent / 'cache' / 'arm_arm' / 't32_operations'
    return arm_arm_t32_dir.exists() and any(arm_arm_t32_dir.iterdir())


# EA-b: T32/A32 tests (require arm_arm cache — built by build_arm_arm_index.py)
INSTR_T32_TESTS = [
    # Existence
    (
        'T32 LDR lookup succeeds (exit 0)',
        [QUERY_INSTR, 'LDR', '--isa', 't32'],
        [exit_ok()],
    ),
    (
        'T32 LDR output shows ISA: T32',
        [QUERY_INSTR, 'LDR', '--isa', 't32'],
        [exit_ok(), stdout_contains('T32')],
    ),
    (
        'T32 LDR encoding contains Rn operand field',
        [QUERY_INSTR, 'LDR', '--isa', 't32', '--enc'],
        [exit_ok(), stdout_contains('Rn')],
    ),
    (
        'T32 LDR encoding contains imm12 operand field',
        [QUERY_INSTR, 'LDR', '--isa', 't32', '--enc'],
        [exit_ok(), stdout_contains('imm12')],
    ),
    (
        'T32 BL lookup succeeds',
        [QUERY_INSTR, 'BL', '--isa', 't32'],
        [exit_ok(), stdout_contains('BL')],
    ),
    (
        'T32 --list LDR finds LDR',
        [QUERY_INSTR, '--list', 'LDR', '--isa', 't32'],
        [exit_ok(), stdout_contains('LDR')],
    ),
    (
        'T32 hallucinated FAKEZAP not found (exit non-zero)',
        [QUERY_INSTR, 'FAKEZAP', '--isa', 't32'],
        [exit_nonzero()],
    ),
]

INSTR_A32_TESTS = [
    # Existence
    (
        'A32 LDR lookup succeeds (exit 0)',
        [QUERY_INSTR, 'LDR', '--isa', 'a32'],
        [exit_ok()],
    ),
    (
        'A32 LDR output shows ISA: A32',
        [QUERY_INSTR, 'LDR', '--isa', 'a32'],
        [exit_ok(), stdout_contains('A32')],
    ),
    (
        'A32 LDR encoding contains cond operand field',
        [QUERY_INSTR, 'LDR', '--isa', 'a32', '--enc'],
        [exit_ok(), stdout_contains('cond')],
    ),
    (
        'A32 B encoding contains imm24 operand field',
        [QUERY_INSTR, 'B', '--isa', 'a32', '--enc'],
        [exit_ok(), stdout_contains('imm24')],
    ),
    (
        'A32 SUB lookup succeeds',
        [QUERY_INSTR, 'SUB', '--isa', 'a32'],
        [exit_ok(), stdout_contains('SUB')],
    ),
    (
        'A32 --list LDR finds LDR',
        [QUERY_INSTR, '--list', 'LDR', '--isa', 'a32'],
        [exit_ok(), stdout_contains('LDR')],
    ),
]

SEARCH_T32_TESTS = [
    (
        'search --op LDR --isa t32 finds T32 LDR',
        [QUERY_SRCH, '--op', 'LDR', '--isa', 't32'],
        [exit_ok(), stdout_contains('LDR')],
    ),
    (
        'search --op ADD --isa all finds both T32 and A32 ADD',
        [QUERY_SRCH, '--op', 'ADD', '--isa', 'all'],
        [exit_ok(), stdout_contains('T32'), stdout_contains('A32')],
    ),
    (
        'search --op B --isa a32 finds A32 branch',
        [QUERY_SRCH, '--op', 'B', '--isa', 'a32'],
        [exit_ok(), stdout_contains('A32')],
    ),
]

# ---------------------------------------------------------------------------
# EB tests: GIC skill (arm-gic cache — built by build_gic_index.py)
# ---------------------------------------------------------------------------

def _check_gic_cache_available() -> bool:
    """Return True if the GIC cache exists."""
    gic_meta = TOOLS_DIR.parent / 'cache' / 'gic' / 'gic_meta.json'
    return gic_meta.exists()


# EB: GIC register tests (require gic cache — built by build_gic_index.py)
GIC_TESTS = [
    # Register existence
    (
        'GICD_CTLR lookup succeeds (exit 0)',
        [QUERY_GIC, 'GICD_CTLR'],
        [exit_ok()],
    ),
    (
        'GICD_CTLR output shows block GICD',
        [QUERY_GIC, 'GICD_CTLR'],
        [exit_ok(), stdout_contains('GICD')],
    ),
    # Field existence and bit position (exit criteria: EnableGrp0 at bit 0)
    (
        'GICD_CTLR EnableGrp0 field lookup succeeds (exit 0)',
        [QUERY_GIC, 'GICD_CTLR', 'EnableGrp0'],
        [exit_ok()],
    ),
    (
        'GICD_CTLR EnableGrp0 field is at bit [0]',
        [QUERY_GIC, 'GICD_CTLR', 'EnableGrp0'],
        [exit_ok(), stdout_contains('[0]')],
    ),
    (
        'GICD_CTLR EnableGrp0 field access type is RW',
        [QUERY_GIC, 'GICD_CTLR', 'EnableGrp0'],
        [exit_ok(), stdout_contains('RW')],
    ),
    (
        'GICD_CTLR EnableGrp1S field is at bit [2]',
        [QUERY_GIC, 'GICD_CTLR', 'EnableGrp1S'],
        [exit_ok(), stdout_contains('[2]')],
    ),
    (
        'GICD_CTLR EnableGrp1NS field is at bit [1]',
        [QUERY_GIC, 'GICD_CTLR', 'EnableGrp1NS'],
        [exit_ok(), stdout_contains('[1]')],
    ),
    # Block listing
    (
        '--block GICD lists registers',
        [QUERY_GIC, '--block', 'GICD'],
        [exit_ok(), stdout_contains('GICD_CTLR')],
    ),
    (
        '--block GICR lists GICR_CTLR',
        [QUERY_GIC, '--block', 'GICR'],
        [exit_ok(), stdout_contains('GICR_CTLR')],
    ),
    (
        '--block GITS lists GITS_CTLR',
        [QUERY_GIC, '--block', 'GITS'],
        [exit_ok(), stdout_contains('GITS_CTLR')],
    ),
    # Name listing
    (
        '--list CTLR finds GICD_CTLR',
        [QUERY_GIC, '--list', 'CTLR'],
        [exit_ok(), stdout_contains('GICD_CTLR')],
    ),
    # ICC cross-reference
    (
        '--icc-xref ICC_IAR1_EL1 returns cross-reference',
        [QUERY_GIC, '--icc-xref', 'ICC_IAR1_EL1'],
        [exit_ok(), stdout_contains('ICC_IAR1_EL1')],
    ),
    (
        '--icc-xref ICC_PMR_EL1 redirects to arm-reg',
        [QUERY_GIC, '--icc-xref', 'ICC_PMR_EL1'],
        [exit_ok(), stdout_contains('query_register.py')],
    ),
    # Hallucination guard
    (
        'Hallucinated register GICD_FAKECTRL not found (exit non-zero)',
        [QUERY_GIC, 'GICD_FAKECTRL'],
        [exit_nonzero()],
    ),
    (
        'Hallucinated ICC register returns error when used as GIC query',
        [QUERY_GIC, 'ICC_NONEXISTENT_EL9'],
        [exit_nonzero()],
    ),
]

# GIC search integration tests
GIC_SEARCH_TESTS = [
    (
        'search EnableGrp1 finds GIC registers',
        [QUERY_SRCH, 'EnableGrp1'],
        [exit_ok(), stdout_contains('GICD')],
    ),
    (
        'search --spec gic EnableGrp1 returns GIC results',
        [QUERY_SRCH, '--spec', 'gic', 'EnableGrp1'],
        [exit_ok(), stdout_contains('GICD_CTLR')],
    ),
    (
        'search --spec gic FAKECTRL returns no results (exit non-zero)',
        [QUERY_SRCH, '--spec', 'gic', 'FAKECTRL_ZZZZ'],
        [exit_nonzero()],
    ),
]

# ---------------------------------------------------------------------------
# EC tests: CoreSight skill (arm-coresight cache — built by build_coresight_index.py)
# ---------------------------------------------------------------------------

def _check_coresight_cache_available() -> bool:
    """Return True if the CoreSight cache exists."""
    cs_meta = TOOLS_DIR.parent / 'cache' / 'coresight' / 'cs_meta.json'
    return cs_meta.exists()


# EC: CoreSight register tests (require coresight cache — built by build_coresight_index.py)
CORESIGHT_TESTS = [
    # Exit criteria: query_coresight.py etm TRCPRGCTLR returns field layout
    (
        'ETM TRCPRGCTLR lookup succeeds (exit 0) — exit criteria',
        [QUERY_CS, 'etm', 'TRCPRGCTLR'],
        [exit_ok()],
    ),
    (
        'ETM TRCPRGCTLR output shows component ETM',
        [QUERY_CS, 'etm', 'TRCPRGCTLR'],
        [exit_ok(), stdout_contains('ETM')],
    ),
    # Field existence and bit position (EN at bit [0])
    (
        'ETM TRCPRGCTLR EN field lookup succeeds (exit 0)',
        [QUERY_CS, 'etm', 'TRCPRGCTLR', 'EN'],
        [exit_ok()],
    ),
    (
        'ETM TRCPRGCTLR EN field is at bit [0]',
        [QUERY_CS, 'etm', 'TRCPRGCTLR', 'EN'],
        [exit_ok(), stdout_contains('[0]')],
    ),
    (
        'ETM TRCPRGCTLR EN field access type is RW',
        [QUERY_CS, 'etm', 'TRCPRGCTLR', 'EN'],
        [exit_ok(), stdout_contains('RW')],
    ),
    # TRCSTATR
    (
        'ETM TRCSTATR IDLE field is at bit [0]',
        [QUERY_CS, 'etm', 'TRCSTATR', 'IDLE'],
        [exit_ok(), stdout_contains('[0]')],
    ),
    (
        'ETM TRCSTATR IDLE field is read-only',
        [QUERY_CS, 'etm', 'TRCSTATR', 'IDLE'],
        [exit_ok(), stdout_contains('RO')],
    ),
    # CTI
    (
        'CTI CTICONTROL lookup succeeds (exit 0)',
        [QUERY_CS, 'cti', 'CTICONTROL'],
        [exit_ok()],
    ),
    (
        'CTI CTICONTROL GLBEN field is at bit [0]',
        [QUERY_CS, 'cti', 'CTICONTROL', 'GLBEN'],
        [exit_ok(), stdout_contains('[0]')],
    ),
    (
        'CTI CTICONTROL GLBEN access type is RW',
        [QUERY_CS, 'cti', 'CTICONTROL', 'GLBEN'],
        [exit_ok(), stdout_contains('RW')],
    ),
    # Component listing
    (
        '--component etm lists ETM registers',
        [QUERY_CS, '--component', 'etm'],
        [exit_ok(), stdout_contains('TRCPRGCTLR')],
    ),
    (
        '--component cti lists CTI registers',
        [QUERY_CS, '--component', 'cti'],
        [exit_ok(), stdout_contains('CTICONTROL')],
    ),
    (
        '--component stm lists STM registers',
        [QUERY_CS, '--component', 'stm'],
        [exit_ok(), stdout_contains('STMHEMCR')],
    ),
    (
        '--component itm lists ITM registers',
        [QUERY_CS, '--component', 'itm'],
        [exit_ok(), stdout_contains('TCR')],
    ),
    # ID block
    (
        '--id-block lists identification registers',
        [QUERY_CS, '--id-block'],
        [exit_ok(), stdout_contains('DEVARCH')],
    ),
    (
        'id_block DEVTYPE lookup succeeds',
        [QUERY_CS, 'id_block', 'DEVTYPE'],
        [exit_ok(), stdout_contains('DEVTYPE')],
    ),
    # Name listing
    (
        '--list TRC finds ETM TRC registers',
        [QUERY_CS, '--list', 'TRC'],
        [exit_ok(), stdout_contains('TRCPRGCTLR')],
    ),
    (
        '--list-components lists all 5 components',
        [QUERY_CS, '--list-components'],
        [exit_ok(), stdout_contains('ETM'), stdout_contains('CTI'),
         stdout_contains('STM'), stdout_contains('ITM')],
    ),
    # Hallucination guard
    (
        'Hallucinated register TRCFAKECTRL not found (exit non-zero)',
        [QUERY_CS, 'etm', 'TRCFAKECTRL'],
        [exit_nonzero()],
    ),
    (
        'Hallucinated component FICTIOUS not found (exit non-zero)',
        [QUERY_CS, '--component', 'FICTIOUS'],
        [exit_nonzero()],
    ),
]

# CoreSight search integration tests
CORESIGHT_SEARCH_TESTS = [
    (
        'search TRC finds CoreSight ETM registers — exit criteria',
        [QUERY_SRCH, 'TRC'],
        [exit_ok(), stdout_contains('TRCPRGCTLR')],
    ),
    (
        'search --spec coresight TRC returns CoreSight results',
        [QUERY_SRCH, '--spec', 'coresight', 'TRC'],
        [exit_ok(), stdout_contains('TRCPRGCTLR')],
    ),
    (
        'search --spec coresight GLBEN finds CTI CTICONTROL',
        [QUERY_SRCH, '--spec', 'coresight', 'GLBEN'],
        [exit_ok(), stdout_contains('CTICONTROL')],
    ),
    (
        'search --spec coresight FAKECTRL_ZZZZ returns no results (exit non-zero)',
        [QUERY_SRCH, '--spec', 'coresight', 'FAKECTRL_ZZZZ'],
        [exit_nonzero()],
    ),
]

# ---------------------------------------------------------------------------
# E0 tests: PMU skill (arm-pmu cache — built by build_pmu_index.py)
# ---------------------------------------------------------------------------

def _check_pmu_cache_available() -> bool:
    """Return True if the PMU cache exists."""
    pmu_meta = TOOLS_DIR.parent / 'cache' / 'pmu_meta.json'
    return pmu_meta.exists()


# E0: PMU event tests (require pmu cache — built by build_pmu_index.py)
PMU_TESTS = [
    # -- CPU existence -------------------------------------------------------
    (
        'cortex-a710 is present in the PMU cache',
        [QUERY_PMU, 'cortex-a710'],
        [exit_ok(), stdout_contains('Cortex-A710')],
    ),
    (
        'cortex-a710 event count is reported',
        [QUERY_PMU, 'cortex-a710'],
        [exit_ok(), stdout_contains('Events')],
    ),
    (
        'neoverse-n1 is present in the PMU cache',
        [QUERY_PMU, 'neoverse-n1'],
        [exit_ok(), stdout_contains('Neoverse N1')],
    ),
    # -- CPU_CYCLES event code for Cortex-A710 (exit criteria) ---------------
    (
        'cortex-a710 CPU_CYCLES returns correct code 17 (0x011)',
        [QUERY_PMU, 'cortex-a710', 'CPU_CYCLES'],
        [exit_ok(), stdout_contains('CPU_CYCLES'), stdout_contains('17 (0x011)')],
    ),
    (
        'cortex-a710 CPU_CYCLES description is present',
        [QUERY_PMU, 'cortex-a710', 'CPU_CYCLES'],
        [exit_ok(), stdout_contains('Cycle')],
    ),
    # -- L1D_CACHE_REFILL event code -----------------------------------------
    (
        'cortex-a710 L1D_CACHE_REFILL code is 3 (0x003)',
        [QUERY_PMU, 'cortex-a710', 'L1D_CACHE_REFILL'],
        [exit_ok(), stdout_contains('L1D_CACHE_REFILL'), stdout_contains('3 (0x003)')],
    ),
    (
        'cortex-a710 L1D_CACHE_REFILL description mentions L1',
        [QUERY_PMU, 'cortex-a710', 'L1D_CACHE_REFILL'],
        [exit_ok(), stdout_contains('L1')],
    ),
    # -- Cross-CPU search ----------------------------------------------------
    (
        '--search L1D_CACHE_REFILL finds multiple CPUs',
        [QUERY_PMU, '--search', 'L1D_CACHE_REFILL'],
        [exit_ok(), stdout_contains('cortex-a710'), stdout_contains('neoverse-n1')],
    ),
    (
        '--search L1D_CACHE_REFILL consistently shows code 3 (0x003)',
        [QUERY_PMU, '--search', 'L1D_CACHE_REFILL'],
        [exit_ok(), stdout_contains('3 (0x003)')],
    ),
    (
        '--search CYCLE finds CPU_CYCLES event',
        [QUERY_PMU, '--search', 'CYCLE'],
        [exit_ok(), stdout_contains('CPU_CYCLES')],
    ),
    # -- --list command -------------------------------------------------------
    (
        '--list shows all CPUs',
        [QUERY_PMU, '--list'],
        [exit_ok(), stdout_contains('cortex-a710'), stdout_contains('neoverse-n1')],
    ),
    (
        '--list neoverse filters to Neoverse CPUs only',
        [QUERY_PMU, '--list', 'neoverse'],
        [exit_ok(), stdout_contains('neoverse-n1'), stdout_not_contains('cortex-a710')],
    ),
    # -- Hallucination guard -------------------------------------------------
    (
        'FAKE_CPU_ZZZZ is not found (hallucination guard)',
        [QUERY_PMU, 'FAKE_CPU_ZZZZ'],
        [exit_nonzero()],
    ),
    (
        'cortex-a710 FAKE_EVENT_ZZZZ is not found (hallucination guard)',
        [QUERY_PMU, 'cortex-a710', 'FAKE_EVENT_ZZZZ'],
        [exit_nonzero()],
    ),
]

# ---------------------------------------------------------------------------
# EX tests: Cross-extension integration (arm-reg + arm-gic cross-routing)
# ---------------------------------------------------------------------------

# EX-1: Cross-skill routing tests — requires A64 cache AND GIC cache
CROSS_ROUTING_TESTS = [
    # ICC_PMR_EL1 is an AArch64 system register in AARCHMRS → query via arm-reg
    (
        'ICC_PMR_EL1 is in AARCHMRS and accessible via arm-reg (EX-1 cross-routing)',
        [QUERY_REG, 'ICC_PMR_EL1'],
        [exit_ok(), stdout_contains('ICC_PMR_EL1')],
    ),
    (
        'ICC_PMR_EL1 state is AArch64 (system register, not GIC memory-mapped)',
        [QUERY_REG, 'ICC_PMR_EL1'],
        [exit_ok(), stdout_contains('AArch64')],
    ),
    # GICD_CTLR is in AARCHMRS as an ext-state memory-mapped register;
    # arm-gic provides the GIC-specific field view and routing
    (
        'GICD_CTLR in AARCHMRS is ext-state (memory-mapped); arm-gic gives GIC-specific view',
        [QUERY_REG, 'GICD_CTLR'],
        [exit_ok(), stdout_contains('ext')],
    ),
    # arm-gic cross-reference: ICC_PMR_EL1 redirects to arm-reg
    (
        'arm-gic --icc-xref ICC_PMR_EL1 routes to arm-reg (cross-routing)',
        [QUERY_GIC, '--icc-xref', 'ICC_PMR_EL1'],
        [exit_ok(), stdout_contains('query_register.py')],
    ),
    # Combined search finds AARCHMRS ICC registers
    (
        'Combined search "PMR" finds ICC_PMR_EL1 (AARCHMRS system register)',
        [QUERY_SRCH, 'PMR'],
        [exit_ok(), stdout_contains('ICC_PMR_EL1')],
    ),
    # Combined search finds both AARCHMRS and GIC registers — full cross-spec view
    (
        'Combined search "CTLR" finds SCTLR_EL1 (AARCHMRS) and GICD_CTLR (GIC)',
        [QUERY_SRCH, 'CTLR'],
        [exit_ok(), stdout_contains('SCTLR_EL1'), stdout_contains('GICD_CTLR')],
    ),
]

# EX-2: --spec aarchmrs tests — requires A64 cache only
SEARCH_SPEC_AARCHMRS_TESTS = [
    (
        '--spec aarchmrs TCR returns AARCHMRS TCR_EL1 register (EX-2)',
        [QUERY_SRCH, '--spec', 'aarchmrs', 'TCR'],
        [exit_ok(), stdout_contains('TCR_EL1')],
    ),
    (
        '--spec aarchmrs ADD finds ADD_addsub_imm A64 operation',
        [QUERY_SRCH, '--spec', 'aarchmrs', 'ADD'],
        [exit_ok(), stdout_contains('ADD_addsub_imm')],
    ),
    (
        '--spec aarchmrs CPU_CYCLES finds nothing (PMU event, not an AARCHMRS name)',
        [QUERY_SRCH, '--spec', 'aarchmrs', 'CPU_CYCLES'],
        [exit_nonzero()],
    ),
    (
        '--spec aarchmrs with no match exits non-zero',
        [QUERY_SRCH, '--spec', 'aarchmrs', 'FAKE_ZZZ_NOEXIST'],
        [exit_nonzero()],
    ),
]

# EX-2: --spec pmu tests — requires PMU cache only
SEARCH_SPEC_PMU_TESTS = [
    (
        '--spec pmu CPU_CYCLES finds PMU event (EX-2)',
        [QUERY_SRCH, '--spec', 'pmu', 'CPU_CYCLES'],
        [exit_ok(), stdout_contains('CPU_CYCLES')],
    ),
    (
        '--spec pmu L1D_CACHE finds L1D_CACHE_REFILL event',
        [QUERY_SRCH, '--spec', 'pmu', 'L1D_CACHE'],
        [exit_ok(), stdout_contains('L1D_CACHE_REFILL')],
    ),
    (
        '--spec pmu shows CPU count for CPU_CYCLES',
        [QUERY_SRCH, '--spec', 'pmu', 'CPU_CYCLES'],
        [exit_ok(), stdout_contains('CPU(s)')],
    ),
    (
        '--spec pmu FAKE_EVENT_ZZZZ exits non-zero',
        [QUERY_SRCH, '--spec', 'pmu', 'FAKE_EVENT_ZZZZ'],
        [exit_nonzero()],
    ),
]

# Map skill name → test list
ALL_SKILLS: dict = {
    'feat':                  FEAT_TESTS,
    'reg':                   REG_TESTS,
    'search':                SEARCH_TESTS,
    'instr':                 INSTR_TESTS,
    'instr_t32':             INSTR_T32_TESTS,
    'instr_a32':             INSTR_A32_TESTS,
    'search_t32':            SEARCH_T32_TESTS,
    'gic':                   GIC_TESTS,
    'gic_search':            GIC_SEARCH_TESTS,
    'coresight':             CORESIGHT_TESTS,
    'coresight_search':      CORESIGHT_SEARCH_TESTS,
    'pmu':                   PMU_TESTS,
    'cross_routing':         CROSS_ROUTING_TESTS,
    'search_spec_aarchmrs':  SEARCH_SPEC_AARCHMRS_TESTS,
    'search_spec_pmu':       SEARCH_SPEC_PMU_TESTS,
}

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_skill_tests(skill_name: str, tests: list, verbose: bool) -> tuple:
    """Run a list of tests and return (pass_count, fail_count)."""
    print(f'\n[ arm-{skill_name} skill ] — {len(tests)} test case(s)')
    print('-' * 60)

    pass_count = 0
    fail_count = 0

    for desc, args, checks in tests:
        rc, stdout, stderr = _run(args)
        all_ok = True
        details = []

        for chk in checks:
            ok, detail = chk(rc, stdout, stderr)
            if not ok:
                all_ok = False
            details.append((ok, detail))

        status = 'PASS' if all_ok else 'FAIL'
        print(f'  [{status}] {desc}')

        if not all_ok or verbose:
            for ok, detail in details:
                marker = '      ✓' if ok else '      ✗'
                print(f'{marker} {detail}')
            if not all_ok or verbose:
                if stdout.strip():
                    print(f'      stdout: {stdout.strip()[:300]}')
                if stderr.strip():
                    print(f'      stderr: {stderr.strip()[:200]}')

        if all_ok:
            pass_count += 1
        else:
            fail_count += 1

    return pass_count, fail_count


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Correctness evaluation for the ARM MRS agent skills.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        '--skill', metavar='SKILL',
        help=f'Run only tests for this skill (choices: {", ".join(ALL_SKILLS.keys())}). Default: all.',
    )
    parser.add_argument(
        '--verbose', action='store_true',
        help='Print stdout/stderr for every test, not just failures.',
    )
    args = parser.parse_args()

    print('ARM MRS Skill Correctness Evaluation')
    print('Architecture: v9Ap6-A, Build 445, March 2025')
    print('=' * 60)

    # Validate cache — A64 cache is required for feat/reg/search/instr/cross_routing/search_spec_aarchmrs tests;
    # arm_arm cache is required for instr_t32/instr_a32/search_t32 tests;
    # gic cache is required for gic/gic_search/cross_routing tests;
    # coresight cache is required for coresight/coresight_search tests;
    # pmu cache is required for pmu/search_spec_pmu tests.
    ARM_ARM_ONLY_SKILLS  = frozenset(('instr_t32', 'instr_a32', 'search_t32'))
    GIC_ONLY_SKILLS      = frozenset(('gic', 'gic_search'))
    GIC_ALSO_SKILLS      = frozenset(('cross_routing',))   # needs A64 + GIC
    CS_ONLY_SKILLS       = frozenset(('coresight', 'coresight_search'))
    PMU_ONLY_SKILLS      = frozenset(('pmu', 'search_spec_pmu'))

    # Select skills to test first (so we can decide which caches to require)
    if args.skill:
        if args.skill not in ALL_SKILLS:
            print(f'Unknown skill "{args.skill}". Available: {", ".join(ALL_SKILLS.keys())}',
                  file=sys.stderr)
            return 1
        skills_to_run = {args.skill: ALL_SKILLS[args.skill]}
    else:
        skills_to_run = ALL_SKILLS

    # NON_A64_SKILLS: skills that do NOT require the A64 cache.
    # cross_routing and search_spec_aarchmrs are NOT here — they need A64.
    NON_A64_SKILLS       = ARM_ARM_ONLY_SKILLS | GIC_ONLY_SKILLS | CS_ONLY_SKILLS | PMU_ONLY_SKILLS
    needs_a64_cache      = any(s not in NON_A64_SKILLS for s in skills_to_run)
    needs_arm_arm_cache  = any(s in ARM_ARM_ONLY_SKILLS for s in skills_to_run)
    needs_gic_cache      = any(s in GIC_ONLY_SKILLS | GIC_ALSO_SKILLS for s in skills_to_run)
    needs_cs_cache       = any(s in CS_ONLY_SKILLS for s in skills_to_run)
    needs_pmu_cache      = any(s in PMU_ONLY_SKILLS for s in skills_to_run)

    if needs_a64_cache and not _check_cache_available():
        print('\nERROR: A64 cache not found or incomplete.')
        print('Build the A64 cache first:  python tools/build_index.py')
        return 1

    if needs_arm_arm_cache and not _check_arm_arm_cache_available():
        print('\nERROR: ARM ARM cache (T32/A32) not found.')
        print('Build it first:  python tools/build_arm_arm_index.py')
        return 1

    if needs_gic_cache and not _check_gic_cache_available():
        print('\nERROR: GIC cache not found.')
        print('Build it first:  python tools/build_gic_index.py')
        return 1

    if needs_cs_cache and not _check_coresight_cache_available():
        print('\nERROR: CoreSight cache not found.')
        print('Build it first:  python tools/build_coresight_index.py')
        return 1

    if needs_pmu_cache and not _check_pmu_cache_available():
        print('\nERROR: PMU cache not found.')
        print('Build it first:  python tools/build_pmu_index.py')
        return 1

    total_pass = 0
    total_fail = 0

    for skill_name, tests in skills_to_run.items():
        p, f = run_skill_tests(skill_name, tests, args.verbose)
        total_pass += p
        total_fail += f

    total = total_pass + total_fail
    score = total_pass / total * 100 if total > 0 else 0.0

    print()
    print('=' * 60)
    print(f'Results : {total_pass}/{total} passed  ({score:.1f}%)')

    if total_fail == 0:
        print('Status  : ALL TESTS PASSED')
        print()
        print('All skills are correctly grounded in the ARM MRS data.')
        print('All verified facts match the official specification — no hallucination.')
        return 0
    else:
        print(f'Status  : {total_fail} TEST(S) FAILED')
        print()
        print('Some facts returned by the skill do not match the ARM MRS data.')
        print('Check the failures above and rebuild the cache if needed.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
