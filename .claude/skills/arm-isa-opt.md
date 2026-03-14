# arm-isa-opt — AArch64 Advanced ISA Optimization (SVE2/SME/PAC/BTI/MTE)

Use this skill when the user asks about generating optimized or security-hardened
AArch64 code using modern ISA extensions:

- "Generate SVE2 code for a dot-product loop"
- "Create an SME matrix-multiply kernel"
- "Harden this assembly with PAC and BTI"
- "Add MTE memory tagging to my allocator"
- "What security rules apply to PAC/BTI/MTE code?"
- "Is SVE2 available on ARMv9.2-A?"
- "List available code-generation templates"

## Do NOT use this skill when:
- The user asks about register field layouts → use `arm-reg`
- The user wants an instruction allowlist → use `arm-allowlist`
- The user wants to compile code → use `arm-cross`
- The user wants to run code in QEMU → use `arm-qemu`
- The user wants to debug with GDB → use `arm-gdb`
- The user asks about feature dependencies → use `arm-feat`

---

## Path resolution

```bash
REPO=$(git rev-parse --show-toplevel)
SCRIPT="$REPO/tools/isa_optimize.py"
```

---

## Commands

### List available code-generation templates

```bash
python "$SCRIPT" --list-templates
python "$SCRIPT" --list-templates --category sve2
python "$SCRIPT" --list-templates --category sme
python "$SCRIPT" --list-templates --output json
```

Returns: template names, descriptions, required features, and minimum arch.

### Generate a code template

```bash
python "$SCRIPT" --template sve2-dotproduct --arch v9Ap4
python "$SCRIPT" --template sme-matmul --arch v9Ap2
python "$SCRIPT" --template sve2-gather --arch v9Ap4 --output json
```

Returns: C code with SVE2/SME intrinsics, pre-filled `-march` flags.
Error if the required features are not available at the target arch.

### Auto-insert PAC/BTI security instructions

```bash
python "$SCRIPT" --auto-pac-bti --arch v9Ap0 --input func.s
echo "my_func:\n\tret" | python "$SCRIPT" --auto-pac-bti --arch v9Ap0
python "$SCRIPT" --auto-pac-bti --arch v9Ap0 --input func.s --output json
```

Returns: hardened assembly with PACIASP/AUTIASP (PAC) and BTI c (BTI)
inserted at function entry/return points. Only inserts instructions that
are available at the target architecture.

### Generate MTE helper header

```bash
python "$SCRIPT" --mte-helpers --arch v8Ap5
python "$SCRIPT" --mte-helpers --arch v9Ap0 --output json
```

Returns: C header with MTE intrinsic wrappers (IRG, STG, LDG, ADDG,
region tagging, pool allocation). Error if MTE not available at target.

### List security best-practice rules

```bash
python "$SCRIPT" --list-rules
python "$SCRIPT" --list-rules --category pac
python "$SCRIPT" --list-rules --category bti
python "$SCRIPT" --list-rules --category mte
python "$SCRIPT" --list-rules --category general
python "$SCRIPT" --list-rules --output json
```

Returns: 18 security rules (R01–R18) for PAC, BTI, MTE, and combined usage.
Rules include ID, title, description, instruction, min_arch, and required features.
Exported as JSON for H7 linter integration.

### Check feature availability at target arch

```bash
python "$SCRIPT" --check-features --arch v9Ap4 SVE2 SME MTE PAC BTI
python "$SCRIPT" --check-features --arch v8Ap0 SVE2 SME
python "$SCRIPT" --check-features --arch v9Ap4 SVE2 --output json
```

Returns: per-extension availability status. Exit 0 if all available, 1 if any unavailable.

---

## Available templates

### SVE2 templates (8)

| Template | Description | Min arch |
|----------|-------------|----------|
| `sve2-dotproduct` | Integer dot-product accumulation loop | v9Ap0 |
| `sve2-matrix-multiply` | Integer matrix multiply (SMMLA) | v9Ap0 |
| `sve2-convolution` | 1-D convolution with predicated load/store | v9Ap0 |
| `sve2-reduce` | Horizontal reduction (sum) | v9Ap0 |
| `sve2-gather` | Gather-load from index array | v9Ap0 |
| `sve2-scatter` | Scatter-store to index array | v9Ap0 |
| `sve2-scan` | Prefix-sum (inclusive scan) | v9Ap0 |
| `sve2-permute` | Table-lookup permutation (TBL) | v9Ap0 |

