# arm-gdb — AArch64 GDB-MCP Debugging Skill

Use this skill when the user wants to step through AArch64 assembly or C code in GDB,
inspect register values, assert register state, or diagnose a SIGILL fault:

- "Step through my AArch64 binary and show X0 after the first 3 instructions"
- "Assert that X0 == 0 and X1 == 0x42 after the function call"
- "I got a SIGILL — how do I diagnose it?"
- "Run my assertion suite on this binary"
- "Show the backtrace for my AArch64 crash"
- "Set a breakpoint at main and inspect the registers"

## Do NOT use this skill when:
- The user asks about register field layouts or bit positions → use `arm-reg`
- The user asks which instructions are valid for an architecture version → use `arm-allowlist`
- The user needs to compile an AArch64 binary → use `arm-cross`
- The user needs to run a binary and observe the exit code → use `arm-qemu`

---

## Path resolution

```bash
REPO=$(git rev-parse --show-toplevel)
SCRIPT="$REPO/tools/query_gdb.py"
```

---

## Prerequisites

Install `gdb-multiarch`:

```bash
sudo apt install gdb-multiarch
```

Check installation:

```bash
python "$SCRIPT" --check
```

---

## Commands

### Check GDB availability

```bash
python "$SCRIPT" --check
```

Returns: path to the GDB binary, or an error if not installed.

### Print GDB version

```bash
python "$SCRIPT" --version
```

### Run binary to main and inspect registers

```bash
python "$SCRIPT" ./my_aarch64_binary --registers
```

### Set breakpoint, step N lines, then show registers

```bash
python "$SCRIPT" ./my_aarch64_binary --break main --step 3 --registers
```

### Assert register values

```bash
python "$SCRIPT" ./my_aarch64_binary --break main --step 1 --assert "x0=0 x1=0x42"
```

Returns: PASS if all assertions hold; lists failures and exits non-zero otherwise.

Value formats: decimal (`42`) or hex (`0x2a`) — both are accepted.

### Step machine instructions (nexti)

```bash
python "$SCRIPT" ./my_aarch64_binary --break main --nexti 5 --registers
```

### Show backtrace

```bash
python "$SCRIPT" ./my_aarch64_binary --break main --backtrace
```

### Run a JSON assertion suite

```bash
python "$SCRIPT" ./my_aarch64_binary --suite suite.json
```

---

## Suite JSON format

```json
[
  {"action": "breakpoint", "location": "main"},
  {"action": "step", "count": 3,
   "assert": {"x0": 0, "x1": 66},
   "note": "after init"},
  {"action": "nexti", "count": 10,
   "note": "run 10 machine instructions"},
  {"action": "continue",
   "assert": {"x0": 1},
   "note": "after main returns"}
]
```

Valid `action` values: `"step"`, `"next"`, `"stepi"`, `"nexti"`, `"continue"`, `"breakpoint"`.

---

## SIGILL repair workflow

When GDB (or QEMU) reports a `SIGILL` (Illegal Instruction):

```bash
# 1. Get the repair hint
python "$SCRIPT" --sigill-hint v9Ap4 --pc 0x4004f0

# 2. Query the allowlist for the target architecture
REPO=$(git rev-parse --show-toplevel)
python "$REPO/tools/query_allowlist.py" --arch v9Ap4 --output json \
  | python3 -c "import json,sys; d=json.load(sys.stdin); \
    print('\n'.join(d['prohibited_operations'][:20]))"

# 3. Find a valid replacement instruction
python "$REPO/tools/query_allowlist.py" --arch v9Ap4 --summary
```

Exit code `2` from `query_gdb.py` indicates a SIGILL was detected.

---

## Programmatic API (for H8 orchestration)

```python
import sys
REPO = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'],
                                text=True).strip()
sys.path.insert(0, f'{REPO}/tools')

from gdb_session import GdbSession, SigilDetectedError, AssertionFailedError

with GdbSession('./my_binary') as gdb:
    gdb.set_breakpoint('main')
    gdb.run()
    gdb.step(3)
    regs = gdb.get_registers()          # dict: x0..x30, sp, pc, pstate
    gdb.assert_register('x0', 0)        # raises AssertionFailedError if wrong
    frames = gdb.get_backtrace()

# High-level batch API
from gdb_session import run_assertion_suite_on_binary
result = run_assertion_suite_on_binary('./my_binary', suite_steps, arch='v9Ap4')
# result['passed'], result['failed'], result['failures']
```

---

## Register name reference

| Register | Role |
|----------|------|
| x0–x7    | Function argument / result registers |
| x8       | Indirect result location / syscall number |
| x9–x15   | Caller-saved temporary registers |
| x16–x17  | Intra-procedure-call scratch registers (IP0/IP1) |
| x18      | Platform register (reserved by OS on Linux) |
| x19–x28  | Callee-saved registers |
| x29      | Frame pointer (FP) |
| x30      | Link register (LR) — holds return address |
| sp       | Stack pointer (must be 16-byte aligned at calls) |
| pc       | Program counter |
| pstate   | Processor state (NZCV + DAIF + EL + SP flags) |

---

## Important constraints

- **gdb-multiarch is required** — the host's plain `gdb` may not support AArch64.
  Install with `sudo apt install gdb-multiarch`.
- **Binary must be an AArch64 ELF** — cross-compiled with `arm-cross` (H5) or
  a system AArch64 binary.
- **Stripped binaries**: GDB can still inspect registers and memory but not source lines.
  Use `--nexti` instead of `--step` for stripped code.
- **SIGILL exit code 2**: `query_gdb.py` exits with code 2 on SIGILL; use this to
  programmatically trigger the H1 allowlist repair loop.

---

## Example interactions

**User:** "Assert X0 == 0 after calling my_init()"
```bash
python "$SCRIPT" ./my_binary --break my_init --step 5 --assert "x0=0"
```

**User:** "My binary crashes with SIGILL — how do I diagnose it?"
```bash
# First, run it under QEMU to confirm SIGILL
python "$REPO/tools/gen_qemu_launch.py" --run ./my_binary
# Then, get the repair hint
python "$SCRIPT" --sigill-hint v9Ap4
# Check which instructions are prohibited at this arch version
python "$REPO/tools/query_allowlist.py" --arch v9Ap4 --output json
```

**User:** "Run the full assertion suite in suite.json"
```bash
python "$SCRIPT" ./my_binary --suite suite.json
```
Report passed/failed counts. If any assertion fails, show the register mismatch.
