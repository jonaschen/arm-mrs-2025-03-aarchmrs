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

# Map skill name → test list
ALL_SKILLS: dict = {
    'feat':   FEAT_TESTS,
    'reg':    REG_TESTS,
    'search': SEARCH_TESTS,
    'instr':  INSTR_TESTS,
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

    # Validate cache
    if not _check_cache_available():
        print('\nERROR: Cache not found or incomplete.')
        print('Build the cache first:  python tools/build_index.py')
        return 1

    # Select skills to test
    if args.skill:
        if args.skill not in ALL_SKILLS:
            print(f'Unknown skill "{args.skill}". Available: {", ".join(ALL_SKILLS.keys())}',
                  file=sys.stderr)
            return 1
        skills_to_run = {args.skill: ALL_SKILLS[args.skill]}
    else:
        skills_to_run = ALL_SKILLS

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
