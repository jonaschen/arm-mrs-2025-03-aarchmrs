#!/usr/bin/env python3
"""
gen_qemu_launch.py — AArch64 QEMU launch-script generator and emulation runner.

Generates parametrised QEMU launch scripts for AArch64 system or user-mode
emulation, and provides a run interface that captures exit conditions for
integration with the GDB-MCP (H3) and cross-compilation (H5) skills.

Usage:
    # Generate a system-mode launch script
    gen_qemu_launch.py --mode system --cpu cortex-a57 --memory 4G \
                       --output launch_aarch64.sh

    # Generate a user-mode launch script (simpler, for cross-compiled binaries)
    gen_qemu_launch.py --mode user --output run_aarch64.sh

    # Run a binary directly in user-mode QEMU and report the result
    gen_qemu_launch.py --run ./my_binary [--cpu max] [--timeout 30]

    # Check whether qemu-aarch64 or qemu-system-aarch64 is available
    gen_qemu_launch.py --check

    # List available AArch64 CPUs
    gen_qemu_launch.py --list-cpus

Emulation modes:
    user    qemu-aarch64 (or qemu-aarch64-static) — runs a single AArch64
            user-space binary on an x86-64 host, intercepting Linux syscalls.
            Fastest for unit-testing cross-compiled binaries.
    system  qemu-system-aarch64 — full system emulation with UEFI firmware,
            virtio NIC, SMMU.  Required for kernel/EL1/EL2 testing.

Exit codes returned by --run:
    0       binary exited with status 0
    N       binary exited with status N
    124     timeout (QEMU did not exit within --timeout seconds)
    139     SIGSEGV detected
    132     SIGILL detected (suggests arm-allowlist / arm-gdb repair)

Result classification:
    pass     exit code 0
    fail     non-zero exit code
    sigill   exit code 132 (SIGILL)
    sigsegv  exit code 139 (SIGSEGV)
    timeout  QEMU did not complete within the timeout

Environment:
    ARM_QEMU_USER_PATH    Override user-mode QEMU binary path
    ARM_QEMU_SYSTEM_PATH  Override system-mode QEMU binary path

Standard QEMU configuration target (system mode):
    qemu-system-aarch64 \\
        -machine virt,iommu=smmuv3 \\
        -cpu cortex-a57 \\
        -accel tcg \\
        -m 4G \\
        -pflash edk2-aarch64-code.fd \\
        -pflash edk2-arm-vars.fd \\
        -nic user \\
        -nographic
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# QEMU binary discovery
# ---------------------------------------------------------------------------

_USER_QEMU_NAMES   = ['qemu-aarch64', 'qemu-aarch64-static']
_SYSTEM_QEMU_NAMES = ['qemu-system-aarch64']

# Signal values as exit codes in QEMU user-mode
_SIGILL_EXIT  = 132   # 128 + SIGILL (4)
_SIGSEGV_EXIT = 139   # 128 + SIGSEGV (11)
_TIMEOUT_EXIT = 124


def find_qemu(mode: str = 'user') -> str | None:
    """Return the path to a QEMU binary for ``mode`` (``'user'`` or ``'system'``).

    Returns ``None`` if no suitable binary is found (does not raise).
    """
    env_key = (
        'ARM_QEMU_USER_PATH' if mode == 'user' else 'ARM_QEMU_SYSTEM_PATH'
    )
    env_val = os.environ.get(env_key)
    if env_val:
        if shutil.which(env_val):
            return env_val
        return None

    names = _USER_QEMU_NAMES if mode == 'user' else _SYSTEM_QEMU_NAMES
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def qemu_available(mode: str = 'user') -> bool:
    """Return True if QEMU is available for the given mode."""
    return find_qemu(mode) is not None


# ---------------------------------------------------------------------------
# CPU catalogue
# ---------------------------------------------------------------------------

# Representative AArch64 CPUs available in QEMU (not exhaustive)
QEMU_CPUS: dict[str, str] = {
    # QEMU generic target (enables most features)
    'max':           'Maximum features supported by this QEMU build',

    # Cortex-A series
    'cortex-a35':    'Armv8.0-A, 2-wide OOO, 32 KB L1I+D; IoT/embedded',
    'cortex-a53':    'Armv8.0-A, 2-wide in-order; low-power mobile',
    'cortex-a55':    'Armv8.2-A, 4-wide in-order + DotProd; mobile/IoT',
    'cortex-a57':    'Armv8.0-A, 3-wide OOO; server/desktop (legacy)',
    'cortex-a72':    'Armv8.0-A, 3-wide OOO; mid-range server',
    'cortex-a76':    'Armv8.2-A, 4-wide OOO; high-performance mobile',
    'cortex-a710':   'Armv9.0-A, 5-wide OOO + SVE2; latest big core',

    # Neoverse server
    'neoverse-n1':   'Armv8.4-A, 4-wide OOO; cloud/HPC server (N1)',
    'neoverse-v1':   'Armv8.4-A + SVE; high-perf cloud server (V1)',

    # Cortex-X
    'cortex-x1':     'Armv8.2-A, 7-wide OOO; ultra-high-perf mobile',
}


# ---------------------------------------------------------------------------
# Launch script generators
# ---------------------------------------------------------------------------

def gen_user_mode_script(
    *,
    cpu: str = 'max',
    env_vars: dict | None = None,
    extra_args: list | None = None,
    static: bool = False,
) -> str:
    """Generate a user-mode QEMU launch shell script fragment.

    The generated script expects the binary path as its first argument
    (``$1``), forwarding any remaining arguments (``"$@"``).

    Parameters
    ----------
    cpu : str
        CPU model to pass to ``-cpu`` (use ``'max'`` for maximum features).
    env_vars : dict | None
        Additional environment variables to set before the QEMU command.
    extra_args : list | None
        Extra flags to append to the QEMU command line.
    static : bool
        If True, use ``qemu-aarch64-static`` (for static binaries in
        non-binfmt_misc environments).
    """
    env_vars = env_vars or {}
    extra_args = extra_args or []

    qemu_binary = 'qemu-aarch64-static' if static else 'qemu-aarch64'

    lines = [
        '#!/usr/bin/env bash',
        '# Auto-generated by gen_qemu_launch.py (arm-qemu skill)',
        '# AArch64 user-mode QEMU launch script',
        '#',
        '# Usage: ./run_aarch64.sh <binary> [args...]',
        '',
        'set -euo pipefail',
        '',
    ]

    for k, v in env_vars.items():
        lines.append(f'export {k}={v!r}')

    if env_vars:
        lines.append('')

    cmd_parts = [qemu_binary, f'-cpu {cpu}'] + extra_args + ['"$@"']
    lines.append('exec ' + ' \\\n    '.join(cmd_parts))
    lines.append('')

    return '\n'.join(lines)


def gen_system_mode_script(
    *,
    cpu: str = 'cortex-a57',
    memory: str = '4G',
    accel: str = 'tcg',
    machine: str = 'virt,iommu=smmuv3',
    firmware_code: str = 'edk2-aarch64-code.fd',
    firmware_vars: str = 'edk2-arm-vars.fd',
    nic: str = 'user',
    extra_args: list | None = None,
    nographic: bool = True,
    kernel: str | None = None,
    dtb: str | None = None,
    drive: str | None = None,
) -> str:
    """Generate a full system-mode QEMU launch shell script.

    Matches the standard QEMU configuration from the design plan:
        qemu-system-aarch64 -machine virt,iommu=smmuv3 -cpu cortex-a57
        -accel tcg -m 4G -pflash edk2-aarch64-code.fd
        -pflash edk2-arm-vars.fd -nic user -nographic

    Parameters
    ----------
    cpu : str
        CPU model (e.g. ``'cortex-a57'``, ``'max'``).
    memory : str
        RAM size (e.g. ``'4G'``, ``'2G'``, ``'512M'``).
    accel : str
        Accelerator: ``'tcg'`` (software), ``'kvm'``, or ``'hvf'``.
    machine : str
        QEMU machine type.
    firmware_code : str
        Path to the UEFI code flash image.
    firmware_vars : str
        Path to the UEFI variables flash image (writable copy recommended).
    nic : str
        NIC model (``'user'`` for user-mode networking, ``'none'`` to disable).
    extra_args : list | None
        Additional flags to append.
    nographic : bool
        If True, add ``-nographic`` (redirect serial to terminal).
    kernel : str | None
        If set, add ``-kernel <path>`` (Linux direct-kernel boot).
    dtb : str | None
        If set, add ``-dtb <path>``.
    drive : str | None
        If set, add ``-drive file=<path>,format=qcow2``.
    """
    extra_args = extra_args or []

    lines = [
        '#!/usr/bin/env bash',
        '# Auto-generated by gen_qemu_launch.py (arm-qemu skill)',
        '# AArch64 system-mode QEMU launch script',
        '#',
        '# Requirements:',
        '#   qemu-system-aarch64    (sudo apt install qemu-system-arm)',
        f'#   {firmware_code}  (UEFI firmware)',
        f'#   {firmware_vars}  (UEFI variables — keep a writable copy)',
        '',
        'set -euo pipefail',
        '',
        'QEMU=qemu-system-aarch64',
        '',
        'exec "$QEMU" \\',
        f'    -machine {machine} \\',
        f'    -cpu {cpu} \\',
        f'    -accel {accel} \\',
        f'    -m {memory} \\',
        f'    -pflash {firmware_code} \\',
        f'    -pflash {firmware_vars} \\',
        f'    -nic {nic} \\',
    ]

    if kernel:
        lines.append(f'    -kernel {kernel} \\')
    if dtb:
        lines.append(f'    -dtb {dtb} \\')
    if drive:
        lines.append(f'    -drive file={drive},format=qcow2 \\')
    for arg in extra_args:
        lines.append(f'    {arg} \\')
    if nographic:
        lines.append('    -nographic')
    else:
        # Remove trailing backslash from last option
        if lines and lines[-1].endswith(' \\'):
            lines[-1] = lines[-1][:-2]

    lines.append('')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Run helpers
# ---------------------------------------------------------------------------

class QemuResult:
    """Result of a QEMU user-mode run.

    Attributes
    ----------
    exit_code : int
        Process exit code (or ``_TIMEOUT_EXIT`` on timeout).
    stdout : str
        Combined stdout of the binary.
    stderr : str
        Combined stderr / QEMU messages.
    elapsed : float
        Wall-clock seconds.
    classification : str
        One of: ``'pass'``, ``'fail'``, ``'sigill'``, ``'sigsegv'``,
        ``'timeout'``.
    sigill_pc : str | None
        Address hint from stderr if a SIGILL was detected.
    """

    def __init__(self, exit_code: int, stdout: str, stderr: str,
                 elapsed: float):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.elapsed = elapsed
        self.classification = self._classify(exit_code, stderr)
        self.sigill_pc: str | None = self._extract_sigill_pc(stderr)

    @staticmethod
    def _classify(exit_code: int, stderr: str) -> str:
        if exit_code == _TIMEOUT_EXIT:
            return 'timeout'
        if exit_code == _SIGILL_EXIT or 'Illegal instruction' in stderr:
            return 'sigill'
        if exit_code == _SIGSEGV_EXIT or 'Segmentation fault' in stderr:
            return 'sigsegv'
        if exit_code == 0:
            return 'pass'
        return 'fail'

    @staticmethod
    def _extract_sigill_pc(stderr: str) -> str | None:
        """Try to extract the PC from QEMU's SIGILL message."""
        m = re.search(r'(?:pc|PC)[:=]\s*(0x[0-9a-fA-F]+)', stderr)
        return m.group(1) if m else None

    def to_dict(self) -> dict:
        return {
            'exit_code':      self.exit_code,
            'classification': self.classification,
            'elapsed':        round(self.elapsed, 3),
            'stdout':         self.stdout,
            'stderr':         self.stderr,
            'sigill_pc':      self.sigill_pc,
        }

    def __repr__(self) -> str:
        return (
            f'QemuResult(exit={self.exit_code}, '
            f'class={self.classification!r}, '
            f't={self.elapsed:.2f}s)'
        )


