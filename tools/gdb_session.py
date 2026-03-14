#!/usr/bin/env python3
"""
gdb_session.py — AArch64 GDB/MI session manager for the arm-gdb skill.

Provides a Python class that drives GDB using the GDB/MI (Machine Interface)
protocol over subprocess stdin/stdout.  Intended for batch orchestration of:
  step → inspect → assert sequences on AArch64 binaries.

Typical usage (programmatic):

    from gdb_session import GdbSession, GdbNotAvailableError, SigilDetectedError

    with GdbSession('my_binary') as gdb:
        gdb.set_breakpoint('main')
        gdb.run()
        regs = gdb.get_registers()
        gdb.assert_register('x0', 0)   # raises AssertionError on mismatch
        gdb.step(3)
        regs = gdb.get_registers()

SIGILL handling:

    try:
        gdb.step()
    except SigilDetectedError as e:
        # e.pc is the address of the illegal instruction
        # Query H1 (query_allowlist.py) to find a valid substitute
        print(f'SIGILL at {hex(e.pc)} — consult arm-allowlist for repair')

GDB process requirements:
    gdb-multiarch (preferred) or gdb must be installed.
    The binary must be a valid ELF for the target architecture.

Exit codes returned by GdbSession.run_to_exit():
    0       Binary exited normally
    None    Binary still running (e.g. stuck in loop)
    SIGILL  SigilDetectedError raised

Environment:
    ARM_GDB_PATH   Override the GDB executable path (default: auto-detect
                   gdb-multiarch then gdb)
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class GdbNotAvailableError(RuntimeError):
    """Raised when no usable GDB executable is found on the system."""


class GdbError(RuntimeError):
    """Raised when GDB returns an unexpected error response."""


class SigilDetectedError(RuntimeError):
    """Raised when GDB reports a SIGILL stop.

    Attributes
    ----------
    pc : int | None
        Program counter address of the illegal instruction, if available.
    arch : str | None
        Architecture hint (e.g. ``"aarch64"``), if detected from GDB output.
    """

    def __init__(self, message: str, pc: int | None = None,
                 arch: str | None = None):
        super().__init__(message)
        self.pc = pc
        self.arch = arch


class AssertionFailedError(AssertionError):
    """Raised by GdbSession.assert_register() when the actual value differs.

    Attributes
    ----------
    register : str
        Register name (lower-case, e.g. ``"x0"``).
    expected : int
        Expected value.
    actual : int
        Actual value read from GDB.
    """

    def __init__(self, register: str, expected: int, actual: int):
        super().__init__(
            f'Register {register}: expected {hex(expected)}, got {hex(actual)}'
        )
        self.register = register
        self.expected = expected
        self.actual = actual


# ---------------------------------------------------------------------------
# GDB executable discovery
# ---------------------------------------------------------------------------

_KNOWN_GDB_NAMES = ['gdb-multiarch', 'gdb']


def find_gdb() -> str:
    """Return the path to a usable GDB executable.

    Priority order:
    1. ``ARM_GDB_PATH`` environment variable
    2. ``gdb-multiarch``  (preferred — supports all architectures)
    3. ``gdb``            (fallback)

    Raises
    ------
    GdbNotAvailableError
        If no GDB executable is found.
    """
    env_path = os.environ.get('ARM_GDB_PATH')
    if env_path:
        if shutil.which(env_path):
            return env_path
        raise GdbNotAvailableError(
            f'ARM_GDB_PATH={env_path!r} is set but the executable was not found.'
        )

    for name in _KNOWN_GDB_NAMES:
        path = shutil.which(name)
        if path:
            return path

    raise GdbNotAvailableError(
        'No GDB executable found. Install gdb-multiarch:\n'
        '    sudo apt install gdb-multiarch\n'
        'or set the ARM_GDB_PATH environment variable.'
    )


def gdb_available() -> bool:
    """Return True if a GDB executable is available, False otherwise."""
    try:
        find_gdb()
        return True
    except GdbNotAvailableError:
        return False


# ---------------------------------------------------------------------------
# GDB/MI line-level parser helpers
# ---------------------------------------------------------------------------

# Record type prefixes defined by the GDB/MI specification.
_MI_PREFIX = {
    '*': 'async-exec',      # async execution records (stopped, running, …)
    '+': 'async-status',    # async status records
    '=': 'async-notify',    # async notify records
    '~': 'stream-console',  # console stream output
    '@': 'stream-target',   # target stream output
    '&': 'stream-log',      # log stream output
    '^': 'result',          # result records (done, running, error, …)
}


def _parse_mi_record(line: str) -> dict:
    """Parse one GDB/MI output line into a dict.

    Returns a dict with at minimum a ``type`` key.  The ``payload`` key
    contains a free-form string for stream records or a dict parsed from the
    GDB/MI value syntax for result/async records.
    """
    line = line.strip()
    if not line:
        return {'type': 'empty'}

    # Token prefix (optional sequence of digits followed by a record type)
    token = ''
    m = re.match(r'^(\d+)', line)
    if m:
        token = m.group(1)
        line = line[len(token):]

    if not line:
        return {'type': 'empty', 'token': token}

    prefix = line[0]
    rest = line[1:]

    rec_type = _MI_PREFIX.get(prefix, 'unknown')
    record: dict = {'type': rec_type, 'raw': line, 'token': token}

    if prefix in ('~', '@', '&'):
        # Stream record — payload is a C-style quoted string
        if rest.startswith('"') and rest.endswith('"'):
            rest = rest[1:-1]
        record['payload'] = rest.replace('\\n', '\n').replace('\\t', '\t')
    else:
        # Result / async record — parse "class,key=value,…"
        parts = rest.split(',', 1)
        record['class'] = parts[0]
        record['payload'] = parts[1] if len(parts) > 1 else ''

    return record


def _extract_value(text: str, key: str) -> str | None:
    """Extract the value of ``key`` from a GDB/MI result string.

    Handles simple ``key="value"`` patterns.  Does not implement full
    recursive GDB/MI value grammar; sufficient for register/frame queries.
    """
    pattern = rf'{re.escape(key)}="([^"]*)"'
    m = re.search(pattern, text)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# GdbSession
# ---------------------------------------------------------------------------

class GdbSession:
    """Drive GDB over the GDB/MI protocol for AArch64 batch debugging.

    Parameters
    ----------
    executable : str | Path
        Path to the AArch64 binary to debug.
    gdb_path : str | None
        Path to the GDB executable.  If ``None``, auto-detected.
    timeout : float
        Seconds to wait for each GDB/MI response (default: 10.0).
    extra_args : list[str]
        Additional arguments passed to GDB (e.g. ``['-ex', 'set arch aarch64']``).
    """

    def __init__(
        self,
        executable: str | Path,
        *,
        gdb_path: str | None = None,
        timeout: float = 10.0,
        extra_args: list | None = None,
    ):
        self._executable = str(executable)
        self._gdb_path = gdb_path or find_gdb()
        self._timeout = timeout
        self._extra_args = extra_args or []
        self._proc: subprocess.Popen | None = None
        self._token = 0

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> 'GdbSession':
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.close()
        return False   # propagate exceptions

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Launch the GDB process in MI mode."""
        cmd = [
            self._gdb_path,
            '--interpreter=mi',
            '--quiet',
            '--args', self._executable,
        ] + self._extra_args

        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        # Drain GDB's startup banner
        self._drain_until_prompt()

    def close(self) -> None:
        """Send ``-gdb-exit`` and wait for GDB to terminate."""
        if self._proc and self._proc.poll() is None:
            try:
                self._send_mi('-gdb-exit')
            except Exception:
                pass
            try:
                self._proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    # ------------------------------------------------------------------
    # Execution control
    # ------------------------------------------------------------------

    def run(self, args: str = '') -> dict:
        """Start the inferior process and run until a stop event.

        Returns the stop record dict.

        Raises
        ------
        SigilDetectedError
            If the inferior stops with SIGILL.
        """
        cmd = f'-exec-run {args}'.strip()
        return self._exec_and_wait_for_stop(cmd)

    def continue_(self) -> dict:
        """Resume execution until the next stop event.

        Raises
        ------
        SigilDetectedError
            If the inferior stops with SIGILL.
        """
        return self._exec_and_wait_for_stop('-exec-continue')

    def step(self, count: int = 1) -> dict:
        """Execute ``count`` source lines (step in), stopping after each.

        Returns the stop record for the last step.

        Raises
        ------
        SigilDetectedError
            If SIGILL is encountered during stepping.
        """
        result: dict = {}
        for _ in range(count):
            result = self._exec_and_wait_for_stop('-exec-step')
        return result

    def next(self, count: int = 1) -> dict:
        """Execute ``count`` source lines (step over), stopping after each.

        Raises
        ------
        SigilDetectedError
            If SIGILL is encountered during stepping.
        """
        result: dict = {}
        for _ in range(count):
            result = self._exec_and_wait_for_stop('-exec-next')
        return result

    def stepi(self, count: int = 1) -> dict:
        """Execute ``count`` *machine instructions* (step in).

        Raises
        ------
        SigilDetectedError
            If SIGILL is encountered.
        """
        result: dict = {}
        for _ in range(count):
            result = self._exec_and_wait_for_stop('-exec-step-instruction')
        return result

    def nexti(self, count: int = 1) -> dict:
        """Execute ``count`` *machine instructions* (step over).

        Raises
        ------
        SigilDetectedError
            If SIGILL is encountered.
        """
        result: dict = {}
        for _ in range(count):
            result = self._exec_and_wait_for_stop('-exec-next-instruction')
        return result

    # ------------------------------------------------------------------
    # Breakpoint management
    # ------------------------------------------------------------------

    def set_breakpoint(self, location: str) -> int:
        """Set a breakpoint at ``location`` (function name, address, or file:line).

        Returns
        -------
        int
            GDB breakpoint number.
        """
        records = self._send_mi(f'-break-insert {location}')
        for rec in records:
            if rec.get('class') == 'done':
                bp_str = _extract_value(rec.get('payload', ''), 'number')
                if bp_str:
                    return int(bp_str)
        raise GdbError(f'Failed to set breakpoint at {location!r}')

    def list_breakpoints(self) -> list:
        """Return a list of breakpoint descriptions as dicts."""
        records = self._send_mi('-break-list')
        for rec in records:
            if rec.get('class') == 'done':
                return self._parse_breakpoint_table(rec.get('payload', ''))
        return []

    def delete_breakpoint(self, bp_number: int) -> None:
        """Delete a breakpoint by number."""
        self._send_mi(f'-break-delete {bp_number}')

    # ------------------------------------------------------------------
    # Data inspection
    # ------------------------------------------------------------------

    def get_registers(self) -> dict:
        """Return a dict of AArch64 register names → integer values.

        Covers: x0–x30, sp, pc, and cpsr/pstate.

        The dict keys are lower-case (``"x0"``, ``"sp"``, ``"pc"``).
        """
        # Request all registers in hexadecimal format
        records = self._send_mi('-data-list-register-values x')
        registers: dict = {}
        for rec in records:
            if rec.get('class') == 'done':
                payload = rec.get('payload', '')
                # Parse pairs: {number="N",value="0x..."}
                for m in re.finditer(
                    r'\{number="(\d+)",value="([^"]+)"\}', payload
                ):
                    num = int(m.group(1))
                    val_str = m.group(2)
                    name = self._reg_num_to_name(num)
                    if name:
                        try:
                            registers[name] = int(val_str, 16)
                        except ValueError:
                            registers[name] = val_str
        return registers

    def get_register(self, name: str) -> int | str:
        """Return the value of a single register.

        Parameters
        ----------
        name : str
            Register name (case-insensitive, e.g. ``"X0"``, ``"sp"``, ``"pc"``).
        """
        regs = self.get_registers()
        key = name.lower()
        if key not in regs:
            raise GdbError(
                f'Register {name!r} not found. Available: '
                + ', '.join(sorted(regs.keys()))
            )
        return regs[key]

    def examine_memory(self, address: int | str, count: int = 8,
                       unit: str = 'b') -> list:
        """Read memory at ``address``.

        Parameters
        ----------
        address : int | str
            Memory address (integer or hex string such as ``"0x400000"``).
        count : int
            Number of units to read.
        unit : str
            Unit size: ``'b'`` (byte), ``'h'`` (halfword), ``'w'`` (word),
            ``'g'`` (giant/8-byte).
        """
        if isinstance(address, int):
            address = hex(address)
        records = self._send_mi(
            f'-data-read-memory-bytes {address} {count}'
        )
        results = []
        for rec in records:
            if rec.get('class') == 'done':
                payload = rec.get('payload', '')
                for m in re.finditer(
                    r'\{begin="([^"]+)",offset="([^"]+)",end="([^"]+)",'
                    r'contents="([^"]+)"\}',
                    payload,
                ):
                    results.append({
                        'begin':    m.group(1),
                        'offset':   m.group(2),
                        'end':      m.group(3),
                        'contents': m.group(4),
                    })
        return results

    def get_backtrace(self, max_frames: int = 20) -> list:
        """Return a list of stack frames (dicts with level/addr/func/file/line)."""
        records = self._send_mi(f'-stack-list-frames 0 {max_frames - 1}')
        frames = []
        for rec in records:
            if rec.get('class') == 'done':
                payload = rec.get('payload', '')
                for m in re.finditer(
                    r'\{level="([^"]*)"(?:,addr="([^"]*)")?'
                    r'(?:,func="([^"]*)")?(?:,file="([^"]*)")?'
                    r'(?:,fullname="[^"]*")?(?:,line="([^"]*)")?\}',
                    payload,
                ):
                    frames.append({
                        'level': m.group(1),
                        'addr':  m.group(2) or '?',
                        'func':  m.group(3) or '??',
                        'file':  m.group(4) or '?',
                        'line':  m.group(5) or '?',
                    })
        return frames

    def select_frame(self, level: int) -> None:
        """Select the stack frame at ``level``."""
        self._send_mi(f'-stack-select-frame {level}')

    def evaluate(self, expr: str) -> str:
        """Evaluate a GDB expression and return the result as a string."""
        records = self._send_mi(f'-data-evaluate-expression "{expr}"')
        for rec in records:
            if rec.get('class') == 'done':
                val = _extract_value(rec.get('payload', ''), 'value')
                if val is not None:
                    return val
        raise GdbError(f'Failed to evaluate expression: {expr!r}')

    # ------------------------------------------------------------------
    # Assertion helpers
    # ------------------------------------------------------------------

    def assert_register(self, register: str, expected: int) -> None:
        """Assert that ``register == expected``.

        Parameters
        ----------
        register : str
            Register name (case-insensitive).
        expected : int
            Expected integer value.

        Raises
        ------
        AssertionFailedError
            If the actual value differs from ``expected``.
        """
        actual = self.get_register(register)
        if isinstance(actual, str):
            # Try to parse the string value
            try:
                actual = int(actual, 0)
            except ValueError:
                raise AssertionFailedError(register.lower(), expected, -1)
        if actual != expected:
            raise AssertionFailedError(register.lower(), expected, actual)

    def assert_registers(self, expected: dict) -> list:
        """Assert multiple registers at once.

        Parameters
        ----------
        expected : dict
            Map of register name → expected integer value.

        Returns
        -------
        list[AssertionFailedError]
            List of assertion failures (empty if all pass).
        """
        regs = self.get_registers()
        failures = []
        for reg, exp_val in expected.items():
            key = reg.lower()
            if key not in regs:
                failures.append(
                    AssertionFailedError(key, exp_val, -1)
                )
                continue
            actual = regs[key]
            if isinstance(actual, str):
                try:
                    actual = int(actual, 0)
                except ValueError:
                    failures.append(AssertionFailedError(key, exp_val, -1))
                    continue
            if actual != exp_val:
                failures.append(AssertionFailedError(key, exp_val, actual))
        return failures

    def run_assertion_suite(self, steps: list) -> dict:
        """Run a batch step → assert sequence.

        Parameters
        ----------
        steps : list[dict]
            Each dict may have:
            - ``"action"``: ``"step"`` | ``"next"`` | ``"stepi"`` | ``"nexti"``
              | ``"continue"`` | ``"breakpoint"``
            - ``"count"``: int (for step/next/stepi/nexti)
            - ``"location"``: str (for breakpoint)
            - ``"assert"``: dict of register → expected value
            - ``"note"``: str (human-readable description)

        Returns
        -------
        dict
            ``{"passed": int, "failed": int, "failures": [...]}``
        """
        passed = 0
        failed = 0
        failures = []

        for i, step_spec in enumerate(steps):
            action  = step_spec.get('action', 'step')
            count   = step_spec.get('count', 1)
            note    = step_spec.get('note', f'step {i}')
            asserts = step_spec.get('assert', {})

            try:
                if action == 'step':
                    self.step(count)
                elif action == 'next':
                    self.next(count)
                elif action == 'stepi':
                    self.stepi(count)
                elif action == 'nexti':
                    self.nexti(count)
                elif action == 'continue':
                    self.continue_()
                elif action == 'breakpoint':
                    self.set_breakpoint(step_spec['location'])
                    continue    # no assert after just setting a breakpoint
            except SigilDetectedError as e:
                failures.append({
                    'step': note,
                    'error': 'SIGILL',
                    'pc': hex(e.pc) if e.pc else 'unknown',
                })
                failed += 1
                continue

            if asserts:
                step_failures = self.assert_registers(asserts)
                if step_failures:
                    for f in step_failures:
                        failures.append({
                            'step': note,
                            'register': f.register,
                            'expected': hex(f.expected),
                            'actual': hex(f.actual),
                        })
                        failed += 1
                else:
                    passed += len(asserts)
            else:
                passed += 1

        return {'passed': passed, 'failed': failed, 'failures': failures}

    # ------------------------------------------------------------------
    # SIGILL repair helper
    # ------------------------------------------------------------------

    @staticmethod
    def suggest_sigill_repair(arch: str, pc: int | None = None) -> str:
        """Return a diagnostic message for a SIGILL, including H1 query hint.

        This does not automatically invoke query_allowlist.py; it constructs
        the command string for the user or caller to run.

        Parameters
        ----------
        arch : str
            Architecture version string, e.g. ``"v9Ap4"``.
        pc : int | None
            Program counter of the illegal instruction, if known.

        Returns
        -------
        str
            Formatted repair hint.
        """
        hint = 'SIGILL — Illegal Instruction detected.\n'
        if pc is not None:
            hint += f'  PC at time of fault: {hex(pc)}\n'
        hint += '\n'
        hint += 'To find a valid substitute instruction, query the H1 allowlist:\n'
        hint += (
            f'  python3 tools/query_allowlist.py --arch {arch} --output json\n'
        )
        hint += '\n'
        hint += (
            'Look up the failing instruction in prohibited_operations and find\n'
            'a compatible allowed_operation for your architecture version.\n'
        )
        return hint

    # ------------------------------------------------------------------
    # Internal MI communication
    # ------------------------------------------------------------------

    def _next_token(self) -> int:
        self._token += 1
        return self._token

    def _send_mi(self, command: str) -> list:
        """Send one GDB/MI command and return all response records.

        Returns a list of parsed MI record dicts up to and including the
        ``^done`` / ``^error`` / ``^running`` result record.
        """
        if self._proc is None or self._proc.poll() is not None:
            raise GdbError('GDB process is not running.')

        token = self._next_token()
        line = f'{token}{command}\n'
        self._proc.stdin.write(line)
        self._proc.stdin.flush()
        return self._drain_until_result(token)

    def _drain_until_prompt(self, timeout: float | None = None) -> list:
        """Read lines until the ``(gdb)`` prompt."""
        return self._read_lines_until(
            lambda l: l.strip() == '(gdb)',
            timeout=timeout or self._timeout,
        )

    def _drain_until_result(self, token: int,
                            timeout: float | None = None) -> list:
        """Read lines until a result record matching ``token`` arrives."""
        token_str = str(token)
        records = []

        def is_result(line: str) -> bool:
            return (
                line.startswith(token_str + '^')
                or line.startswith('^')
            )

        lines = self._read_lines_until(
            is_result, timeout=timeout or self._timeout
        )
        for line in lines:
            rec = _parse_mi_record(line)
            records.append(rec)
        return records

    def _exec_and_wait_for_stop(self, command: str) -> dict:
        """Send an execution MI command and wait for the ``*stopped`` record.

        Raises
        ------
        SigilDetectedError
            If the stop reason is ``signal-received`` with signal ``SIGILL``.
        """
        if self._proc is None:
            raise GdbError('GDB session not started.')

        token = self._next_token()
        line = f'{token}{command}\n'
        self._proc.stdin.write(line)
        self._proc.stdin.flush()

        stop_record: dict = {}
        deadline = time.monotonic() + self._timeout

        while time.monotonic() < deadline:
            raw_line = self._proc.stdout.readline()
            if not raw_line:
                break
            raw_line = raw_line.rstrip('\n')
            rec = _parse_mi_record(raw_line)

            if rec.get('type') == 'async-exec':
                if rec.get('class') == 'stopped':
                    stop_record = rec
                    # Check for SIGILL
                    payload = rec.get('payload', '')
                    reason = _extract_value(payload, 'reason')
                    signal_name = _extract_value(payload, 'signal-name')
                    if (reason == 'signal-received'
                            and signal_name == 'SIGILL'):
                        pc_str = _extract_value(payload, 'addr')
                        pc_val = int(pc_str, 16) if pc_str else None
                        raise SigilDetectedError(
                            f'SIGILL at {pc_str or "unknown address"}',
                            pc=pc_val,
                        )
                    return stop_record

            # Drain result record for the command itself
            if raw_line.startswith(str(token) + '^') or raw_line.startswith('^'):
                stop_record = _parse_mi_record(raw_line)
                # For 'running' we keep waiting for the stop
                if stop_record.get('class') not in ('running',):
                    return stop_record

        return stop_record

    def _read_lines_until(
        self, predicate, timeout: float = 10.0
    ) -> list:
        """Read stdout lines until ``predicate(line)`` returns True."""
        lines = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self._proc.stdout.readline()
            if not line:
                break
            line = line.rstrip('\n')
            lines.append(line)
            if predicate(line):
                break
        return lines

    # ------------------------------------------------------------------
    # Register number → name mapping (AArch64)
    # ------------------------------------------------------------------

    # GDB assigns stable numbers to AArch64 registers.
    # Numbers 0–30: x0–x30; 31: sp; 32: pc; 33: cpsr/pstate
    _AARCH64_REG_MAP: dict[int, str] = {
        **{i: f'x{i}' for i in range(31)},
        31: 'sp',
        32: 'pc',
        33: 'pstate',
    }

    def _reg_num_to_name(self, number: int) -> str | None:
        """Map a GDB register number to a canonical AArch64 name."""
        return self._AARCH64_REG_MAP.get(number)


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

def run_assertion_suite_on_binary(
    executable: str | Path,
    steps: list,
    *,
    arch: str = 'v9Ap4',
    gdb_path: str | None = None,
    timeout: float = 30.0,
) -> dict:
    """High-level helper: open a session, run steps, close, return results.

    Parameters
    ----------
    executable : str | Path
        Path to the AArch64 ELF binary to debug.
    steps : list[dict]
        Step/assert sequence as accepted by ``GdbSession.run_assertion_suite()``.
    arch : str
        Architecture version (used in SIGILL repair hints).
    gdb_path : str | None
        Override GDB path.
    timeout : float
        Per-operation timeout in seconds.

    Returns
    -------
    dict
        ``{"passed": int, "failed": int, "failures": list}``
    """
    with GdbSession(executable, gdb_path=gdb_path, timeout=timeout) as gdb:
        return gdb.run_assertion_suite(steps)
