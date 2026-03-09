# Cache Schema Design

This document records the verified cache JSON schemas for each entity type, derived from running `tools/probe.py` against the actual MRS source files. These schemas are the authoritative reference for implementing `tools/build_index.py` and the query scripts.

---

## 1. Feature Cache — `cache/features.json`

### Source structure (verified)

`Features.json` is a single object with two constraint locations that **both** must be walked:
- `parameters[i].constraints` — per-feature AST constraint list (360 of 361 parameters have these)
- top-level `constraints` — globally scoped constraints (3 entries; trivial in this release but present)

All 361 parameters are `Parameters.Boolean` type. 344 are `FEAT_*` names; 17 are version strings (`v8Ap0`…`v9Ap6`).

### `min_version` extraction algorithm

Version constraints are encoded as `AST.BinaryOp` nodes with `op: "-->"`. The traversal must recurse into all subtrees — a naive string search misses constraints nested inside compound expressions (e.g., `(FEAT_X && FEAT_Y) --> v9Ap2`).

```
For each parameter:
  Walk constraints (both per-parameter and top-level)
  Find BinaryOp nodes where op == "-->"
    If left is FEAT_* and right is vNApM → record (feature, version)
    If right is FEAT_* and left is vNApM → record (feature, version) [unusual but handle it]
  Keep only the minimum (earliest) version if multiple are found
```

Known version ordering (oldest → newest):
`v8Ap0 < v8Ap1 < v8Ap2 < v8Ap3 < v8Ap4 < v8Ap5 < v8Ap6 < v8Ap7 < v8Ap8 < v8Ap9 < v9Ap0 < v9Ap1 < v9Ap2 < v9Ap3 < v9Ap4 < v9Ap5 < v9Ap6`

Probe result: 320 of 361 features have a version bound. 41 have no version constraint.

### Cache schema

`cache/features.json` stores the full parameter list as a JSON array. Each entry:

```json
{
  "name": "FEAT_SVE",
  "type": "Parameters.Boolean",
  "min_version": "v8Ap2",
  "constraints": [
    {
      "_type": "AST.BinaryOp",
      "left": {"_type": "AST.Identifier", "value": "FEAT_SVE"},
      "op": "-->",
      "right": {"_type": "AST.Identifier", "value": "v8Ap2"}
    }
  ]
}
```

- `min_version`: earliest version at which this feature is introduced (null if no version constraint found)
- `constraints`: raw AST array preserved verbatim for dependency tree rendering

---

## 2. Register Cache — `cache/registers/NAME__STATE.json`

### Source structure (verified)

`Registers.json` is a flat JSON array of 1,607 register objects. Key fields:

| Field | Notes |
|-------|-------|
| `name` | Register name, may contain `<n>` for parameterized registers (150 of 1,607) |
| `state` | `"AArch64"`, `"AArch32"`, or `"ext"` |
| `fieldsets` | Array of fieldset objects; each has `values` (the fields array) |
| `accessors` | Array of accessor objects (six `_type` variants) |
| `index_variable` | e.g., `"n"` for parameterized registers (null otherwise) |
| `indexes` | Range defining valid index values (null for non-parameterized) |
| `condition` | AST expression for when this register exists |

### Field types

Each entry in `fieldset.values` is one of several `Fields.*` types. Only `Fields.Field` entries have meaningful names and value enumerations. `Fields.Reserved`, `Fields.ImplementationDefined`, and `Fields.ConditionalField` with no cases are skipped in the cache (they have no `name`).

Probe result for SCTLR_EL1: 59 raw fields → 13 named (cached), 46 unnamed/reserved (skipped).

### Accessor types (all six must be handled)

| `_type` | Count in Registers.json |
|---------|------------------------|
| `Accessors.SystemAccessor` | 2,098 |
| `Accessors.MemoryMapped` | 482 |
| `Accessors.ExternalDebug` | 195 |
| `Accessors.SystemAccessorArray` | 115 |
| `Accessors.BlockAccess` | 109 |
| `Accessors.BlockAccessArray` | 17 |

### Cache file naming

- Non-parameterized: `SCTLR_EL1__AArch64.json`
- Parameterized: `<param>` and any immediately following `_` are replaced with `_param_`, trailing `_` stripped. `DBGBCR<n>_EL1` → `DBGBCR_n_EL1`; `DBGBCR<n>` (no suffix) → `DBGBCR_n`.
- Same name + different state = separate files: `DBGBCR_n_EL1__AArch64.json`, `DBGBCR_n_EL1__ext.json`
- Actual counts: 1,607 register files across 1,514 unique names; 150 registers are parameterized.

### Cache schema