def run_binary(
    binary: str | Path,
    args: list | None = None,
    *,
    cpu: str = 'max',
    timeout: float = 30.0,
    env: dict | None = None,
) -> QemuResult:
    """Run an AArch64 binary under user-mode QEMU and return a QemuResult.

    Parameters
    ----------
    binary : str | Path
        Path to the AArch64 ELF binary.
    args : list | None
        Arguments to pass to the binary.
    cpu : str
        QEMU CPU model.
    timeout : float
        Maximum run time in seconds.
    env : dict | None
        Additional environment variables for the QEMU process.

    Returns
    -------
    QemuResult
        Structured result including classification and captured output.
    """
    qemu = find_qemu('user')
    if not qemu:
        raise RuntimeError(
            'QEMU user-mode not found. Install with:\n'
            '    sudo apt install qemu-user-static\n'
            'or set ARM_QEMU_USER_PATH.'
        )

    cmd = [qemu, '-cpu', cpu, str(binary)] + (args or [])
    proc_env = dict(os.environ)
    if env:
        proc_env.update(env)

    t0 = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=proc_env,
        )
        exit_code = proc.returncode
        stdout    = proc.stdout
        stderr    = proc.stderr
    except subprocess.TimeoutExpired as e:
        timed_out = True
        exit_code = _TIMEOUT_EXIT
        stdout    = e.stdout or ''
        stderr    = e.stderr or ''
    elapsed = time.monotonic() - t0

    return QemuResult(exit_code, stdout, stderr, elapsed)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='AArch64 QEMU launch-script generator and emulation runner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Mode selection
    mode_grp = parser.add_mutually_exclusive_group()
    mode_grp.add_argument(
        '--check', action='store_true',
        help='Check whether qemu-aarch64 / qemu-system-aarch64 is installed',
    )
    mode_grp.add_argument(
        '--list-cpus', action='store_true',
        help='List available AArch64 CPU models',
    )
    mode_grp.add_argument(
        '--run', metavar='BINARY',
        help='Run a binary under user-mode QEMU and report the result',
    )

    # Launch script generation
    parser.add_argument(
        '--mode', choices=['user', 'system'], default='user',
        help='Emulation mode: user (default) or system',
    )
    parser.add_argument(
        '--cpu', default='max',
        help='CPU model (default: max; use --list-cpus to see options)',
    )
    parser.add_argument(
        '--memory', default='4G',
        help='RAM size for system mode (default: 4G)',
    )
    parser.add_argument(
        '--accel', default='tcg', choices=['tcg', 'kvm', 'hvf'],
        help='Accelerator for system mode (default: tcg)',
    )
    parser.add_argument(
        '--output', metavar='FILE',
        help='Write the generated launch script to FILE (default: stdout)',
    )
    parser.add_argument(
        '--static', action='store_true',
        help='Use qemu-aarch64-static for user mode (for static binaries)',
    )
    parser.add_argument(
        '--timeout', type=float, default=30.0,
        help='Timeout in seconds for --run (default: 30)',
    )
    parser.add_argument(
        '--json', action='store_true',
        help='Output --run result as JSON',
    )
    parser.add_argument(
        '--kernel', metavar='PATH',
        help='Linux kernel image for system-mode direct-kernel boot',
    )
    parser.add_argument(
        '--drive', metavar='PATH',
        help='Disk image path (qcow2) for system mode',
    )

    args = parser.parse_args()

    # --check
    if args.check:
        found_any = False
        for mode in ('user', 'system'):
            path = find_qemu(mode)
            if path:
                print(f'QEMU {mode}-mode: {path}')
                found_any = True
            else:
                print(f'QEMU {mode}-mode: NOT FOUND')
        if not found_any:
            print(
                '\nInstall with:\n'
                '    sudo apt install qemu-user-static qemu-system-arm',
                file=sys.stderr,
            )
            return 1
        return 0

    # --list-cpus
    if args.list_cpus:
        print('Available AArch64 CPU models for QEMU:\n')
        for cpu, desc in QEMU_CPUS.items():
            print(f'  {cpu:<18}  {desc}')
        print()
        print('Pass the CPU model name to --cpu or in the generated script.')
        return 0

    # --run <binary>
    if args.run:
        binary = args.run
        if not Path(binary).exists():
            print(f'ERROR: Binary not found: {binary}', file=sys.stderr)
            return 1
        if not qemu_available('user'):
            print(
                'ERROR: QEMU user-mode not found.\n'
                '    sudo apt install qemu-user-static',
                file=sys.stderr,
            )
            return 1

        print(f'Running under qemu-aarch64 (cpu={args.cpu}, '
              f'timeout={args.timeout}s)…')
        result = run_binary(binary, cpu=args.cpu, timeout=args.timeout)

        if args.json:
            import json as json_mod
            print(json_mod.dumps(result.to_dict(), indent=2))
        else:
            print(f'Classification : {result.classification.upper()}')
            print(f'Exit code      : {result.exit_code}')
            print(f'Elapsed        : {result.elapsed:.2f}s')
            if result.stdout.strip():
                print(f'stdout:\n{result.stdout.rstrip()}')
            if result.stderr.strip():
                print(f'stderr:\n{result.stderr.rstrip()}')
            if result.classification == 'sigill':
                print('\nSIGILL detected — consult arm-allowlist for repair:')
                print('    python3 tools/query_allowlist.py --arch v9Ap4 '
                      '--output json')

        # Route back to H3 (GDB) or H5 (re-compile) based on exit condition
        if result.classification in ('sigill', 'sigsegv'):
            return 132 if result.classification == 'sigill' else 139
        return 0 if result.classification == 'pass' else result.exit_code

    # Script generation (default when no --run/--check/--list-cpus)
    if args.mode == 'user':
        script = gen_user_mode_script(cpu=args.cpu, static=args.static)
    else:
        script = gen_system_mode_script(
            cpu=args.cpu,
            memory=args.memory,
            accel=args.accel,
            kernel=args.kernel,
            drive=args.drive,
        )

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(script)
        out_path.chmod(0o755)
        print(f'Launch script written to: {out_path}')
    else:
        print(script, end='')

    return 0


if __name__ == '__main__':
    sys.exit(main())
