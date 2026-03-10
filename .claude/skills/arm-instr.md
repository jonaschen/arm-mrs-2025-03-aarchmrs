# arm-instr -- ARM Instruction Encoding and Behavior Queries

Use this skill when the user asks about AArch64 (A64) instructions:
- What encoding variants exist for an instruction (`ADC`, `ADD`, `MRS`, ...)
- The bit layout of an instruction's 32-bit encoding word
- Assembly syntax / operand template for an instruction
- ASL pseudocode for decode or operation semantics
- Listing all operation_ids for a given mnemonic

## Do NOT use this skill when the user asks about:
- "How do I read/write SCTLR_EL1?" -> use `arm-reg` (register accessor)
- "What encoding does MRS use to SELECT a register?" -> use `arm-reg REG --access`
- "Does this CPU support SVE?" -> use `arm-feat`

### MRS ambiguity
- "MRS instruction encoding" (the MRS A64 opcode itself) -> `arm-instr MRS`
- "MRS/MSR encoding that selects SCTLR_EL1" (op0/op1/op2/CRn/CRm) -> `arm-reg SCTLR_EL1 --access`

---

## Path resolution

```bash
REPO=$(git rev-parse --show-toplevel)
SCRIPT="$REPO/tools/query_instruction.py"
```

---

## Commands

### Summary for an operation (variants + assembly template)
```bash
python3 "$SCRIPT" ADC
python3 "$SCRIPT" ADD_addsub_imm
```
Returns: operation ID, title/brief (if available), all instruction variant names, and their
assembly syntax templates.

### Encoding bit fields for all variants
```bash
python3 "$SCRIPT" ADC --enc
```
Returns: for each variant, the 32-bit field layout with bit ranges, field names, fixed values,
and kind (`fixed` = always this value, `operand` = encodes a register/immediate, `class` = ISA
class discriminator).

### ASL pseudocode
```bash
python3 "$SCRIPT" ADC --op
python3 "$SCRIPT" ADC --op --full
```
Returns: the `decode` block (shared decode logic) and `operation` block (instruction semantics),
truncated to 60 lines by default. Use `--full` for the complete output.

**Note:** In the BSD MRS release, all pseudocode fields are `null` or `// Not specified`.
ASL pseudocode is only available in the full (non-redistributable) ARM Architecture Reference Manual.

### List all operation_ids matching a pattern
```bash
python3 "$SCRIPT" --list ADD
python3 "$SCRIPT" --list MRS
```
Returns: all operation_id strings whose name contains the pattern (case-insensitive).
Use this to find the correct operation_id when you only know the mnemonic.

---

## Important constraints

- **operation_id is the key.** A mnemonic like `ADD` may map to multiple operation_ids:
  `ADD_addsub_imm`, `ADD_addsub_ext`, `ADD_addsub_shift`, `ADD_z_zi`, etc. Use `--list` to find them.
- **No prose descriptions.** `title`, `brief`, and `description` are null in the BSD release.
  Do not synthesize descriptions. State "not available in BSD MRS release".
- **No ASL pseudocode.** `decode` and `operation` are null/`// Not specified` in the BSD release.
  Only the encoding bit layout and assembly templates are present.
- **Encoding fields:** `kind=fixed` means bits are always that value; `kind=operand` encodes
  a register/immediate; `kind=class` is the A64 instruction class discriminator (bits [28:25]).
- **`instruction_variants`** are the actual named instruction forms (e.g. `ADC_32_addsub_carry`,
  `ADC_64_addsub_carry`) that share the same operation semantics.

---

## Example interactions

**User:** "What are the encoding variants of ADC?"
```bash
python3 "$SCRIPT" ADC
```
Report the two variants (32-bit and 64-bit) and their assembly templates.

**User:** "Show me the bit layout of the ADC instruction"
```bash
python3 "$SCRIPT" ADC --enc
```
Present the encoding table. Explain `sf=0` for 32-bit, `sf=1` for 64-bit.

**User:** "What ADD instructions are there in SIMD?"
```bash
python3 "$SCRIPT" --list ADD
```
Filter results for `advsimd` in the operation_id and list those.

**User:** "What is the MRS instruction encoding?"
```bash
python3 "$SCRIPT" MRS --enc
```
Report the 32-bit MRS encoding, noting op0/op1/op2/CRn/CRm are the system register selector fields.
Clarify that the actual per-register encoding values come from `arm-reg REG_NAME --access`.
