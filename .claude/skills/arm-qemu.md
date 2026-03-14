# arm-qemu — AArch64 QEMU Emulation Automation Skill

Use this skill when the user wants to run an AArch64 binary in QEMU, generate a QEMU
launch script, or understand QEMU exit conditions:

- "Run my cross-compiled AArch64 binary in QEMU"
- "Generate a QEMU launch script for cortex-a57 with 4 GB RAM"
- "What CPU should I pass to QEMU for ARMv9.2-A testing?"
- "My binary crashed with SIGILL in QEMU — what do I do next?"
- "Generate a system-mode QEMU script with UEFI firmware"
- "Check whether qemu-aarch64 is installed"

## Do NOT use this skill when:
- The user asks about register field layouts → use `arm-reg`
- The user wants to step through code in a debugger → use `arm-gdb`
- The user needs to compile a binary → use `arm-cross`
- The user needs instruction encoding information → use `arm-instr`

---

## Path resolution

```bash
REPO=$(git rev-parse --show-toplevel)
SCRIPT="$REPO/tools/gen_qemu_launch.py"
```

---

## Prerequisites

```bash
# User-mode QEMU (run individual AArch64 binaries — simplest)
sudo apt install qemu-user-static

# System-mode QEMU (full VM — needed for kernel/EL1/EL2 testing)
sudo apt install qemu-system-arm
```

Check installation:

```bash
python "$SCRIPT" --check
```

---

## Commands

### Check QEMU availability

```bash
python "$SCRIPT" --check
```

Returns paths for both user-mode and system-mode QEMU.

### Run an AArch64 binary (user-mode)

```bash
python "$SCRIPT" --run ./my_aarch64_binary
python "$SCRIPT" --run ./my_aarch64_binary --cpu cortex-a710 --timeout 60
python "$SCRIPT" --run ./my_aarch64_binary --json
```

Returns: `PASS` / `FAIL` / `SIGILL` / `SIGSEGV` / `TIMEOUT` + exit code + output.

### List available CPU models

```bash
python "$SCRIPT" --list-cpus
```

### Generate a user-mode launch script

```bash
python "$SCRIPT" --mode user --cpu max --output run_aarch64.sh
```

Generated script accepts a binary as `$1` and forwards remaining arguments.

### Generate a system-mode launch script

```bash
python "$SCRIPT" --mode system --cpu cortex-a57 --memory 4G --output launch_vm.sh
python "$SCRIPT" --mode system --cpu max --memory 8G --accel kvm --output launch_vm.sh
```

### System-mode with Linux direct-kernel boot

```bash
python "$SCRIPT" --mode system --cpu max \
                 --kernel Image --drive rootfs.qcow2 \
                 --output launch_linux.sh
```

---

## Exit condition routing

| Classification | Meaning | Suggested action |
|---------------|---------|-----------------|
| `pass`        | Binary exited 0 | ✅ Test passed |
| `fail`        | Non-zero exit code | Debug with `arm-gdb` |
| `sigill`      | Illegal instruction (exit 132) | Query `arm-allowlist` for the arch; recompile with correct `-march` |
| `sigsegv`     | Segmentation fault (exit 139) | Debug with `arm-gdb` |
| `timeout`     | QEMU did not exit within timeout | Increase `--timeout` or check for infinite loops |

### SIGILL repair workflow

```bash
# 1. Run binary and detect SIGILL
python "$SCRIPT" --run ./my_binary --cpu cortex-a57

# 2. Determine which instructions are prohibited at the target arch
python "$REPO/tools/query_allowlist.py" --arch v8Ap0 --output json \
  | python3 -c "import json,sys; d=json.load(sys.stdin); \
    print('\n'.join(d['prohibited_operations'][:30]))"

# 3. Recompile with the correct -march flag
python "$REPO/tools/setup_cross_compile.py" --compile source.c \
    --arch v8Ap0 --link static

# 4. Re-run
python "$SCRIPT" --run ./source_aarch64 --cpu cortex-a57
```

---

## CPU model reference

| QEMU CPU | Architecture | Typical use |
|----------|-------------|-------------|
| `max`    | Latest features | Testing new code |
| `cortex-a35` | Armv8.0-A | IoT / low-power |
| `cortex-a53` | Armv8.0-A | Low-power mobile |
| `cortex-a55` | Armv8.2-A | Mobile + DotProd |
| `cortex-a57` | Armv8.0-A | Server / desktop legacy |
| `cortex-a72` | Armv8.0-A | Mid-range server |
| `cortex-a76` | Armv8.2-A | High-perf mobile |
| `cortex-a710` | Armv9.0-A + SVE2 | Latest big core |
| `neoverse-n1` | Armv8.4-A | Cloud / HPC |

Run `python "$SCRIPT" --list-cpus` for the full list with descriptions.

---

## Programmatic API (for H8 orchestration)

```python
import sys
REPO = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'],
                                text=True).strip()
sys.path.insert(0, f'{REPO}/tools')

from gen_qemu_launch import run_binary, QemuResult, gen_user_mode_script

# Run a binary
result: QemuResult = run_binary('./my_binary', cpu='cortex-a57', timeout=30.0)
print(result.classification)   # 'pass', 'fail', 'sigill', 'sigsegv', 'timeout'
print(result.exit_code)
print(result.stdout)

# Generate a launch script programmatically
script = gen_user_mode_script(cpu='cortex-a710')
Path('run.sh').write_text(script)
```

---

## Standard system-mode QEMU configuration

```bash
qemu-system-aarch64 \
    -machine virt,iommu=smmuv3 \
    -cpu cortex-a57 \
    -accel tcg \
    -m 4G \
    -pflash edk2-aarch64-code.fd \
    -pflash edk2-arm-vars.fd \
    -nic user \
    -nographic
```

For accelerated emulation on a native AArch64 host:
- Linux: use `-accel kvm`
- macOS: use `-accel hvf`

---

## Important constraints

- **User-mode QEMU is preferred for binary testing** — faster than system mode,
  no firmware required, intercepts Linux syscalls transparently.
- **System-mode requires firmware** — download the EDK2 images for UEFI boot:
  `apt install qemu-efi-aarch64`  (Ubuntu; installs to `/usr/share/AAVMF/`).
- **SIGILL exit code 132** — `gen_qemu_launch.py` exits 132 when SIGILL is detected
  in user mode; route this back to the `arm-allowlist` repair loop.
- **Timeout exit code 124** — mirrors the `timeout(1)` command convention.

---

## Example interactions

**User:** "Run my binary and tell me if it passes"
```bash
python "$SCRIPT" --run ./my_binary
```
Report the classification and exit code.

**User:** "Generate a QEMU launch script for Cortex-A710 testing"
```bash
python "$SCRIPT" --mode user --cpu cortex-a710 --output run_a710.sh
cat run_a710.sh
```

**User:** "My binary gets SIGILL on Cortex-A57 but works on max — why?"
Run the allowlist for v8Ap0 (Cortex-A57 baseline) and compare prohibited operations:
```bash
python "$REPO/tools/query_allowlist.py" --arch v8Ap0 --summary
python "$REPO/tools/query_allowlist.py" --arch v9Ap0 --summary
```
Then recompile with the correct `-march` flag targeting Cortex-A57.