```json
{
  "name": "SCTLR_EL1",
  "state": "AArch64",
  "condition": {
    "_type": "AST.Function",
    "arguments": [{"_type": "AST.Identifier", "value": "FEAT_AA64"}],
    "name": "IsFeatureImplemented"
  },
  "index_variable": null,
  "indexes": null,
  "fieldsets": [
    {
      "condition": {"_type": "AST.Bool", "value": true},
      "width": 64,
      "fields": [
        {
          "name": "UCI",
          "type": "Fields.Field",
          "bits": [{"start": 26, "width": 1}],
          "values": [
            {"value": "'0'", "meaning": null},
            {"value": "'1'", "meaning": null}
          ]
        }
      ]
    }
  ],
  "accessors": [
    {
      "type": "Accessors.SystemAccessor",
      "name": null,
      "encoding": {"op0": 3, "op1": 0, "CRn": 1, "CRm": 0, "op2": 0},
      "access": null
    }
  ]
}
```

Notes:
- `fieldsets[].fields` contains only named fields (unnamed/reserved stripped)
- `values` is `null` when no value enumeration exists for a field
- `meaning` is `null` throughout in the BSD MRS release (prose omitted)
- `accessors[].type` preserves the full `_type` string for all six accessor variants

### `registers_meta.json` — listing and search index

A separate lightweight index for `arm-reg-list` and `arm-search`:

```json
{
  "SCTLR_EL1": [{"state": "AArch64", "cache_key": "SCTLR_EL1__AArch64"}],
  "SCTLR":     [{"state": "AArch32", "cache_key": "SCTLR__AArch32"}],
  "DBGBCR<n>_EL1": [
    {"state": "AArch64", "cache_key": "DBGBCR_n_EL1__AArch64"},
    {"state": "ext",     "cache_key": "DBGBCR_n_EL1__ext"}
  ]
}
```

---

## 3. Operation Cache — `cache/operations/OPERATION_ID.json`

### Source structure (verified)

`Instructions.json` has two parallel structures that must be joined:
- `operations` dict — keyed by `operation_id`; contains behavior (title, brief, decode, operation ASL)
- `instructions` tree — a single `InstructionSet` root with nested `InstructionGroup` and `Instruction` nodes; each leaf carries `operation_id`, `encoding`, and `assembly`

The two sets match perfectly: 2,262 `operation_id` values appear in both. `operation_id` is the universal join key.

### Encoding hierarchy (critical finding)

The instruction tree has up to 4 levels of depth. Each level carries partial encoding information:

```
InstructionSet (A64)          ← broadest encoding class
  └── InstructionGroup        ← intermediate encoding class
        └── InstructionGroup  ← most specific group; defines operand fields + fixed class bits
              └── Instruction ← leaf; carries only the per-variant discriminating bits
```

**Verified example — `ADD_addsub_imm` path:**

| Level | Node | Encoding contribution |
|-------|------|-----------------------|
| 0 | `InstructionSet A64` | `op0[31]='x'`, `op1[28:25]='xxxx'` |
| 1 | `InstructionGroup dpimm` | `op0[30:29]='xx'`, `[28:26]='100'`, `op1[25:22]='xxxx'` |
| 2 | `InstructionGroup addsub_imm` | `sf[31]='x'`, `op[30]='x'`, `S[29]='x'`, `[25:23]='010'`, `sh[22]='x'`, `imm12[21:10]`, `Rn[9:5]`, `Rd[4:0]` |
| 3 | `Instruction ADD_32_addsub_imm` | `[31:29]='000'` (discriminates sf=0, op=0, S=0) |

Each level reuses bit positions, with deeper levels being more specific. The leaf's `'000'` at `[31:29]` overrides the group's named `sf`/`op`/`S` fields at the same positions for this variant.

### Merge algorithm (as implemented in `build_index.py`)

A simplified "first write wins by start key" approach produces overlapping fields (38 bits for a 32-bit instruction) because the leaf's multi-bit field (e.g., `[31:29]='000'`, start=29, width=3) and the group's individual named fields (sf[31], op[30], S[29]) have different `start` values and both get written. The actual implementation uses a **two-pass bit-level algorithm**:

**Pass 1 — Named fields (bottom-up, bit-range collision detection):**
Walk from leaf to root. For each field with a name, add it to `named_fields` only if **none** of its bit positions are already claimed. This captures the most specific (deepest) named definition for each bit range.

**Pass 2 — Fixed bits (bottom-up, per-bit-position):**
Walk from leaf to root. For each bit position carrying a `'0'` or `'1'` value, record it only if not yet seen. The leaf's discriminating bits are recorded first.

