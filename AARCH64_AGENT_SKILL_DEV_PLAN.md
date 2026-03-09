# AArch64 Agent Skills — Development Plan

## Goal

Create a set of Claude Code agent skills that ground hardware-related AI responses in the official ARM Machine Readable Specification (MRS), eliminating hallucination for tasks involving registers, instructions, and architecture features.

---

## Data Reality Check

Key facts about this MRS release (v9Ap6-A, Build 445, March 2025):

| File | Size | Entries | Description fields |
|------|------|---------|-------------------|
| `Features.json` | 1 MB | 344 `FEAT_*` + 17 version params | Mostly `null` (BSD subset omits prose) |
| `Instructions.json` | 38 MB | 4,584 instruction nodes, 2,262 operations | Operation `brief`/`description` present |
| `Registers.json` | 75 MB | 1,607 registers | `title`/`purpose` mostly `null` |

The data provides **structural facts** (encodings, field layouts, bit ranges, access modes, feature constraints), but **not prose descriptions**. Skills are designed around what is actually present.

Loading these files whole in a skill context is impossible (~100M+ tokens). The solution is **targeted extraction** — load only the specific entity requested.

### Data model notes (verified against actual files)

**Feature constraints live in two locations:**
- `parameters[i].constraints` — per-feature constraint expressions (360 of 361 parameters have these)
- top-level `constraints` — globally scoped constraints (3 entries in this release; trivial but present)

Both arrays must be walked by the extractor. Missing the top-level array silently drops dependency edges.

**Accessor types in Registers.json (actual distribution):**

| `_type` | Count |
|---------|-------|
| `Accessors.SystemAccessor` | 2,098 |
| `Accessors.MemoryMapped` | 482 |
| `Accessors.ExternalDebug` | 195 |
| `Accessors.SystemAccessorArray` | 115 |
| `Accessors.BlockAccess` | 109 |
| `Accessors.BlockAccessArray` | 17 |

All six types must be handled by the `arm-reg-access` query tool.

**Instruction identity: `operation_id` is the universal key.**
The `operations` dict in `Instructions.json` is keyed by `operation_id` (e.g., `"ADC"`, `"add_z_p_zz"`).
Every instruction node in the tree also carries `operation_id`. These sets match perfectly (2,262 entries each). This means `operation_id` is the bridge for both behavior lookup (operations dict) and encoding lookup (instruction tree). All skills use `operation_id` as the primary query key.

**Parameterized registers:**
150 of 1,607 registers are parameterized (e.g., `DBGBCR<n>_EL1`). Each has `index_variable` (e.g., `"n"`) and `indexes` (a Range indicating valid values). The same parameterized name can appear multiple times with different states (e.g., `DBGBCR<n>_EL1` exists in both `AArch64` and `ext` states). Cache naming and query resolution must account for this.

**Operation `decode` field:** Optional (null when no shared decode block). Indexing scripts must not assume it is present.

---

## Repository Structure

```
arm-mrs-2025-03-aarchmrs/
├── .gitignore               # Must include cache/
├── tools/
│   ├── build_index.py       # One-time bootstrap: builds cache/
│   ├── query_register.py    # CLI: query_register.py SCTLR_EL1 [FIELD]
│   ├── query_instruction.py # CLI: query_instruction.py ADC [--enc] [--op] [--summary]
│   └── query_feature.py     # CLI: query_feature.py FEAT_SVE [--deps] [--version v9Ap2]
├── cache/                   # Generated, gitignored
│   ├── manifest.json        # Source file hashes for staleness detection
│   ├── registers/           # One JSON file per register × state (~1,800+ files)
│   │   ├── SCTLR_EL1__AArch64.json
│   │   ├── SCTLR__AArch32.json
│   │   ├── DBGBCR_n_EL1__AArch64.json
│   │   └── ...
│   ├── operations/          # One JSON file per operation_id (~2,262 files)
│   │   ├── ADC.json         # operation data + linked instruction encodings
│   │   ├── add_z_p_zz.json
│   │   └── ...
│   ├── features.json        # All 361 features in one file (small enough)
│   └── registers_meta.json  # name→[{state, cache_key}] index for listing/search
└── .claude/
    └── skills/
        ├── arm-reg.md
        ├── arm-instr.md
        ├── arm-feat.md
        └── arm-search.md
```

