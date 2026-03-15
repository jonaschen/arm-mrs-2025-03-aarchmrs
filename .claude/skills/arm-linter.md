# arm-linter — AArch64 Assembly Linter-in-the-Loop (VIXL)

Use this skill when the user asks about linting, validating, or checking
AArch64 assembly code for correctness:

- "Lint this AArch64 assembly for errors"
- "Check my assembly for common mistakes"
- "Are there any alignment issues in this code?"
- "Is this STXR usage correct?"
- "Run a lint-green check on my assembly"
- "What lint rules apply to PAC/BTI code?"
- "How do I fix this register overlap in STXR?"
- "Check if VIXL linter is available"

## Do NOT use this skill when:
- The user asks about register field layouts → use `arm-reg`
- The user wants to generate optimized code → use `arm-isa-opt`
- The user wants to compile code → use `arm-cross`
- The user wants to run code in QEMU → use `arm-qemu`
- The user wants to debug with GDB → use `arm-gdb`
- The user wants an instruction allowlist → use `arm-allowlist`

---

## Path resolution

```bash
REPO=$(git rev-parse --show-toplevel)
SCRIPT="$REPO/tools/isa_linter.py"
```

---

## Commands

### Lint an assembly file

```bash
python3 "$SCRIPT" --lint test.s
python3 "$SCRIPT" --lint test.s --arch v9Ap0
python3 "$SCRIPT" --lint test.s --category alignment
python3 "$SCRIPT" --lint test.s --arch v9Ap4 --output json
```

Returns: List of violations with line numbers, rule IDs, severity, and
repair suggestions. When `--arch` is given, only rules applicable to that
architecture version are checked.

### Lint assembly from stdin

```bash
echo "sub sp, sp, #17" | python3 "$SCRIPT" --lint-stdin --arch v8Ap0
python3 "$SCRIPT" --lint-stdin --arch v9Ap0 < func.s
```

Returns: Same output as `--lint`, reading from standard input.

### List all lint rules

```bash
python3 "$SCRIPT" --list-rules
python3 "$SCRIPT" --list-rules --category security
python3 "$SCRIPT" --list-rules --category alignment
python3 "$SCRIPT" --list-rules --category register
python3 "$SCRIPT" --list-rules --category branch
python3 "$SCRIPT" --list-rules --category encoding
python3 "$SCRIPT" --list-rules --output json
```

Returns: All 50 lint rules with ID, category, severity, title, description,
min architecture, and source reference.

### Check VIXL linter availability

```bash
python3 "$SCRIPT" --check-vixl
python3 "$SCRIPT" --check-vixl --output json
```

Returns: Whether VIXL linter (or aarch64-linux-gnu-objdump) is available
on PATH. Falls back to built-in rule engine if not available.

### Lint-green gate

```bash
python3 "$SCRIPT" --lint-green test.s
python3 "$SCRIPT" --lint-green test.s --arch v9Ap0
python3 "$SCRIPT" --lint-green test.s --arch v9Ap4 --output json
```

Returns: PASS (exit 0) if zero errors and zero warnings. FAIL (exit 1)
if any errors or warnings are found. This is the blocking merge gate
from the H7 verification flow.

---

## Lint rule categories (50 rules)

| Category | Rules | Count | Description |
|----------|-------|-------|-------------|
| security | L01–L18 | 18 | PAC/BTI/MTE security (from H6 R01–R18) |
| alignment | L19–L26 | 8 | Memory alignment, SP alignment, atomics |
| register | L27–L36 | 10 | Register constraints, writeback, overlaps |
| branch | L37–L44 | 8 | Branch targets, dead code, control flow |
| encoding | L45–L50 | 6 | Immediate ranges, shift amounts, encoding |

### Security rules (L01–L18, from H6)

| Rule | Severity | Title | Min arch |
|------|----------|-------|----------|
| L01 | warning | Sign return address in prologue (PACIASP) | v8Ap3 |
| L02 | warning | Authenticate return address before RET (AUTIASP) | v8Ap3 |
| L03 | warning | PAC key diversity | v8Ap3 |
| L04 | warning | No unauthenticated pointer dereference | v8Ap3 |
| L05 | warning | Use RETAA/RETAB where available | v8Ap3 |
| L06 | warning | BTI landing pad at indirect branch targets | v8Ap5 |
| L07 | warning | BTI j at indirect jump targets | v8Ap5 |
| L08 | warning | Enable GP bit in page tables | v8Ap5 |
| L09 | warning | Combine PAC + BTI at function entry | v8Ap5 |
| L10 | warning | No computed branch into mid-function | v8Ap5 |
| L11 | warning | Tag every heap allocation (IRG + STG) | v8Ap5 |
| L12 | warning | Align allocations to 16-byte MTE granule | v8Ap5 |
| L13 | warning | Clear tags on free | v8Ap5 |
| L14 | warning | Enable SCTLR_EL1.TCF tag checking | v8Ap5 |
| L15 | warning | Use ADDG for sub-object tagging | v8Ap5 |
| L16 | warning | Stack tagging with MTE | v8Ap5 |
| L17 | warning | Combine PAC + BTI + MTE defense in depth | v8Ap5 |
| L18 | warning | Prefer FEAT_PAuth2 enhanced PAC | v8Ap6 |

### Alignment rules (L19–L26)

| Rule | Severity | Title |
|------|----------|-------|
| L19 | warning | LDP/STP non-SP base must be 16-byte aligned |
| L20 | error | SP modification must maintain 16-byte alignment |
| L21 | warning | Atomic instructions require natural alignment |
| L22 | error | STXR status register must differ from data/address |
| L23 | error | SVE load/store must use governing predicate |
| L24 | warning | Stack push should save even number of registers |
| L25 | error | SIMD LDn/STn must specify element arrangement |
| L26 | info | Literal pool LDR must be within ±1 MB |

