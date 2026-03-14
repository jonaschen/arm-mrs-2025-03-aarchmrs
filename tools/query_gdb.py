#!/usr/bin/env python3
"""
query_gdb.py — AArch64 GDB debugging CLI for the arm-gdb skill.

Orchestrates GDB/MI sessions for step-trace, register inspection, and
register-state assertion on AArch64 ELF binaries.

Usage:
    query_gdb.py --check
    query_gdb.py --version
    query_gdb.py <binary> --registers
    query_gdb.py <binary> --break main --step 3 --registers
    query_gdb.py <binary> --break main --assert "x0=0 x1=0"
    query_gdb.py <binary> --suite suite.json
    query_gdb.py <binary> --backtrace
    query_gdb.py --sigill-hint v9Ap4 [--pc 0x4004f0]

Commands:
    --check            Check whether gdb-multiarch / gdb is installed
    --version          Print the GDB version string
    --registers        Print all AArch64 register values at a breakpoint
    --break LOCATION   Set a breakpoint before stepping (default: main)
    --step N           Execute N source lines (step-in) before inspecting
    --nexti N          Execute N machine instructions (step-over)
    --assert "REG=VAL REG2=VAL2"
                       Assert register values at current stop;
                       VAL can be decimal or 0x-prefixed hex
    --backtrace        Print the call stack
    --suite FILE.json  Run a JSON step/assert batch suite
    --sigill-hint ARCH --pc ADDR
                       Print H1-based SIGILL repair hint for an arch version

Environment:
    ARM_GDB_PATH   Override the GDB executable (default: gdb-multiarch or gdb)

Exit codes:
    0  success / check passed / all assertions passed
    1  tool or binary not found, GDB error, assertion failure
    2  SIGILL detected

Suite JSON format:
    [
      {"action": "breakpoint", "location": "main"},
      {"action": "step", "count": 3,
       "assert": {"x0": 0, "x1": "0x42"}, "note": "after init"},
      {"action": "continue",
       "assert": {"x0": 1}, "note": "after main returns"}
    ]
"""

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate tools directory for imports
# ---------------------------------------------------------------------------
_TOOLS_DIR = Path(__file__).parent.resolve()
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from gdb_session import (
    GdbSession,
    GdbError,
    GdbNotAvailableError,
    SigilDetectedError,
    find_gdb,
    gdb_available,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_assert_string(spec: str) -> dict:
    """Parse ``"x0=0 x1=0x42 sp=4096"`` → ``{"x0": 0, "x1": 66, "sp": 4096}``."""
    result = {}
    for token in spec.split():
        if '=' not in token:
            print(f'WARNING: Ignoring malformed assertion token {token!r}',
                  file=sys.stderr)
            continue
        reg, val_str = token.split('=', 1)
        try:
            result[reg.strip()] = int(val_str.strip(), 0)
        except ValueError:
            print(f'WARNING: Cannot parse value {val_str!r} for {reg!r}; skipping.',
                  file=sys.stderr)
    return result


def _load_suite(path: str) -> list:
    """Load a JSON step/assert suite file."""
    p = Path(path)
    if not p.exists():
        print(f'ERROR: Suite file not found: {path}', file=sys.stderr)
        sys.exit(1)
    try:
        with open(p) as f:
            data = json.load(f)
        if not isinstance(data, list):
            print('ERROR: Suite file must be a JSON array.', file=sys.stderr)
            sys.exit(1)
        return data
    except json.JSONDecodeError as e:
        print(f'ERROR: Invalid JSON in suite file: {e}', file=sys.stderr)
        sys.exit(1)


def _print_registers(regs: dict) -> None:
    """Pretty-print AArch64 register values."""
    general = [f'x{i}' for i in range(31)] + ['sp', 'pc', 'pstate']
    print('AArch64 Registers:')
    for name in general:
        if name in regs:
            val = regs[name]
            if isinstance(val, int):
                print(f'  {name:<8} = {hex(val):>20}  ({val})')
            else:
                print(f'  {name:<8} = {val}')


def _print_backtrace(frames: list) -> None:
    """Pretty-print a GDB backtrace."""
    print('Backtrace:')
    for frame in frames:
        print(f'  #{frame["level"]:<3} {frame["addr"]:<18} '
              f'{frame["func"]}  ({frame["file"]}:{frame["line"]})')


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------

def cmd_check() -> int:
    """Check whether a usable GDB is installed."""
    if gdb_available():
        try:
            path = find_gdb()
            print(f'GDB available: {path}')
            return 0
        except GdbNotAvailableError as e:
            print(f'GDB not available: {e}', file=sys.stderr)
            return 1
    else:
        print(
            'GDB not found. Install with:\n'
            '    sudo apt install gdb-multiarch',
            file=sys.stderr,
        )
        return 1


def cmd_version() -> int:
    """Print the GDB version."""
    import subprocess
    try:
        gdb = find_gdb()
    except GdbNotAvailableError as e:
        print(str(e), file=sys.stderr)
        return 1
    try:
        result = subprocess.run(
            [gdb, '--version'],
            capture_output=True, text=True, timeout=10
        )
        print(result.stdout.splitlines()[0] if result.stdout else 'unknown')
        return 0
    except Exception as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1


def cmd_sigill_hint(arch: str, pc: int | None) -> int:
    """Print the SIGILL repair hint for the given arch."""
    print(GdbSession.suggest_sigill_repair(arch, pc))
    return 0


def cmd_debug(
    binary: str,
    *,
    break_location: str = 'main',
    step_count: int = 0,
    nexti_count: int = 0,
    show_registers: bool = False,
    assert_spec: str | None = None,
    show_backtrace: bool = False,
    suite_file: str | None = None,
    sigill_arch: str = 'v9Ap4',
) -> int:
    """Run GDB on ``binary`` and perform the requested operations."""
    if not Path(binary).exists():
        print(f'ERROR: Binary not found: {binary}', file=sys.stderr)
        return 1

    try:
        find_gdb()
    except GdbNotAvailableError as e:
        print(str(e), file=sys.stderr)
        return 1

    if suite_file:
        # Batch mode: run the JSON suite
        suite = _load_suite(suite_file)
        print(f'Running suite: {suite_file} ({len(suite)} steps)')
        try:
            result = run_assertion_suite_on_binary(
                binary, suite, arch=sigill_arch,
            )
        except GdbError as e:
            print(f'GDB error: {e}', file=sys.stderr)
            return 1
        print(f'Passed: {result["passed"]}  Failed: {result["failed"]}')
        if result['failures']:
            print('Failures:')
            for f in result['failures']:
                if 'error' in f:
                    print(f'  [{f["step"]}] {f["error"]} at {f.get("pc","?")}')
                else:
                    print(
                        f'  [{f["step"]}] {f["register"]}: '
                        f'expected {f["expected"]}, got {f["actual"]}'
                    )
            return 1
        return 0

    # Interactive (non-suite) mode
    try:
        with GdbSession(binary) as gdb:
            # Set breakpoint
            bp_num = gdb.set_breakpoint(break_location)
            print(f'Breakpoint {bp_num} at {break_location!r}')

            # Run to breakpoint
            gdb.run()
            print(f'Stopped at {break_location!r}')

            # Step-in
            if step_count > 0:
                print(f'Stepping {step_count} source line(s)…')
                gdb.step(step_count)

            # Step machine instructions (step-over)
            if nexti_count > 0:
                print(f'Stepping {nexti_count} machine instruction(s) (nexti)…')
                gdb.nexti(nexti_count)

            # Show registers
            if show_registers or assert_spec:
                regs = gdb.get_registers()
                if show_registers:
                    _print_registers(regs)

            # Assertions
            if assert_spec:
                expected = _parse_assert_string(assert_spec)
                failures = gdb.assert_registers(expected)
                if failures:
                    print(f'ASSERTION FAILURES ({len(failures)}):')
                    for f in failures:
                        print(
                            f'  {f.register}: expected {hex(f.expected)}, '
                            f'got {hex(f.actual)}'
                        )
                    return 1
                else:
                    print(f'All {len(expected)} assertion(s) passed.')

            # Backtrace
            if show_backtrace:
                frames = gdb.get_backtrace()
                _print_backtrace(frames)

    except SigilDetectedError as e:
        print(f'SIGILL at {hex(e.pc) if e.pc else "unknown"}', file=sys.stderr)
        print(GdbSession.suggest_sigill_repair(sigill_arch, e.pc))
        return 2
    except GdbError as e:
        print(f'GDB error: {e}', file=sys.stderr)
        return 1

    return 0


# Expose for programmatic imports (H3-2, H3-4)
from gdb_session import run_assertion_suite_on_binary  # noqa: F401 E402


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='AArch64 GDB debugging CLI (arm-gdb skill)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Mode selection
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        '--check', action='store_true',
        help='Check whether gdb-multiarch / gdb is installed',
    )
    mode.add_argument(
        '--version', action='store_true',
        help='Print the GDB version string',
    )

    # Binary target
    parser.add_argument(
        'binary', nargs='?', metavar='BINARY',
        help='Path to the AArch64 ELF binary to debug',
    )

    # Debugging options
    parser.add_argument(
        '--break', dest='break_location', default='main',
        metavar='LOCATION',
        help='Set a breakpoint before stepping (default: main)',
    )
    parser.add_argument(
        '--step', type=int, default=0, metavar='N',
        help='Execute N source lines (step-in)',
    )
    parser.add_argument(
        '--nexti', type=int, default=0, metavar='N',
        help='Execute N machine instructions (step-over)',
    )
    parser.add_argument(
        '--registers', action='store_true',
        help='Print all AArch64 register values at the current stop',
    )
    parser.add_argument(
        '--assert', dest='assert_spec', metavar='"REG=VAL …"',
        help='Assert register values (e.g. "x0=0 x1=0x42")',
    )
    parser.add_argument(
        '--backtrace', action='store_true',
        help='Print the call stack',
    )
    parser.add_argument(
        '--suite', metavar='FILE.json',
        help='Run a JSON step/assert batch suite',
    )

    # SIGILL repair
    parser.add_argument(
        '--sigill-hint', metavar='ARCH',
        help='Print H1-based SIGILL repair hint for an architecture version',
    )
    parser.add_argument(
        '--pc', metavar='ADDR',
        help='Program counter of the SIGILL (hex), used with --sigill-hint',
    )

    args = parser.parse_args()

    # Dispatch
    if args.check:
        return cmd_check()

    if args.version:
        return cmd_version()

    if args.sigill_hint:
        pc_val = int(args.pc, 16) if args.pc else None
        return cmd_sigill_hint(args.sigill_hint, pc_val)

    if not args.binary:
        parser.print_help()
        return 1

    return cmd_debug(
        args.binary,
        break_location=args.break_location,
        step_count=args.step,
        nexti_count=args.nexti,
        show_registers=args.registers,
        assert_spec=args.assert_spec,
        show_backtrace=args.backtrace,
        suite_file=args.suite,
    )


if __name__ == '__main__':
    sys.exit(main())