### SME templates (4)

| Template | Description | Min arch |
|----------|-------------|----------|
| `sme-matmul` | Outer-product matrix multiply (FP32 tiles) | v9Ap2 |
| `sme-accumulate` | Streaming-mode accumulation | v9Ap2 |
| `sme-transpose` | ZA tile transpose | v9Ap2 |
| `sme-int8-matmul` | Int8 → int32 matrix multiply | v9Ap2 |

---

## Security rules (18 rules)

| Category | Rules | Min arch | Required feature |
|----------|-------|----------|-----------------|
| PAC | R01–R05 | v8Ap3 | FEAT_PAuth |
| BTI | R06–R10 | v8Ap5 | FEAT_BTI |
| MTE | R11–R15 | v8Ap5 | FEAT_MTE |
| General | R16–R18 | v8Ap5+ | Various |

Use `--list-rules --output json` to export rules for H7 linter integration.

---

## Extension availability by architecture

| Extension | Required feature | Min arch | Compile flag |
|-----------|-----------------|----------|-------------|
| SVE2 | FEAT_SVE2 | v9Ap0 | `-march=armv9-a+sve2` |
| SME | FEAT_SME | v9Ap2 | `-march=armv9.2-a+sme` |
| PAC | FEAT_PAuth | v8Ap3 | `-march=armv8.3-a+pauth` |
| BTI | FEAT_BTI | v8Ap5 | `-march=armv8.5-a+bti` |
| MTE | FEAT_MTE | v8Ap5 | `-march=armv8.5-a+memtag` |

---

## Programmatic API (for H7/H8 integration)

```python
import sys
REPO = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'],
                                text=True).strip()
sys.path.insert(0, f'{REPO}/tools')

from isa_optimize import (
    list_templates,
    generate_template,
    insert_pac_bti,
    generate_mte_helpers,
    list_security_rules,
    check_features,
    check_extension_available,
    ALL_TEMPLATES,
    SECURITY_RULES,
)

# List templates
templates = list_templates(category='sve2')

# Generate code
result = generate_template('sve2-dotproduct', arch='v9Ap4')
print(result['code'])

# Harden assembly
result = insert_pac_bti(asm_text, arch='v9Ap0')
print(result['output'])

# MTE helpers
result = generate_mte_helpers(arch='v8Ap5')
print(result['helpers'])

# Security rules
rules = list_security_rules(category='pac')

# Feature check
ok, detail = check_extension_available('v9Ap4', 'SVE2')
```

---

## Important constraints

- **Feature gating is enforced via H1.** Every code-generation path checks feature
  availability through the H1 allowlist API. Generated code will only use
  instructions that are available at the target architecture version.
- **No prose descriptions are synthesized.** Template comments and rule descriptions
  are based on the ARM Architecture Reference Manual and ISA specification.
- **Generated code uses ARM C Language Extensions (ACLE).** SVE2 templates use
  `<arm_sve.h>` intrinsics; SME templates use `<arm_sme.h>`; MTE uses `<arm_acle.h>`.
- **PAC/BTI insertion is conservative.** The auto-inserter adds PACIASP/AUTIASP
  and BTI c only where features are available. It does not remove existing
  hardening instructions.
- **MTE requires 16-byte alignment.** All MTE helpers assume 16-byte (granule)
  aligned addresses. The `mte_tag_region` helper iterates in 16-byte steps.

---

## Example interactions

**User:** "Generate an SVE2 dot-product loop for ARMv9.4-A"
```bash
python "$SCRIPT" --template sve2-dotproduct --arch v9Ap4
```
Return the generated C code with intrinsics and compile flags.

**User:** "Harden my assembly function with PAC and BTI"
```bash
python "$SCRIPT" --auto-pac-bti --arch v9Ap0 --input my_func.s
```
Return the hardened assembly with PACIASP/AUTIASP and BTI c inserted.

**User:** "What security rules should I follow for MTE?"
```bash
python "$SCRIPT" --list-rules --category mte
```
Return MTE-specific rules R11–R15.

**User:** "Is SME available on ARMv8.4-A?"
```bash
python "$SCRIPT" --check-features --arch v8Ap4 SME
```
Returns: SME NOT available (requires v9Ap2+).

**User:** "Generate MTE helper code for my memory allocator"
```bash
python "$SCRIPT" --mte-helpers --arch v8Ap5
```
Return the C header with MTE intrinsic wrappers.