**Final construction:**
- For each named field: reconstruct its actual value from the per-bit fixed map. All `'x'` → `kind='operand'`; any fixed bit → `kind='fixed'`.
- For fixed bits **not** covered by any named field: group into contiguous ranges → `kind='class'` (encoding class identifiers, unnamed in source).
- Sort all fields MSB first (descending `start`).

### Field classification

- `"kind": "fixed"` — named field whose bits are fully determined (value has no `'x'`)
- `"kind": "operand"` — named field whose bits are all variable (`'x'`; user-supplied operand)
- `"kind": "class"` — unnamed fixed-value range (encoding class identifier)

### Resolved encoding for `ADD_32_addsub_imm` (verified against actual cache output)

The two-pass algorithm captures `op1[28:25]` from the `InstructionSet` level (bits 28–25 are unclaimed when that level is processed), then reconstructs its value as `'1000'` from the fixed-bit map. The remaining uncovered fixed bits [24:23] become a `class` field.

```
[31:31] sf    = '0'    kind=fixed   (discriminator: leaf '000' → bit 31='0')
[30:30] op    = '0'    kind=fixed   (discriminator: leaf '000' → bit 30='0')
[29:29] S     = '0'    kind=fixed   (discriminator: leaf '000' → bit 29='0')
[28:25] op1   = '1000' kind=fixed   (named at InstructionSet level; value from dpimm+'010' at [25])
[24:23] null  = '10'   kind=class   (residual encoding class bits)
[22:22] sh    = 'x'    kind=operand
[21:10] imm12 = 'xxxxxxxxxxxx' kind=operand
[9:5]   Rn    = 'xxxxx'  kind=operand
[4:0]   Rd    = 'xxxxx'  kind=operand
```

Total: 32 bits exactly. The groupings differ from the conceptual description in §3 above (which anticipated `[28:26]='100'` and `[25:23]='010'` as separate class fields), but the bit values are correct and the `kind` classification is valid.

### Cache schema

```json
{
  "operation_id": "ADD_addsub_imm",
  "title": "",
  "brief": "Add (immediate)",
  "description": null,
  "decode": null,
  "operation": "// ASL pseudocode text (full, not truncated in cache)",
  "instruction_variants": [
    {
      "name": "ADD_32_addsub_imm",
      "condition": {"_type": "AST.Bool", "value": true},
      "assembly": {
        "_type": "Instruction.Assembly",
        "description": null,
        "symbols": [...]
      },
      "encoding": {
        "width": 32,
        "fields": [
          {"start": 31, "width": 1,  "name": "sf",    "value": "'0'",            "kind": "fixed"},
          {"start": 30, "width": 1,  "name": "op",    "value": "'0'",            "kind": "fixed"},
          {"start": 29, "width": 1,  "name": "S",     "value": "'0'",            "kind": "fixed"},
          {"start": 26, "width": 3,  "name": null,    "value": "'100'",          "kind": "class"},
          {"start": 23, "width": 3,  "name": null,    "value": "'010'",          "kind": "class"},
          {"start": 22, "width": 1,  "name": "sh",    "value": "'x'",            "kind": "operand"},
          {"start": 10, "width": 12, "name": "imm12", "value": "'xxxxxxxxxxxx'", "kind": "operand"},
          {"start": 5,  "width": 5,  "name": "Rn",    "value": "'xxxxx'",        "kind": "operand"},
          {"start": 0,  "width": 5,  "name": "Rd",    "value": "'xxxxx'",        "kind": "operand"}
        ]
      }
    }
  ]
}
```

Notes:
- `operation` stores the full ASL text (not truncated — truncation is the query script's responsibility)
- `decode` is `null` when no shared decode block exists (optional in schema; do not assume present)
- `fields` are sorted by `start` descending (MSB first) for readability
- `assembly.symbols` is preserved verbatim (used by `arm-instr` syntax display)
- `title` and `brief` are present but often empty strings or `"."` in this BSD release

---

## 4. Query Resolution Rules (shared across all query scripts)

### AArch32 vs AArch64 disambiguation
When a register name matches multiple states, **prefer AArch64**. Note the existence of other states in the response. Require `--state AArch32` or `--state ext` to explicitly select non-AArch64 variants.

### Parameterized register resolution
Query `DBGBCR2_EL1` → normalize digit sequences to `<n>` → look up `DBGBCR<n>_EL1` in `registers_meta.json` → load `DBGBCR_n_EL1__AArch64.json`. Note the specific instance index in the response.

### Cache staleness detection
`cache/manifest.json` stores SHA-256 hashes of all three source files at build time. Query scripts check the manifest on startup and emit a warning (not a failure) if any source file has changed since the cache was built.

### Missing cache error
```
Cache not found. Run: python tools/build_index.py
```
Exit non-zero. Never auto-rebuild inside a query script invocation.