---

## Module Plan

### Module 1: `arm-reg` — Register Queries

**Trigger:** User asks about a system register, its fields, bit layout, access method, or field values.
**Do NOT use this skill for:** instruction behavior or architecture feature dependencies.

| Sub-command | What it returns |
|-------------|----------------|
| `arm-reg SCTLR_EL1` | All named fields: bit ranges, field types, allowed values |
| `arm-reg SCTLR_EL1 UCI` | Single field detail (bit position, value enumeration) |
| `arm-reg-values SCTLR_EL1 UCI` | All allowed values for a field and their meanings |
| `arm-reg-list EL1 [--state AArch64\|AArch32\|ext]` | Registers matching name pattern, filtered by state |
| `arm-reg-access SCTLR_EL1` | All accessor types, encodings, and access permissions |

**Data used:** `cache/registers/REG_NAME__STATE.json`

**AArch32 vs AArch64 disambiguation:** When a bare name (e.g., `arm-reg SCTLR`) matches registers in multiple states, **prefer AArch64** and note that AArch32 variants also exist. Require `--state AArch32` to explicitly select the AArch32 version. This default is appropriate because the primary use case is AArch64 firmware and driver development.

**Parameterized registers:** Query `arm-reg DBGBCR2_EL1` → query tool normalizes to `DBGBCR_n_EL1` (replacing digit sequences with `n`), loads the parameterized cache entry, and notes the specific instance index requested. Cache files use `_n_` in place of `<n>`.

**`arm-reg-values` motivation:** The most common firmware lookup is "what does setting bit X to value Y mean?" The `values` field on `Fields.Field` contains allowed value meanings. This sub-command surfaces that directly rather than requiring users to parse raw JSON.

---

### Module 2: `arm-instr` — Instruction Queries

**Trigger:** User asks about an instruction's behavior, encoding, or assembly syntax.
**Do NOT use this skill for:** register field layout or feature dependencies.

| Sub-command | What it returns |
|-------------|----------------|
| `arm-instr ADC` | Operation brief, title, all encoding variants (instruction names) |
| `arm-instr ADC --enc` | Encoding bit fields and widths for all ADC variants |
| `arm-instr ADC --op` | Full ASL pseudocode (operation body); truncated to 60 lines by default |
| `arm-instr ADC --op --full` | Full ASL pseudocode without truncation |
| `arm-instr-list ADD` | All operation_ids matching the prefix (e.g., ADD, ADD_addsub_imm, ADD_advsimd) |

**Instruction identity:** All sub-commands accept `operation_id` as the argument (e.g., `ADC`, `ADD_addsub_imm`, `add_z_p_zz`). Use `arm-instr-list` to discover valid operation_ids for a mnemonic. `operation_id` is the operation dict key and also appears on every instruction node in the tree.

**`--op` output size:** SVE and SIMD operations can have hundreds of lines of ASL. Default truncation (60 lines) prevents context bloat. `--full` is available when the complete pseudocode is needed. The `decode` block (argument setup) and `operation` block (execution logic) are returned separately so users can request each independently.

**MRS/MSR encoding clarification:** "What's the encoding of MRS?" is ambiguous:
- The MRS *instruction* encoding → `arm-instr MRS`
- The MRS encoding *for a specific register* (e.g., what `op0/op1/CRn/CRm/op2` selects `SCTLR_EL1`) → `arm-reg-access SCTLR_EL1`

Both are valid queries; the skill routing should distinguish them based on whether the user mentions a register name.

**Data used:** `cache/operations/OPERATION_ID.json` (contains merged operation data + linked instruction node encodings)

---

### Module 3: `arm-feat` — Feature / Extension Queries

