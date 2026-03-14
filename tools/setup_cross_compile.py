#!/usr/bin/env python3
"""
setup_cross_compile.py — AArch64 cross-compilation environment setup and build tool.

Manages the aarch64-linux-gnu-gcc toolchain for producing AArch64 binaries
that can be tested in H4's QEMU environment.

Usage:
    # Check toolchain availability
    setup_cross_compile.py --check

    # Install the cross-compilation toolchain (requires sudo)
    setup_cross_compile.py --setup

    # Compile a C source file
    setup_cross_compile.py --compile hello.c --out hello_aarch64
    setup_cross_compile.py --compile hello.c --out hello_aarch64 --link static
    setup_cross_compile.py --compile hello.c --out hello_aarch64 \\
        --arch v9Ap0 --feat FEAT_SVE2

    # Get a repair hint for a compiler/linker error
    setup_cross_compile.py --repair-hint "ld-linux-aarch64.so.1: No such file"
    setup_cross_compile.py --repair-hint "illegal instruction"

    # Show the link-strategy decision table
    setup_cross_compile.py --link-strategy

Linking strategies:
    auto     Auto-detect based on availability of AArch64 sysroot (default)
    static   -static (no dynamic libraries; works everywhere)
    dynamic  Multiarch with AArch64 shared libraries installed
    musl     Musl libc + -static (minimal binary; requires musl-tools)

Architecture flag mapping (for use with --arch / --feat):
    v8Ap0   → -march=armv8-a   (AArch64 baseline)
    v8Ap2   → -march=armv8.2-a
    v9Ap0   → -march=armv9-a
    v9Ap4   → -march=armv9.4-a
    FEAT_SVE  → +sve
    FEAT_SVE2 → +sve2
    FEAT_SME  → +sme
    FEAT_FP16 → +fp16
    FEAT_LSE  → +lse
    FEAT_DOTPROD → +dotprod
    FEAT_BF16    → +bf16

Compile-error repair rules:
    20 rule categories covering the most common AArch64 cross-compilation
    errors; see --repair-hint for interactive look-up.

Environment:
    ARM_CC_AARCH64   Override the AArch64 C compiler (default: aarch64-linux-gnu-gcc)
    ARM_CXX_AARCH64  Override the AArch64 C++ compiler (default: aarch64-linux-gnu-g++)
    ARM_SYSROOT      Override the sysroot path for dynamic linking
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Toolchain configuration
# ---------------------------------------------------------------------------

_DEFAULT_CC   = 'aarch64-linux-gnu-gcc'
_DEFAULT_CXX  = 'aarch64-linux-gnu-g++'
_DEFAULT_AS   = 'aarch64-linux-gnu-as'
_DEFAULT_LD   = 'aarch64-linux-gnu-ld'
_DEFAULT_OBJDUMP = 'aarch64-linux-gnu-objdump'


def find_tool(name: str, env_key: str | None = None) -> str | None:
    """Return the path to a cross-tool, or None if not found."""
    if env_key:
        override = os.environ.get(env_key)
        if override:
            return override if shutil.which(override) else None
    return shutil.which(name)


def get_cc() -> str | None:
    return find_tool(_DEFAULT_CC, 'ARM_CC_AARCH64')


def get_cxx() -> str | None:
    return find_tool(_DEFAULT_CXX, 'ARM_CXX_AARCH64')


def toolchain_available() -> bool:
    """Return True if the AArch64 cross-compiler is installed."""
    return get_cc() is not None


# ---------------------------------------------------------------------------
# Architecture version → march flag mapping
# ---------------------------------------------------------------------------

_ARCH_MARCH: dict = {
    'v8Ap0':  'armv8-a',
    'v8Ap1':  'armv8.1-a',
    'v8Ap2':  'armv8.2-a',
    'v8Ap3':  'armv8.3-a',
    'v8Ap4':  'armv8.4-a',
    'v8Ap5':  'armv8.5-a',
    'v8Ap6':  'armv8.6-a',
    'v8Ap7':  'armv8.7-a',
    'v8Ap8':  'armv8.8-a',
    'v8Ap9':  'armv8.9-a',
    'v9Ap0':  'armv9-a',
    'v9Ap1':  'armv9.1-a',
    'v9Ap2':  'armv9.2-a',
    'v9Ap3':  'armv9.3-a',
    'v9Ap4':  'armv9.4-a',
    'v9Ap5':  'armv9.5-a',
    'v9Ap6':  'armv9.6-a',
}

# Feature → +extension suffix for -march
_FEAT_EXTENSION: dict = {
    'FEAT_SVE':      'sve',
    'FEAT_SVE2':     'sve2',
    'FEAT_SME':      'sme',
    'FEAT_SME2':     'sme2',
    'FEAT_FP16':     'fp16',
    'FEAT_LSE':      'lse',
    'FEAT_LSE2':     'lse2',
    'FEAT_DOTPROD':  'dotprod',
    'FEAT_BF16':     'bf16',
    'FEAT_I8MM':     'i8mm',
    'FEAT_MTE':      'memtag',
    'FEAT_MTE2':     'memtag2',
    'FEAT_BTI':      'bti',
    'FEAT_PAUTH':    'pauth',
    'FEAT_SSBS':     'ssbs',
    'FEAT_RNG':      'rng',
    'FEAT_CRC32':    'crc',
    'FEAT_PMULL':    'aes',     # PMULL is bundled with AES on AArch64
    'FEAT_SHA1':     'sha1',
    'FEAT_SHA256':   'sha2',
    'FEAT_SHA3':     'sha3',
    'FEAT_SHA512':   'sha512',
}


def arch_to_march_flag(arch: str, features: list | None = None) -> str:
    """Convert an arch version string and feature list to a GCC -march flag.

    Parameters
    ----------
    arch : str
        Architecture version (e.g. ``'v9Ap4'``).
    features : list[str] | None
        FEAT_* names to enable as extensions.

    Returns
    -------
    str
        GCC march flag (e.g. ``'-march=armv9.4-a+sve2'``).

    Raises
    ------
    ValueError
        If ``arch`` is not a known version string.
    """
    base = _ARCH_MARCH.get(arch)
    if base is None:
        known = ', '.join(sorted(_ARCH_MARCH.keys()))
        raise ValueError(
            f'Unknown architecture version {arch!r}. '
            f'Known versions: {known}'
        )

    extensions = []
    for feat in (features or []):
        ext = _FEAT_EXTENSION.get(feat)
        if ext:
            extensions.append(ext)
        else:
            # Unknown feature — emit a comment-style hint but don't abort
            pass

    suffix = ('+' + '+'.join(extensions)) if extensions else ''
    return f'-march={base}{suffix}'


# ---------------------------------------------------------------------------
# Link strategy decision
# ---------------------------------------------------------------------------

_LINK_STRATEGY_TABLE = """
Linking strategy decision table for AArch64 cross-compiled binaries:
─────────────────────────────────────────────────────────────────────
Target environment         Recommended strategy   Flags
─────────────────────────────────────────────────────────────────────
QEMU bare-metal test       static                 -static
Minimal binary (low-level) musl                   -static (musl libc)
CI / embedded Linux        static                 -static
Full dynamic needed        dynamic                Multiarch sysroot
─────────────────────────────────────────────────────────────────────
Auto-detection logic:
  1. If aarch64 sysroot has libc.so → dynamic
  2. If musl-gcc wrapper available → musl
  3. Otherwise → static (safest fallback)
