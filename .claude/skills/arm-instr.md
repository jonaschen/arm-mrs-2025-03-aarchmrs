# arm-instr -- ARM Instruction Encoding and Behavior Queries

Use this skill when the user asks about AArch64 (A64), T32 (Thumb-2), or A32 (classic ARM 32-bit) instructions:
- What encoding variants exist for an instruction (`ADC`, `ADD`, `LDR`, `B`, ...)
- The bit layout of an instruction's 32-bit encoding word
- Assembly syntax / operand template for an instruction
- ASL pseudocode for decode or operation semantics
- Listing all operation_ids for a given mnemonic
- T32 or A32 instruction encodings (use `--isa t32` or `--isa a32`)

## Do NOT use this skill when the user asks about:
- "How do I read/write SCTLR_EL1?" -> use `arm-reg` (register accessor)
- "What encoding does MRS use to SELECT a register?" -> use `arm-reg REG --access`
- "Does this CPU support SVE?" -> use `arm-feat`

### ISA routing
| User query | Use |
|-----------|-----|
| "What is the A64 encoding of ADC?" | `arm-instr ADC` (default A64) |
| "Show me the T32 LDR encoding" | `arm-instr LDR --isa t32` |
| "What is the A32 branch encoding?" | `arm-instr B --isa a32` |
| "What are all T32 instructions matching ADD?" | `arm-instr --list ADD --isa t32` |

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
python3 "$SCRIPT" LDR --isa t32
python3 "$SCRIPT" LDR --isa a32
```
Returns: operation ID, ISA, title/brief (if available), all instruction variant names, and their
assembly syntax templates.

### Encoding bit fields for all variants
```bash
python3 "$SCRIPT" ADC --enc
python3 "$SCRIPT" LDR --isa t32 --enc
python3 "$SCRIPT" B --isa a32 --enc
```
Returns: for each variant, the 32-bit field layout with bit ranges, field names, fixed values,
and kind (`fixed` = always this value, `operand` = encodes a register/immediate, `class` = ISA
class discriminator / constant opcode bits).

### ASL pseudocode
```bash
python3 "$SCRIPT" ADC --op
python3 "$SCRIPT" ADC --op --full
```
Returns: the `decode` block (shared decode logic) and `operation` block (instruction semantics),
truncated to 60 lines by default. Use `--full` for the complete output.

**Note:** In the BSD MRS release, all A64 pseudocode fields are `null` or `// Not specified`.
T32/A32 hand-curated data also has `null` pseudocode.
ASL pseudocode is only available in the full (non-redistributable) ARM Architecture Reference Manual.

### List all operation_ids matching a pattern
```bash
python3 "$SCRIPT" --list ADD
python3 "$SCRIPT" --list MRS
python3 "$SCRIPT" --list LDR --isa t32
python3 "$SCRIPT" --list B --isa a32
```
Returns: all operation_id strings for the selected ISA whose name contains the pattern
(case-insensitive). Use this to find the correct operation_id when you only know the mnemonic.

---

## ISA data coverage

| ISA | Source | Operations | ASL |
|-----|--------|-----------|-----|
| A64 | BSD MRS JSON (v9Ap6-A, Build 445) | 2,262 | `null` in BSD release |
| T32 | Hand-curated from ARM DDI0487 | 6 (starter set: LDR, STR, ADD, B, BL, MOV) | `null` |
| A32 | Hand-curated from ARM DDI0487 | 6 (starter set: LDR, STR, ADD, SUB, B, BL) | `null` |

T32/A32 data requires `python3 tools/build_arm_arm_index.py` to build the arm_arm cache.
A64 data requires `python3 tools/build_index.py` to build the main cache.

---

## Important constraints

- **operation_id is the key.** In A64, a mnemonic like `ADD` may map to multiple operation_ids:
  `ADD_addsub_imm`, `ADD_addsub_ext`, `ADD_addsub_shift`, `ADD_z_zi`, etc. Use `--list` to find them.
  In T32/A32 (hand-curated), one operation_id per mnemonic is used.
- **No prose descriptions (A64 BSD).** `title`, `brief`, and `description` are null in the BSD release.
  Do not synthesize descriptions. State "not available in BSD MRS release".
- **T32/A32 descriptions available.** Hand-curated operations have brief descriptions.
- **No ASL pseudocode.** `decode` and `operation` are null in both the BSD A64 release and the
  hand-curated T32/A32 data. Only the encoding bit layout and assembly templates are present.
- **Encoding fields:** `kind=fixed` means bits are always that value; `kind=operand` encodes
  a register/immediate; `kind=class` denotes constant opcode/class discriminator bits.
- **`instruction_variants`** are the actual named instruction forms (e.g. `ADC_32_addsub_carry`,
  `ADC_64_addsub_carry`) that share the same operation semantics.
- **T32/A32 condition codes.** A32 instructions have a `cond` operand field at bits[31:28].
  T32 conditional branches use a different encoding from unconditional branches.

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

**User:** "Show me the T32 LDR encoding"
```bash
python3 "$SCRIPT" LDR --isa t32 --enc
```
Present the T32 encoding table showing bits[31:20] as constant opcode, Rn, Rt, and imm12.

**User:** "What is the A32 branch instruction format?"
```bash
python3 "$SCRIPT" B --isa a32 --enc
```
Show the A32 B encoding: cond[31:28], opcode 1010[27:24], and 24-bit signed offset imm24[23:0].

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