**Trigger:** User asks about a `FEAT_*` extension, feature dependencies, or what an architecture version includes.
**Do NOT use this skill for:** register fields or instruction encodings.

| Sub-command | What it returns |
|-------------|----------------|
| `arm-feat FEAT_SVE` | Feature type, all constraint expressions (raw AST) |
| `arm-feat-deps FEAT_SVE` | Direct yes/no answer to dependency question, then full dependency tree |
| `arm-feat-version v9Ap2` | All features with a `FEAT_X --> vNApM` constraint where M ≤ requested version |
| `arm-feat-list SVE` | All `FEAT_*` names containing the pattern |

**`arm-feat-version` algorithm:** Version-to-feature mapping is encoded as AST constraint expressions. The algorithm:
1. Walk all per-feature constraints and the top-level constraints array
2. Find `AST.BinaryOp` nodes with `op == "-->"` where one operand is a version identifier (`v8Ap0`…`v9Ap6`)
3. Build a map: `feature → minimum_version` (taking the earliest version found if multiple constraints exist)
4. Filter by requested version using the known version ordering: `v8Ap0 < v8Ap1 < … < v9Ap6`

A naive string search on the JSON would miss constraints nested inside compound expressions (e.g., `(FEAT_X && FEAT_Y) --> v9Ap2`). The traversal must recurse into all `AST.BinaryOp` subtrees.

**`arm-feat-deps` response format:** First answer the specific question (yes/no: "FEAT_SVE does not directly constrain FEAT_FP16"), then show the full constraint tree as context. Never dump the raw tree without answering the direct question first.

**Data used:** `cache/features.json` (small, ~1 MB, loaded whole)

---

### Module 4: `arm-search` — Cross-cutting Search

**Trigger:** User doesn't know which module to use, or wants to discover entities by keyword.

| Sub-command | What it returns |
|-------------|----------------|
| `arm-search TCR` | Matching registers, operation_ids, and features |
| `arm-search-reg EL2 [--state AArch64]` | Registers whose name contains the pattern |

**Output envelope (uniform JSON for all search results):**
```json
{
  "query": "TCR",
  "results": [
    {"type": "register", "name": "TCR_EL1", "state": "AArch64"},
    {"type": "register", "name": "TCR_EL2", "state": "AArch64"},
    {"type": "operation", "name": "TCANCEL"}
  ]
}
```
This consistent format allows skills to post-process results uniformly regardless of entity type.

**Data used:** `cache/registers_meta.json` + operation keys extracted at build time

---

## Implementation Phases

### Phase 0 — Bootstrap (`tools/build_index.py`)

Steps:
1. Create or update `.gitignore` to include `cache/` **before writing any files**
2. Parse `Features.json` → write `cache/features.json`
3. Parse `Instructions.json` → for each operation_id, write `cache/operations/OPERATION_ID.json` merging operation data with linked instruction node encodings
4. Parse `Registers.json` → for each register, write `cache/registers/NAME__STATE.json`; sanitize `<n>` → `_n_` in filenames; include `index_variable` and `indexes` fields
5. Write `cache/registers_meta.json` (name → state → cache key index)
6. Write `cache/manifest.json` with SHA-256 hashes and mtimes of all three source JSON files

**Memory note:** Parsing `Instructions.json` (38 MB) requires approximately 300–600 MB of RAM due to Python dict overhead. This is acceptable on any modern developer machine. No third-party libraries are needed (`json`, `hashlib`, `os`, `argparse` from stdlib). Python 3.8+ is sufficient.

### Phase 1 — Query Scripts (`tools/`)

Three Python CLI scripts:
- Accept a primary key argument and optional flags
- Load only the relevant cache file(s)
- Return compact, filtered JSON (not raw MRS objects) to stdout
- On missing cache, print a clear error:
  ```
  Cache not found. Run: python tools/build_index.py
  ```
  Do not auto-rebuild inside a script call — too slow for interactive use.
- On stale cache (source file hash differs from manifest), print a warning but continue

### Phase 2 — Skills (`.claude/skills/`)