"""


def detect_link_strategy() -> str:
    """Auto-detect the best link strategy for the current host.

    Returns one of: ``'static'``, ``'dynamic'``, ``'musl'``.
    """
    # Check for dynamic: does an aarch64 sysroot/libc exist?
    sysroot = os.environ.get('ARM_SYSROOT', '')
    if sysroot:
        libc = Path(sysroot) / 'lib' / 'aarch64-linux-gnu' / 'libc.so.6'
        if libc.exists():
            return 'dynamic'

    # Standard Debian/Ubuntu multiarch path
    multiarch_libc = Path('/usr/lib/aarch64-linux-gnu/libc.so.6')
    if multiarch_libc.exists():
        return 'dynamic'

    # Check for musl-gcc wrapper
    if shutil.which('musl-gcc'):
        return 'musl'

    return 'static'


def link_flags(strategy: str) -> list:
    """Return the GCC flags for a given link strategy.

    Parameters
    ----------
    strategy : str
        One of: ``'auto'``, ``'static'``, ``'dynamic'``, ``'musl'``.
    """
    if strategy == 'auto':
        strategy = detect_link_strategy()

    if strategy == 'static':
        return ['-static']
    if strategy == 'musl':
        return ['-static']   # caller should prefix with musl-gcc
    if strategy == 'dynamic':
        return []   # rely on the installed multiarch sysroot
    raise ValueError(f'Unknown link strategy {strategy!r}')


# ---------------------------------------------------------------------------
# Compile-error repair rule library (H5-4 — 20 rules)
# ---------------------------------------------------------------------------

# Each rule is a dict with:
#   pattern   re pattern matched against the error message (case-insensitive)
#   cause     human-readable root cause
#   fix       actionable repair instructions
#   docs_url  optional ARM / GCC documentation reference

REPAIR_RULES: list = [
    # ---- Dynamic / shared library errors --------------------------------
    {
        'id':  'R01',
        'pattern': r'ld-linux-aarch64\.so\.1.*no such file',
        'cause': 'Missing AArch64 dynamic linker — shared objects not installed',
        'fix': (
            'Switch to static linking:\n'
            '    setup_cross_compile.py --compile FILE --link static\n'
            'Or install multiarch support:\n'
            '    sudo dpkg --add-architecture arm64\n'
            '    sudo apt update && sudo apt install libc6:arm64'
        ),
    },
    {
        'id':  'R02',
        'pattern': r'cannot find -l(?!c\b)',
        'cause': 'Missing AArch64 shared library (linker cannot find -lXXX)',
        'fix': (
            'Use static linking to avoid sysroot dependencies:\n'
            '    setup_cross_compile.py --compile FILE --link static\n'
            'Or install the AArch64 variant of the library:\n'
            '    sudo apt install lib<NAME>-dev:arm64'
        ),
    },
    {
        'id':  'R03',
        'pattern': r'cannot find -lc\b',
        'cause': 'AArch64 libc not found for static link',
        'fix': (
            'Install the AArch64 static libc:\n'
            '    sudo apt install libc6-dev-arm64-cross\n'
            'Or use Musl libc:\n'
            '    sudo apt install musl-tools\n'
            '    setup_cross_compile.py --compile FILE --link musl'
        ),
    },

    # ---- Illegal instruction / ISA errors --------------------------------
    {
        'id':  'R04',
        'pattern': r'illegal instruction',
        'cause': 'Generated code contains an instruction not supported by the target CPU',
        'fix': (
            'Query the H1 allowlist to find valid alternatives:\n'
            '    python3 tools/query_allowlist.py --arch <VERSION> --output json\n'
            'Then lower the -march flag to match your target CPU:\n'
            '    setup_cross_compile.py --compile FILE --arch v8Ap0\n'
            'Use --cpu in gen_qemu_launch.py to match the same CPU.'
        ),
    },
    {
        'id':  'R05',
        'pattern': r'-march.*not recognized|invalid feature.*-march',
        'cause': 'The -march extension is not supported by the installed GCC version',
        'fix': (
            'Check the GCC version supports the requested extension:\n'
            '    aarch64-linux-gnu-gcc --version\n'
            'Lower the arch version or remove the unsupported extension:\n'
            '    setup_cross_compile.py --compile FILE --arch v8Ap0'
        ),
    },
    {
        'id':  'R06',
        'pattern': r'error: unknown target triple.*aarch64',
        'cause': 'Compiler does not target AArch64',
        'fix': (
            'Ensure you are using the cross-compiler, not the host compiler:\n'
            '    sudo apt install gcc-aarch64-linux-gnu\n'
            'Then re-run with the correct toolchain prefix.'
        ),
    },

    # ---- Symbol / declaration errors ------------------------------------
    {
        'id':  'R07',
        'pattern': r'undefined reference to `(\w+)',
        'cause': 'Linker cannot find the symbol — missing library or wrong architecture',
        'fix': (
            'Check the symbol exists in the AArch64 library:\n'
            '    aarch64-linux-gnu-nm -D /path/to/libXXX.a | grep SYMBOL\n'
            'Add the missing library with -lXXX, or use static linking.'
        ),
    },
    {
        'id':  'R08',
        'pattern': r'implicit declaration of function',
        'cause': 'Missing #include or function not declared for the target',
        'fix': (
            'Add the required #include at the top of the source file.\n'
            'Compile with -Wall to catch all implicit declarations early.'
        ),
    },
    {
        'id':  'R09',
        'pattern': r"error: '(\w+)' undeclared",
        'cause': 'Variable or macro not declared — possibly a Linux-specific API',
        'fix': (
            'Ensure target-specific APIs are guarded with the right macros:\n'
            '    #define _GNU_SOURCE  before system headers\n'
            'Check the arm64 sysroot header provides this symbol.'
        ),
    },

    # ---- ABI / relocation errors ----------------------------------------
    {
        'id':  'R10',
        'pattern': r'relocation truncated|out of range',
        'cause': 'Branch or addressing range exceeded (common with large static binaries)',
        'fix': (
            'Use position-independent code:\n'
            '    setup_cross_compile.py --compile FILE --extra-flags "-fPIC"\n'
            'Or split the binary into smaller translation units.'
        ),
    },
    {
        'id':  'R11',
        'pattern': r'R_AARCH64_.*not supported',
        'cause': 'Unsupported AArch64 relocation type — linker version mismatch',
        'fix': (
            'Update binutils:\n'
            '    sudo apt install binutils-aarch64-linux-gnu\n'
            'Check the output of: aarch64-linux-gnu-ld --version'
        ),
    },
    {
        'id':  'R12',
        'pattern': r'incompatible with ABI',
        'cause': 'Object file compiled with a different ABI (e.g. soft-float vs hard-float)',
        'fix': (
            'Compile all objects with the same ABI flags:\n'
            '    aarch64-linux-gnu-gcc -mabi=lp64  (default; do not mix)\n'
            'Clean build and recompile all object files.'
        ),
    },

    # ---- Stack / alignment errors ----------------------------------------
    {
        'id':  'R13',
        'pattern': r'stack.*not 16-byte aligned|stack alignment',
        'cause': 'Function call with misaligned stack (AArch64 requires 16-byte alignment)',
        'fix': (
            'Ensure the stack pointer is always 16-byte aligned before BL:\n'
            '    sub sp, sp, #16     ; allocate an extra 16 bytes if needed\n'
            'AArch64 ABI requirement: SP must be 16-byte aligned at call sites.'
        ),
    },
    {
        'id':  'R14',
        'pattern': r'error: address of.*not aligned',
        'cause': 'SIMD / load-pair instruction alignment violation',
        'fix': (
            'Use __attribute__((aligned(16))) on the data structure, or:\n'
            '    LDP/STP require 16-byte aligned addresses.\n'
            'Replace with non-pair LDR/STR if alignment cannot be guaranteed.'
        ),
    },

    # ---- SVE / SIMD errors -----------------------------------------------
    {
        'id':  'R15',
        'pattern': r"error: ACLE function.*requires target feature '?sve",
        'cause': 'SVE intrinsic used but SVE not enabled in -march',
        'fix': (
            'Enable SVE in the -march flag:\n'
            '    setup_cross_compile.py --compile FILE --feat FEAT_SVE\n'
            'Or check feature availability first:\n'
            '    python3 tools/query_feature.py FEAT_SVE'
        ),
    },
    {
        'id':  'R16',
        'pattern': r"requires target feature '?sme",
        'cause': 'SME intrinsic used but SME not enabled in -march',
        'fix': (
            'Enable SME in the -march flag:\n'
            '    setup_cross_compile.py --compile FILE --feat FEAT_SME\n'
            'Or check feature availability:\n'
            '    python3 tools/query_feature.py FEAT_SME'
        ),
    },
    {
        'id':  'R17',
        'pattern': r'error: argument.*out of range.*neon|neon.*not available',
        'cause': 'NEON intrinsic argument out of range, or NEON not available',
        'fix': (
            'Check the NEON intrinsic argument constraints in the ARM ACLE.\n'
            'Ensure target supports NEON:\n'
            '    python3 tools/query_feature.py FEAT_AdvSIMD'
        ),
    },

    # ---- Pointer authentication / BTI ------------------------------------
    {
        'id':  'R18',
        'pattern': r'PACIASP.*not compatible|pauth.*not enabled',
        'cause': 'PAC instructions used but pointer authentication not enabled',
        'fix': (
            'Enable PAC/BTI in the -march flag:\n'
            '    setup_cross_compile.py --compile FILE --feat FEAT_PAUTH\n'
            'Or compile with: -mbranch-protection=standard\n'
            '    (enables PAC + BTI automatically for Armv8.5-A+)'
        ),
    },
    {
        'id':  'R19',
        'pattern': r'BTI.*landing pad|bti.*not enabled',
        'cause': 'BTI landing-pad missing, or BTI not enabled on target',
        'fix': (
            'Enable BTI and add landing pads to indirect branch targets:\n'
            '    compile with: -mbranch-protection=bti\n'
            '    or: -mbranch-protection=standard (PAC + BTI)\n'
            'Check feature support: python3 tools/query_feature.py FEAT_BTI'
        ),
    },

    # ---- Generic compilation errors --------------------------------------
    {
        'id':  'R20',
        'pattern': r'error: ld returned 1 exit status',
        'cause': 'Linker failed — see preceding error lines for the actual cause',
        'fix': (
            'Scroll up in the build output to find the linker error.\n'
            'Common fixes:\n'
            '  - Add missing -l flags\n'
            '  - Switch to --link static\n'
            '  - Check --arch matches the target CPU\n'
            'Run with --verbose for the full linker command.'
        ),
    },
]


def find_repair_rules(error_message: str) -> list:
    """Return repair rules matching ``error_message``.

    Parameters
    ----------
    error_message : str
        Compiler or linker error text.

    Returns
    -------
    list[dict]
        Matching repair rules (may be empty).
    """
    msg_lower = error_message.lower()
    matches = []
    for rule in REPAIR_RULES:
        if re.search(rule['pattern'], msg_lower, re.IGNORECASE):
            matches.append(rule)
    return matches


# ---------------------------------------------------------------------------
# Compile helper
# ---------------------------------------------------------------------------

def cross_compile(
    source: str | Path,
    out: str | Path | None = None,
    *,
    arch: str | None = None,
    features: list | None = None,
    link: str = 'auto',
    extra_flags: list | None = None,
    cxx: bool = False,
    verbose: bool = False,
) -> tuple:
    """Compile a C/C++ source file for AArch64.

    Parameters
    ----------
    source : str | Path
        Path to the C or C++ source file.
    out : str | Path | None
        Output binary path.  Defaults to ``<source stem>_aarch64``.
    arch : str | None
        Architecture version (e.g. ``'v9Ap4'``).  If None, uses the
        compiler default (armv8-a).
    features : list[str] | None
        FEAT_* feature names to enable as -march extensions.
    link : str
        Link strategy: ``'auto'``, ``'static'``, ``'dynamic'``, ``'musl'``.
    extra_flags : list[str] | None
        Extra compiler flags.
    cxx : bool
        If True, use the C++ compiler.
    verbose : bool
        If True, print the compiler command before running it.

    Returns
    -------
    tuple[int, str, str]
        ``(returncode, stdout, stderr)``
    """
    source = Path(source)
    if out is None:
        out = source.parent / (source.stem + '_aarch64')

    compiler = get_cxx() if cxx else get_cc()
    if not compiler:
        return 1, '', (
            'AArch64 cross-compiler not found.\n'
            '    sudo apt install gcc-aarch64-linux-gnu\n'
        )

    cmd = [compiler]

    # -march flag
    if arch:
        try:
            cmd.append(arch_to_march_flag(arch, features))
        except ValueError as e:
            return 1, '', str(e)
    elif features:
        # features without explicit arch — default to armv8-a
        try:
            cmd.append(arch_to_march_flag('v8Ap0', features))
        except ValueError as e:
            return 1, '', str(e)

    # Linking flags
    try:
        cmd.extend(link_flags(link))
    except ValueError as e:
        return 1, '', str(e)

    cmd.extend(extra_flags or [])
    cmd += [str(source), '-o', str(out)]

    if verbose:
        print('Command: ' + ' '.join(cmd))

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 1, '', 'Compilation timed out after 120 seconds.'
    except FileNotFoundError:
        return 1, '', f'Compiler not found: {compiler}'


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='AArch64 cross-compilation environment setup and build tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        '--check', action='store_true',
        help='Check whether the AArch64 cross-compiler is installed',
    )
    mode.add_argument(
        '--setup', action='store_true',
        help='Install the AArch64 cross-compiler (runs apt install; requires sudo)',
    )
    mode.add_argument(
        '--link-strategy', action='store_true',
        help='Show the linking strategy decision table',
    )
    mode.add_argument(
        '--repair-hint', metavar='ERROR',
        help='Print repair hint(s) for the given compiler/linker error string',
    )
    mode.add_argument(
        '--list-archs', action='store_true',
        help='List supported architecture version strings',
    )
    mode.add_argument(
        '--list-feats', action='store_true',
        help='List supported FEAT_* → -march extension mappings',
    )

    # Compile options
    parser.add_argument(
        '--compile', metavar='SOURCE',
        help='C/C++ source file to compile for AArch64',
    )
    parser.add_argument(
        '--out', metavar='BINARY',
        help='Output binary path (default: <source>_aarch64)',
    )
    parser.add_argument(
        '--arch', metavar='VERSION',
        help='Target architecture version (e.g. v9Ap4)',
    )
    parser.add_argument(
        '--feat', nargs='+', metavar='FEAT_XXX',
        help='FEAT_* feature names to enable as -march extensions',
    )
    parser.add_argument(
        '--link', choices=['auto', 'static', 'dynamic', 'musl'], default='auto',
        help='Linking strategy (default: auto)',
    )
    parser.add_argument(
        '--cxx', action='store_true',
        help='Use the C++ compiler (aarch64-linux-gnu-g++)',
    )
    parser.add_argument(
        '--verbose', action='store_true',
        help='Print the compiler command before executing',
    )
    parser.add_argument(
        '--extra-flags', nargs='+', metavar='FLAG',
        help='Extra flags to pass to the compiler',
    )
    parser.add_argument(
        '--march-flag', action='store_true',
        help='Print the -march flag for --arch / --feat and exit (no compilation)',
    )

    args = parser.parse_args()

    # --check
    if args.check:
        cc = get_cc()
        if cc:
            print(f'AArch64 cross-compiler: {cc}')
            strategy = detect_link_strategy()
            print(f'Detected link strategy: {strategy}')
            return 0
        else:
            print(
                'AArch64 cross-compiler NOT found.\n'
                'Install with:\n'
                '    sudo apt install gcc-aarch64-linux-gnu',
                file=sys.stderr,
            )
            return 1

    # --setup
    if args.setup:
        print('Installing AArch64 cross-compilation toolchain…')
        cmd = ['sudo', 'apt', 'install', '-y',
               'gcc-aarch64-linux-gnu',
               'g++-aarch64-linux-gnu',
               'binutils-aarch64-linux-gnu',
               'libc6-dev-arm64-cross']
        try:
            proc = subprocess.run(cmd, timeout=300)
            if proc.returncode == 0:
                print('Installation complete.')
                return 0
            else:
                print('Installation failed.', file=sys.stderr)
                return 1
        except FileNotFoundError:
            print('apt not found — install manually:', file=sys.stderr)
            print('    sudo apt install gcc-aarch64-linux-gnu', file=sys.stderr)
            return 1
        except subprocess.TimeoutExpired:
            print('Installation timed out.', file=sys.stderr)
            return 1

    # --link-strategy
    if args.link_strategy:
        print(_LINK_STRATEGY_TABLE)
        detected = detect_link_strategy()
        print(f'Auto-detected strategy for this host: {detected}')
        return 0

    # --repair-hint
    if args.repair_hint:
        rules = find_repair_rules(args.repair_hint)
        if not rules:
            print('No matching repair rule found for this error.')
            print('Try running with --verbose to see the full compiler output,')
            print('then re-submit with the full error message.')
            return 0
        for rule in rules:
            print(f'[{rule["id"]}] {rule["cause"]}')
            print()
            print(textwrap.indent(rule['fix'], '    '))
            print()
        return 0

    # --list-archs
    if args.list_archs:
        print('Supported architecture versions (--arch):')
        for ver, march in _ARCH_MARCH.items():
            print(f'  {ver:<10}  -march={march}')
        return 0

    # --list-feats
    if args.list_feats:
        print('Supported FEAT_* → -march extension mappings (--feat):')
        for feat, ext in _FEAT_EXTENSION.items():
            print(f'  {feat:<25}  +{ext}')
        return 0

    # --march-flag (print the flag and exit)
    if args.march_flag:
        try:
            flag = arch_to_march_flag(args.arch or 'v8Ap0', args.feat)
            print(flag)
            return 0
        except ValueError as e:
            print(f'ERROR: {e}', file=sys.stderr)
            return 1

    # --compile
    if args.compile:
        if not Path(args.compile).exists():
            print(f'ERROR: Source file not found: {args.compile}', file=sys.stderr)
            return 1

        rc, out, err = cross_compile(
            args.compile,
            out=args.out,
            arch=args.arch,
            features=args.feat,
            link=args.link,
            extra_flags=args.extra_flags,
            cxx=args.cxx,
            verbose=args.verbose,
        )

        if out.strip():
            print(out)
        if err.strip():
            print(err, file=sys.stderr if rc != 0 else sys.stdout)

        if rc == 0:
            out_path = args.out or (
                Path(args.compile).stem + '_aarch64'
            )
            print(f'Binary: {out_path}')
            print('Next step: run with  python3 tools/gen_qemu_launch.py '
                  f'--run {out_path}')
        else:
            # Try to find repair hints for the error
            rules = find_repair_rules(err)
            if rules:
                print('\nRepair hints:', file=sys.stderr)
                for rule in rules[:2]:   # show at most 2 hints
                    print(f'  [{rule["id"]}] {rule["cause"]}', file=sys.stderr)
                    print(
                        textwrap.indent(rule['fix'], '    '),
                        file=sys.stderr,
                    )
            return rc

        return 0

    # No sub-command given
    parser.print_help()
    return 1


if __name__ == '__main__':
    sys.exit(main())