### Register constraint rules (L27–L36)

| Rule | Severity | Title |
|------|----------|-------|
| L27 | error | XZR/WZR must not be writeback base register |
| L28 | warning | SP must not be Rm in data-processing |
| L29 | error | LDP/STP writeback base must not overlap pair |
| L30 | error | Exclusive monitor register must differ |
| L31 | warning | LR (X30) must be saved before BL |
| L32 | warning | X18 (platform register) must not be scratch |
| L33 | warning | X29 (FP) must be saved when modified |
| L34 | info | Conditional branch with stale NZCV flags |
| L35 | error | LDPSW destination registers must not overlap |
| L36 | warning | MOVK requires preceding MOVZ/MOV |

### Branch and control flow rules (L37–L44)

| Rule | Severity | Title |
|------|----------|-------|
| L37 | warning | Dead code after unconditional branch |
| L38 | error | TBZ/TBNZ bit position out of range |
| L39 | warning | CBZ/CBNZ register width check |
| L40 | error | SVC/HVC/SMC immediate out of range |
| L41 | info | ISB should follow system register write |
| L42 | info | RET with non-X30 target |
| L43 | error | BLR must not target SP or XZR |
| L44 | warning | Fall-through from .text into .data |

### Encoding constraint rules (L45–L50)

| Rule | Severity | Title |
|------|----------|-------|
| L45 | error | ADD/SUB immediate out of 12-bit range |
| L46 | info | Logical immediate must be valid bitmask |
| L47 | error | Shift amount out of register width range |
| L48 | error | MOV/MOVZ/MOVN immediate out of 16-bit range |
| L49 | info | UBFM/SBFM/BFM immr/imms must be valid |
| L50 | info | MSR/MRS system register must be recognized |

---

## Verification gate flow (H7-4)

```
Code generation
    │
    ▼
[Lint] ─── FAIL ───▶ Error parse ──▶ Rule-based Repair ──┐
    │                                                      │
  PASS                                                     │
    │◀─────────────────────────────────────────────────────┘
    ▼
[Functional test in H4 QEMU] ─── FAIL ───▶ H3 GDB debug ──▶ Regenerate
    │
  PASS
    ▼
  Merge
```

Use `--lint-green` as the blocking gate. Exit code 0 means pass.

---

## Programmatic API (for H8 integration)

```python
import sys
REPO = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'],
                                text=True).strip()
sys.path.insert(0, f'{REPO}/tools')

from isa_linter import (
    LINT_RULES,
    LINT_CATEGORIES,
    SCHEMA_VERSION,
    lint_assembly,
    suggest_repairs,
    lint_green,
    check_vixl,
    list_lint_rules,
)

# List all rules
rules = list_lint_rules()                    # 50 rules
sec = list_lint_rules(category='security')   # 18 security rules

# Lint assembly text
violations = lint_assembly(asm_text, arch='v9Ap0')
for v in violations:
    print(f"  line {v['line']}: [{v['severity'].upper()}] {v['rule_id']}: {v['message']}")

# Auto-repair suggestions
repairs = suggest_repairs(violations)
for r in repairs:
    print(f"  {r['suggested']}")

# Lint-green gate
result = lint_green(asm_text, arch='v9Ap0')
if result['green']:
    print('PASS')
else:
    print(f"FAIL: {result['errors']} errors, {result['warnings']} warnings")

# Check VIXL availability
vixl = check_vixl()
print(f"VIXL: {'available' if vixl['available'] else 'not available'}")
```

---

## Important constraints

- **No cache dependency.** The linter operates purely on assembly text and
  built-in rules. It does not require any MRS cache to be built.
- **Feature-gated rules.** When `--arch` is specified, only rules whose
  `min_arch` is at or below the target version are applied. Security rules
  (L01–L18) are gated by PAC/BTI/MTE architecture requirements.
- **Severity levels.** `error` = definitely wrong (e.g. register overlap),
  `warning` = likely wrong (e.g. missing PAC), `info` = style recommendation.
- **Lint-green gate is strict.** It fails on BOTH errors and warnings. This
  ensures security best practices (warnings) are enforced before merge.
- **VIXL fallback.** If VIXL is not installed, the built-in rule engine is
  used. The built-in engine covers the same rule set.
- **H6 security rules are re-imported.** L01–L18 map directly to R01–R18
  from H6's `SECURITY_RULES`. Changes to H6 rules automatically propagate.

---

## Example interactions

**User:** "Lint my assembly file for AArch64 errors"
```bash
python3 "$SCRIPT" --lint my_code.s --arch v9Ap0
```
Return all violations with line numbers and repair suggestions.

**User:** "Check if this STXR usage is correct"
```bash
echo "stxr w0, x0, [x1]" | python3 "$SCRIPT" --lint-stdin --arch v8Ap0
```
Returns: L22/L30 error — status register W0 overlaps with data register X0.

**User:** "Run lint-green check before merging"
```bash
python3 "$SCRIPT" --lint-green my_code.s --arch v9Ap4
```
Returns: PASS ✓ or FAIL ✗ with summary of errors/warnings.

**User:** "What alignment rules should I follow?"
```bash
python3 "$SCRIPT" --list-rules --category alignment
```
Returns: 8 alignment rules (L19–L26).

**User:** "Fix the SP alignment error"
```bash
python3 "$SCRIPT" --lint my_code.s --output json | python3 -c "..."
```
Returns: JSON with violations and auto-repair suggestions.