One skill file per module. Each skill:
- States explicitly what queries it handles and what it does NOT handle (negative examples reduce misrouting)
- Resolves the repo root via `ARM_MRS_CACHE_DIR` env var if set, otherwise uses `git rev-parse --show-toplevel` to find the repo root at invocation time — this ensures skills work regardless of the user's current working directory
- Calls `tools/query_*.py` with the appropriate arguments
- Formats output for the user without re-summarizing what the spec already states clearly

---

## Key Design Decisions

### 1. Cache location: in-repo vs. system cache
In-repo `cache/` (gitignored): simple, portable, no path configuration needed.
`~/.cache/arm-mrs/` or `ARM_MRS_CACHE_DIR`: cleaner, shareable across projects.
**Decision:** Default to in-repo `cache/`. Support `ARM_MRS_CACHE_DIR` override for multi-project use.

### 2. Output format: JSON vs. formatted text
Compact JSON for fields and encoding (preserves precision, directly citable). Plain text summary for operation descriptions (more readable in context). Uniform JSON envelope for multi-entity search results.

### 3. Null descriptions
The BSD MRS omits all prose. Skills must acknowledge this explicitly: "Description not available in the BSD MRS release — see ARM Architecture Reference Manual for prose." Skills must never synthesize a description from the field name or context.

### 4. Instruction identity: `operation_id` as primary key
`operation_id` is the bridge between the operations dict (behavior) and instruction tree nodes (encoding). All instruction sub-commands accept `operation_id`. Users discover valid `operation_id` values via `arm-instr-list`.

### 5. Skill granularity and routing
Four skills, each covering one module. Each skill file must include:
- Positive trigger examples ("use this when the user asks about…")
- Negative examples ("do NOT use this skill if the user is asking about…")

This guards against ambiguous queries (e.g., "how do I set E0POE in SCTLR_EL1?" → `arm-reg`, not `arm-reg-access`; "what instruction writes to SCTLR_EL1?" → `arm-reg-access`, not `arm-instr`).

---

## Implementation Priority

Based on data completeness and firmware development value:

1. **Module 3 (`arm-feat`) first** — Features data is small (1 MB), complete, and foundational. Capability detection (`FEAT_SVE` present?) is the first question in any architecture-conditional code path.
2. **Module 1 (`arm-reg`) second** — Highest firmware/driver value. Register field layout and access encoding are the most common hardware lookup needs.
3. **Module 4 (`arm-search`) third** — Depends on the register meta index built in Phase 0; low implementation cost once the cache exists.
4. **Module 2 (`arm-instr`) last** — Most complex due to the operation_id→encoding mapping; best implemented after the patterns from Modules 1 and 3 are established.

---

## What These Skills Enable

| User Task | Skill | Sub-command |
|-----------|-------|-------------|
| "What fields does SCTLR_EL1 have?" | `arm-reg` | `arm-reg SCTLR_EL1` |
| "What is bit 26 (UCI) of SCTLR_EL1?" | `arm-reg` | `arm-reg SCTLR_EL1 UCI` |
| "What do the values of SCTLR_EL1.M mean?" | `arm-reg` | `arm-reg-values SCTLR_EL1 M` |
| "How do I read SCTLR_EL1 from EL1?" | `arm-reg` | `arm-reg-access SCTLR_EL1` |
| "What op0/CRn/CRm encoding selects TCR_EL2?" | `arm-reg` | `arm-reg-access TCR_EL2` |
| "What does the ADC instruction do?" | `arm-instr` | `arm-instr ADC` |
| "What's the encoding of ADC?" | `arm-instr` | `arm-instr ADC --enc` |
| "What ADD variants exist?" | `arm-instr` | `arm-instr-list ADD` |
| "Does FEAT_SVE require FEAT_FP16?" | `arm-feat` | `arm-feat-deps FEAT_SVE` |
| "What features does ARMv9.2 introduce?" | `arm-feat` | `arm-feat-version v9Ap2` |
| "Find all EL2 registers" | `arm-search` | `arm-search-reg EL2 --state AArch64` |
