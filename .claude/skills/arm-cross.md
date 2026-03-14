# arm-cross — AArch64 Cross-Compilation & Static Linking Skill

Use this skill when the user needs to compile C/C++ code for AArch64, set up the
cross-compilation toolchain, choose a linking strategy, or diagnose compilation errors:

- "Compile hello.c for AArch64"
- "Build my C file statically for QEMU testing"
- "How do I enable SVE2 in my cross-compiled binary?"
- "I get ld-linux-aarch64.so.1 not found — how do I fix it?"
- "Set up the AArch64 cross-compiler on my machine"
- "What -march flag should I use for ARMv9.4-A with SVE2?"
- "I get 'illegal instruction' in QEMU — is it a compiler flag issue?"

## Do NOT use this skill when:
- The user asks about register field layouts → use `arm-reg`
- The user wants to run a compiled binary → use `arm-qemu`
- The user wants to debug a binary with GDB → use `arm-gdb`
- The user needs instruction availability for an arch version → use `arm-allowlist`

---

## Path resolution

```bash
REPO=$(git rev-parse --show-toplevel)
SCRIPT="$REPO/tools/setup_cross_compile.py"
```

---

## Prerequisites

Install the cross-compiler toolchain:

```bash
sudo apt install gcc-aarch64-linux-gnu g++-aarch64-linux-gnu binutils-aarch64-linux-gnu
# Or use the automated setup command:
python "$SCRIPT" --setup
```

Check installation:

```bash
python "$SCRIPT" --check
```

---

## Commands

### Check toolchain availability

```bash
python "$SCRIPT" --check
```

Returns: path to the compiler and auto-detected link strategy.

### Install the cross-compiler

```bash
python "$SCRIPT" --setup
```

Runs `sudo apt install gcc-aarch64-linux-gnu`.

### Compile a C source file (auto link strategy)

```bash
python "$SCRIPT" --compile hello.c
python "$SCRIPT" --compile hello.c --out hello_aarch64
```

Produces an AArch64 binary using the auto-detected link strategy (usually `static`).

### Compile with a specific architecture version

```bash
# ARMv8.0-A baseline (safe for Cortex-A53/A57)
python "$SCRIPT" --compile hello.c --arch v8Ap0

# ARMv9.4-A
python "$SCRIPT" --compile hello.c --arch v9Ap4
```

### Compile with specific feature extensions

```bash
python "$SCRIPT" --compile hello.c --arch v9Ap0 --feat FEAT_SVE2
python "$SCRIPT" --compile hello.c --arch v9Ap4 --feat FEAT_SVE2 FEAT_SME
```

### Choose a link strategy

```bash
# Static (recommended for QEMU testing — no sysroot needed)
python "$SCRIPT" --compile hello.c --link static

# Dynamic (requires AArch64 multiarch sysroot)
python "$SCRIPT" --compile hello.c --link dynamic

# Musl libc (minimal static binary)
python "$SCRIPT" --compile hello.c --link musl
```

### Get the -march flag for an arch/feature combination

```bash
python "$SCRIPT" --march-flag --arch v9Ap4 --feat FEAT_SVE2
# Outputs: -march=armv9.4-a+sve2
```

### Show the linking strategy decision table

```bash
python "$SCRIPT" --link-strategy
```

### Get a repair hint for a build error

```bash
python "$SCRIPT" --repair-hint "ld-linux-aarch64.so.1: No such file or directory"
python "$SCRIPT" --repair-hint "illegal instruction"
python "$SCRIPT" --repair-hint "requires target feature 'sve'"
```

### List supported architecture versions

```bash
python "$SCRIPT" --list-archs
```

### List supported FEAT_* extensions

```bash
python "$SCRIPT" --list-feats
```

---

## Architecture → -march mapping

| `--arch` | GCC -march flag | Colloquial |
|----------|----------------|------------|
| `v8Ap0`  | `armv8-a`       | ARMv8.0-A (Cortex-A53/A57) |
| `v8Ap2`  | `armv8.2-a`     | ARMv8.2-A (Cortex-A55/A76) |
| `v8Ap4`  | `armv8.4-a`     | ARMv8.4-A (Neoverse-N1) |
| `v9Ap0`  | `armv9-a`       | ARMv9.0-A (Cortex-A710) |
| `v9Ap4`  | `armv9.4-a`     | ARMv9.4-A |
| `v9Ap6`  | `armv9.6-a`     | ARMv9.6-A (latest) |

Run `python "$SCRIPT" --list-archs` for the complete table.

---

## FEAT_* → -march extension mapping (common)

| FEAT_* flag | -march suffix | Description |
|-------------|--------------|-------------|
| `FEAT_SVE`     | `+sve`       | Scalable Vector Extension |
| `FEAT_SVE2`    | `+sve2`      | SVE version 2 |
| `FEAT_SME`     | `+sme`       | Scalable Matrix Extension |
| `FEAT_FP16`    | `+fp16`      | Half-precision floating-point |
| `FEAT_LSE`     | `+lse`       | Large System Extensions (atomics) |
| `FEAT_DOTPROD` | `+dotprod`   | Dot product |
| `FEAT_MTE`     | `+memtag`    | Memory Tagging Extension |
| `FEAT_BTI`     | `+bti`       | Branch Target Identification |
| `FEAT_PAUTH`   | `+pauth`     | Pointer Authentication |
| `FEAT_BF16`    | `+bf16`      | BFloat16 |
| `FEAT_I8MM`    | `+i8mm`      | Int8 matrix multiply |

