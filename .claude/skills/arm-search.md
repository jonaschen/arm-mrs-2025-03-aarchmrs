# arm-search -- ARM Architecture Cross-Cutting Discovery

Use this skill when the user wants to discover what ARM registers or instructions exist,
without knowing the exact name:
- "Find all EL2 registers"
- "What registers are related to TCR?"
- "List all ADD variants"
- "Is there anything in the spec for 'memory tagging'?"
- "Find GIC registers related to interrupt enable"
- "Is there a GIC register for EnableGrp1?"
- "Find all CoreSight ETM registers"
- "Is there a CoreSight register for trace enable?"

After getting results, follow up with `arm-reg`, `arm-feat`, `arm-instr`, or `arm-gic` for the
specific entity the user is interested in.

## Do NOT use this skill when the user already knows the exact name:
- "What are the fields of SCTLR_EL1?" -> use `arm-reg` directly
- "How does FEAT_SVE work?" -> use `arm-feat` directly
- "Show me the ADC encoding" -> use `arm-instr` directly
- "What are the fields of GICD_CTLR?" -> use `arm-gic` directly

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

### GIC register search (requires GIC cache)
```bash
python3 "$SCRIPT" EnableGrp1
python3 "$SCRIPT" --spec gic EnableGrp1
python3 "$SCRIPT" --spec gic CTLR
```
The combined search automatically includes GIC registers when the GIC cache is present.
Use `--spec gic` to restrict results to GIC registers only.
GIC results appear as `GIC Registers` with the block name (GICD/GICR/GITS).
Follow up with `arm-gic` for field details.

### CoreSight register search (requires CoreSight cache)
```bash
python3 "$SCRIPT" TRC
python3 "$SCRIPT" --spec coresight TRC
python3 "$SCRIPT" --spec coresight CTI
```
The combined search automatically includes CoreSight registers when the CoreSight cache is present.
Use `--spec coresight` to restrict results to CoreSight registers only.
CoreSight results appear as `CoreSight Registers` with the component name (ETM/CTI/STM/ITM/ID_BLOCK).
Follow up with `arm-coresight` for field details.

---

## Workflow after search

Once results are returned, pick the most relevant entry and query it directly:

```bash
# User asked about TCR registers -> found TCR_EL1
REPO=$(git rev-parse --show-toplevel)
python3 "$REPO/tools/query_register.py" TCR_EL1

# User asked about ADD instructions -> found ADD_addsub_imm
python3 "$REPO/tools/query_instruction.py" ADD_addsub_imm --enc

# User asked about GIC registers -> found GICD_CTLR
python3 "$REPO/tools/query_gic.py" GICD_CTLR

# User asked about CoreSight registers -> found TRCPRGCTLR
python3 "$REPO/tools/query_coresight.py" etm TRCPRGCTLR
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

**User:** "Is there a GIC register for EnableGrp1?"
```bash
python3 "$SCRIPT" EnableGrp1
```
GIC results appear in the `GIC Registers` section. Route the user to `arm-gic GICD_CTLR EnableGrp1S`.

**User:** "Find all GICD control registers"
```bash
python3 "$SCRIPT" --spec gic GICD_C
```
Returns only GIC registers matching the pattern. Route any specific hit to `arm-gic`.

**User:** "Find all ETM trace registers"
```bash
python3 "$SCRIPT" TRC
python3 "$SCRIPT" --spec coresight TRC
```
CoreSight results appear in the `CoreSight Registers` section. Route the user to `arm-coresight etm TRCPRGCTLR`.

**User:** "Is there a CoreSight register that controls trace enable?"
```bash
python3 "$SCRIPT" --spec coresight EN
```
Returns TRCPRGCTLR (ETM) and others containing EN fields. Route to `arm-coresight etm TRCPRGCTLR EN`.
