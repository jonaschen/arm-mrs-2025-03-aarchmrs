# arm-allowlist — AArch64 Feature-Qualified Instruction Allowlist

Use this skill when the user asks about which AArch64 instructions or registers are available for a specific target architecture version and feature set:
- "What instructions can I use on ARMv9.4-A with SVE2?"
- "Which registers are not available without FEAT_SVE?"
- "Give me a list of allowed operations for v9Ap4"
- "What is prohibited without FEAT_SME at ARMv9.1?"
- "Generate an instruction allowlist for my cortex-X3 target"

## Do NOT use this skill when the user asks about:
- Feature dependency relationships → use `arm-feat`
- Register field layouts or bit positions → use `arm-reg`
- Instruction encoding details or assembly syntax → use `arm-instr`
- What a feature does (prose description) → not available in BSD MRS release

---

## Path resolution

```bash
REPO=$(git rev-parse --show-toplevel)
SCRIPT="$REPO/tools/query_allowlist.py"
```

---

## Commands

### Summary: allowed/prohibited counts for an arch version

```bash
python "$SCRIPT" --arch v9Ap4 --summary
```
Returns: count of allowed and prohibited operations and registers for the given arch version.

### Full text list with all allowed operations and prohibited registers

```bash
python "$SCRIPT" --arch v9Ap4
```
Returns: full lists of allowed operations, prohibited operations, and prohibited registers with reasons.

### Add explicit feature flags beyond the arch version baseline

```bash
python "$SCRIPT" --arch v9Ap4 --feat FEAT_SVE2
python "$SCRIPT" --arch v9Ap4 --feat FEAT_SVE2 FEAT_SME FEAT_SME2
```
Returns: allowlist computed with the extra features added on top of the arch-version baseline.

### JSON output (for programmatic use / downstream tools)

```bash
python "$SCRIPT" --arch v9Ap4 --feat FEAT_SVE2 --output json
```
Returns a JSON document with schema_version, query parameters, stats, and full lists.

### List all features active at an arch version

```bash
python "$SCRIPT" --list-features v9Ap4
```
Returns: all FEAT_* names whose min_version ≤ v9Ap4.

---

## Output schema (--output json)

```json
{
  "schema_version": "1.0",
  "query": {
    "arch": "v9Ap4",
    "features": ["FEAT_AdvSIMD", "FEAT_FP", ..., "FEAT_SVE2"],
    "explicit_features": ["FEAT_SVE2"]
  },
  "stats": {
    "total_operations": 2262,
    "allowed_operations": 2216,
    "prohibited_operations": 46,
    "total_registers": 1607,
    "allowed_registers": 1398,
    "prohibited_registers": 209
  },
  "allowed_operations": ["ABS", "ADC", "ADD_addsub_imm", ...],
  "prohibited_operations": ["ADDG", ...],
  "allowed_registers": [{"name": "SCTLR_EL1", "state": "AArch64"}, ...],
  "prohibited_registers": [
    {"name": "AMEVCNTR0_0_EL0", "state": "AArch64",
     "reason": "IsFeatureImplemented(FEAT_AMUv1)"}
  ]
}
```

---

## Architecture version strings

Use these exact strings for `--arch`:

| Version | Colloquial name |
|---------|----------------|
| `v8Ap0` | ARMv8.0-A (baseline AArch64) |
| `v8Ap1` | ARMv8.1-A |
| `v8Ap2` | ARMv8.2-A |
| `v8Ap3` | ARMv8.3-A |
| `v8Ap4` | ARMv8.4-A |
| `v8Ap5` | ARMv8.5-A |
| `v8Ap6` | ARMv8.6-A |
| `v8Ap7` | ARMv8.7-A |
| `v8Ap8` | ARMv8.8-A |
| `v8Ap9` | ARMv8.9-A |
| `v9Ap0` | ARMv9.0-A |
| `v9Ap1` | ARMv9.1-A |
| `v9Ap2` | ARMv9.2-A |
| `v9Ap3` | ARMv9.3-A |
| `v9Ap4` | ARMv9.4-A |
| `v9Ap5` | ARMv9.5-A |
| `v9Ap6` | ARMv9.6-A (latest in this release) |

---

## Programmatic API (for H3/H6 downstream skills)

```python
import sys; sys.path.insert(0, "$REPO/tools")
from query_allowlist import query_allowlist

result = query_allowlist(arch='v9Ap4', extra_features=['FEAT_SVE2'])
# result['allowed_operations']   → list of allowed operation_id strings
# result['prohibited_operations'] → list of prohibited operation_id strings
# result['allowed_registers']    → list of {name, state} dicts
# result['prohibited_registers'] → list of {name, state, reason} dicts
# result['query']['features']    → complete active feature set
```

---

## Important constraints

- **Only `IsFeatureImplemented(FEAT_X)` conditions are evaluated.** Complex conditions involving hardware registers (MPAMF_IDR, ERRDEVID, etc.) are conservatively assumed True (available).
- **Feature set is cumulative.** The `--arch vX` version includes all features from v8Ap0 through vX, plus features with no version constraint. `--feat` adds to this set.
- **An operation is allowed if any of its instruction variants are allowed.** To determine if a specific encoding is valid, use `arm-instr` after getting the allowlist.
- **No prose descriptions are available** in the BSD MRS release. If the user needs to understand what a feature or instruction does, consult the ARM Architecture Reference Manual.

---

## Example interactions

**User:** "What AArch64 instructions can I use on ARMv9.2-A?"
```bash
python "$SCRIPT" --arch v9Ap2 --summary
```
Report the counts. If the user wants the full list, run without `--summary`.

**User:** "Does my Cortex-A710 (v9Ap0 + FEAT_SVE2) support FEAT_SME instructions?"
```bash
python "$SCRIPT" --arch v9Ap0 --feat FEAT_SVE2 --summary
# Then check prohibited ops for SME
python "$SCRIPT" --arch v9Ap0 --feat FEAT_SVE2 --output json
# Inspect prohibited_operations for SME-prefixed entries
```

**User:** "Give me the allowlist JSON for my toolchain at v9Ap4"
```bash
python "$SCRIPT" --arch v9Ap4 --output json
```
Return the JSON and explain the schema fields.