Run `python "$SCRIPT" --list-feats` for the complete table.

---

## Linking strategy decision tree

| Target | Use | Flags |
|--------|-----|-------|
| QEMU bare-metal test | `static` | `-static` |
| Minimal binary | `musl` | `-static` (musl libc) |
| Full Linux userland | `dynamic` | Multiarch sysroot |

Auto-detection logic:
1. AArch64 `libc.so.6` found in standard multiarch path → `dynamic`
2. `musl-gcc` available → `musl`
3. Otherwise → `static` (safest fallback)

---

## Compile-error repair rules (20 rules)

The tool has 20 built-in repair rules for common AArch64 cross-compilation errors.
Use `--repair-hint "<error message>"` to look them up interactively.

| Rule | Error pattern | Root cause |
|------|--------------|------------|
| R01 | `ld-linux-aarch64.so.1 not found` | Missing AArch64 dynamic linker |
| R02 | `cannot find -lXXX` | Missing AArch64 shared library |
| R03 | `cannot find -lc` | AArch64 static libc not installed |
| R04 | `illegal instruction` | ISA instruction not supported by target CPU |
| R05 | `-march not recognized` | GCC version does not support the extension |
| R06 | `unknown target triple aarch64` | Using host compiler instead of cross-compiler |
| R07 | `undefined reference to` | Missing library or wrong architecture |
| R08 | `implicit declaration of function` | Missing #include |
| R09 | `undeclared` | Missing #define or wrong header |
| R10 | `relocation truncated` | Branch range exceeded in large static binary |
| R11 | `R_AARCH64_* not supported` | Binutils version mismatch |
| R12 | `incompatible with ABI` | Mixed ABI objects (soft vs hard float) |
| R13 | `stack not 16-byte aligned` | SP misalignment before call (AArch64 ABI) |
| R14 | `address not aligned` | SIMD / LDP/STP alignment violation |
| R15 | `requires target feature 'sve'` | SVE intrinsic without `+sve` in -march |
| R16 | `requires target feature 'sme'` | SME intrinsic without `+sme` in -march |
| R17 | `NEON not available` | NEON intrinsic argument out of range |
| R18 | `pauth not enabled` | PAC instruction without `+pauth` |
| R19 | `BTI not enabled` | Missing BTI landing pad |
| R20 | `ld returned 1 exit status` | Generic linker failure (see preceding lines) |

---

## Programmatic API (for H8 orchestration)

```python
import sys
REPO = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'],
                                text=True).strip()
sys.path.insert(0, f'{REPO}/tools')

from setup_cross_compile import cross_compile, find_repair_rules, arch_to_march_flag

# Get the -march flag
flag = arch_to_march_flag('v9Ap4', ['FEAT_SVE2'])
# → '-march=armv9.4-a+sve2'

# Compile
rc, stdout, stderr = cross_compile(
    'hello.c', out='hello_aarch64',
    arch='v9Ap4', features=['FEAT_SVE2'], link='static'
)

# Auto-repair
if rc != 0:
    rules = find_repair_rules(stderr)
    for rule in rules:
        print(f'[{rule["id"]}] {rule["cause"]}')
        print(rule['fix'])
```

---

## Important constraints

- **Static linking is the safest default for QEMU testing** — avoids sysroot issues.
- **Match --arch to the QEMU --cpu** — if you compile with `--arch v9Ap0` but run on
  `qemu-aarch64 -cpu cortex-a57` (Armv8.0-A), you'll get SIGILL for v9 instructions.
  Use `arm-allowlist` to verify instruction compatibility first.
- **Feature availability check before use** — always run `arm-allowlist --arch <VERSION>`
  or `arm-feat FEAT_XXX` before enabling an extension in `--feat`.
- **gcc-aarch64-linux-gnu version matters** — older GCC versions may not support
  `-march=armv9-a+sme`. Install the latest with `sudo apt install gcc-aarch64-linux-gnu`.

---

## Example interactions

**User:** "Cross-compile hello.c for AArch64 and run it in QEMU"
```bash
python "$SCRIPT" --compile hello.c --out hello_aarch64 --link static
python "$REPO/tools/gen_qemu_launch.py" --run ./hello_aarch64
```

**User:** "Enable SVE2 for my cortex-a710 target"
```bash
# Check SVE2 is available at Armv9.0-A
python "$REPO/tools/query_feature.py" FEAT_SVE2
# Compile with SVE2
python "$SCRIPT" --compile kernel.c --arch v9Ap0 --feat FEAT_SVE2 --link static
```

**User:** "I get ld-linux-aarch64.so.1: No such file or directory"
```bash
python "$SCRIPT" --repair-hint "ld-linux-aarch64.so.1: No such file"
```
Return rule R01 with the fix: switch to `--link static` or install `libc6:arm64`.
