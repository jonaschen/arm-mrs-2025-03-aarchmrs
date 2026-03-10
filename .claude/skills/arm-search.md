# arm-search -- ARM Architecture Cross-Cutting Discovery

Use this skill when the user wants to discover what ARM registers or instructions exist,
without knowing the exact name:
- "Find all EL2 registers"
- "What registers are related to TCR?"
- "List all ADD variants"
- "Is there anything in the spec for 'memory tagging'?"

After getting results, follow up with `arm-reg`, `arm-feat`, or `arm-instr` for the
specific entity the user is interested in.

## Do NOT use this skill when the user already knows the exact name:
- "What are the fields of SCTLR_EL1?" -> use `arm-reg` directly
- "How does FEAT_SVE work?" -> use `arm-feat` directly
- "Show me the ADC encoding" -> use `arm-instr` directly

---

## Path resolution

```bash
REPO=$(git rev-parse --show-toplevel)
SCRIPT="$REPO/tools/query_search.py"
```

---

## Commands

### Combined search (registers + operations)
```bash
python3 "$SCRIPT" TCR
```
Returns: matching registers (with state) and matching operation IDs.

### Registers only
```bash
python3 "$SCRIPT" --reg EL2
python3 "$SCRIPT" --reg EL2 --state AArch64
```
Returns: all registers whose name contains the pattern, with their state.
`--state` accepts: `AArch64`, `AArch32`, `ext`

### Operations only
```bash
python3 "$SCRIPT" --op ADD
```
Returns: all operation_id values containing the pattern (case-insensitive).

---

## Workflow after search

Once results are returned, pick the most relevant entry and query it directly:

```bash
# User asked about TCR registers -> found TCR_EL1
REPO=$(git rev-parse --show-toplevel)
python3 "$REPO/tools/query_register.py" TCR_EL1

# User asked about ADD instructions -> found ADD_addsub_imm
python3 "$REPO/tools/query_instruction.py" ADD_addsub_imm --enc
```

---

## Example interactions

**User:** "Find all EL2 system registers"
```bash
python3 "$SCRIPT" --reg EL2 --state AArch64
```
Report the count and list. Offer to query any specific register's fields.

**User:** "What is there in the spec related to TCR?"
```bash
python3 "$SCRIPT" TCR
```
Report register and operation results. Note the most likely ones (e.g. `TCR_EL1`, `TCR_EL2`)
and offer to query them with `arm-reg`.

**User:** "List all SIMD add instructions"
```bash
python3 "$SCRIPT" --op ADD
```
Filter the results to those containing `advsimd` in the operation_id.
Offer to show encoding details for any variant.
