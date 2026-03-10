# arm-reg -- ARM Architecture Register Queries

Use this skill when the user asks about AArch64/AArch32 system registers:
- Field layout or bit positions of a register (`SCTLR_EL1`, `TCR_EL1`, ...)
- What a specific field does or what values it takes (`SCTLR_EL1.UCI`, ...)
- How to access a register via MRS/MSR (encoding: op0/op1/op2/CRn/CRm)
- Listing registers matching a name pattern or at a particular EL

## Do NOT use this skill when the user asks about:
- Architecture features or extensions (`FEAT_SVE`, version support) -> use `arm-feat`
- "How does instruction ADC work?" -> use `arm-instr`
- "What is the MRS instruction encoding?" (the instruction itself) -> use `arm-instr MRS`
- "What encoding does MRS use to access SCTLR_EL1?" -> use THIS skill (`arm-reg SCTLR_EL1 --access`)

---

## Path resolution

```bash
REPO=$(git rev-parse --show-toplevel)
SCRIPT="$REPO/tools/query_register.py"
```

If `ARM_MRS_CACHE_DIR` is set, it points to a shared cache; `REPO` still resolves correctly for the script location.

---

## Commands

### All fields for a register (default: AArch64)
```bash
python3 "$SCRIPT" SCTLR_EL1
```
Returns: bit positions, field types, value counts. AArch64 preferred when multiple states match.

### Single field detail
```bash
python3 "$SCRIPT" SCTLR_EL1 UCI
```
Returns: bit position, type, count of defined values.

### Single field with full value enumeration
```bash
python3 "$SCRIPT" SCTLR_EL1 UCI --values
```
Returns: each value encoding and its meaning (if available).

### Accessor / MRS-MSR encoding
```bash
python3 "$SCRIPT" SCTLR_EL1 --access
```
Returns: all accessor types (SystemAccessor, MemoryMapped, ExternalDebug, SystemAccessorArray),
assembly mnemonic, and the op0/op1/op2/CRn/CRm encoding fields, plus condensed access rules.

### Parameterized registers (e.g. DBGBCR<n>_EL1)
```bash
python3 "$SCRIPT" DBGBCR2_EL1
```
The digit `2` is normalized to `<n>` for lookup; the output header shows the requested instance.
Valid index range is shown in the `Index` line of the output.

### Explicit state selection
```bash
python3 "$SCRIPT" SCTLR_EL1 --state AArch32
python3 "$SCRIPT" SCTLR_EL1 --state ext
```
Use when the register exists in multiple states. Default is AArch64.

### List registers matching a pattern
```bash
python3 "$SCRIPT" --list EL1
python3 "$SCRIPT" --list EL2 --state AArch64
```
Returns: all register names containing the pattern (case-insensitive), with their state.

---

## Important constraints

- **No prose descriptions.** The BSD MRS release omits all descriptive text. `title`, `purpose`,
  `description`, and field `meaning` are `null` throughout. Do not synthesize meaning -- tell the
  user it is not available in this release.
- **AArch64 is the default state.** When a register exists in both AArch32 and AArch64, AArch64
  is returned unless `--state AArch32` is specified. The output notes when other states exist.
- **Accessor types:** `SystemAccessor` = MRS/MSR, `SystemAccessorArray` = parameterized MRS/MSR
  (e.g. `TRCACVR<m>`), `MemoryMapped` = memory-mapped peripheral access, `ExternalDebug` = APB/JTAG.
- **Access rules use ASL-like notation.** `PSTATE.EL == EL1` means "when running at EL1".
  `[AST.Assignment]` indicates a register read/write action (prose omitted in BSD release).
- **Field type `Field`** is the standard type; other types may appear for special fields.

---

## Example interactions

**User:** "What are the fields of SCTLR_EL1?"
```bash
python3 "$SCRIPT" SCTLR_EL1
```
Report the field table. Note that field descriptions are unavailable.

**User:** "What bit is the UCI field of SCTLR_EL1?"
```bash
python3 "$SCRIPT" SCTLR_EL1 UCI
```
Report bit position. Say descriptions are not available in this release.

**User:** "What values does SCTLR_EL1.M take?"
```bash
python3 "$SCRIPT" SCTLR_EL1 M --values
```
Report each value and note that meanings are null in the BSD release.

**User:** "What is the MRS encoding for SCTLR_EL1?"
```bash
python3 "$SCRIPT" SCTLR_EL1 --access
```
Report the `A64.MRS` accessor entry: `op0='11' op1='000' CRn='0001' CRm='0000' op2='000'`.

**User:** "List all EL2 registers"
```bash
python3 "$SCRIPT" --list EL2 --state AArch64
```
Present the list. Note there are also `ext` state registers if relevant.
