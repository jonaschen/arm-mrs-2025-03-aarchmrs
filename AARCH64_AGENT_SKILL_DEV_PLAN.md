# ARM Agent Skills — Complete Development Plan

This document is the canonical design reference for the ARM agent skills project.

- **Part I** covers the original AARCHMRS skills (M0–M4), all of which are complete.
- **Part II** covers the extension plan: PMU Events, ARM ARM (T32/A32 + ASL), GIC, and CoreSight.

---

# Part I — Foundation Skills (Completed)

## Goal

Create a set of Claude Code agent skills that ground hardware-related AI responses in the official
ARM Machine Readable Specification (MRS), eliminating hallucination for tasks involving registers,
instructions, and architecture features.

**Status:** M0–EX complete. 137/137 eval tests pass (100%). See `ROADMAP.md` for milestone detail.

### Implementation deviations from original design

| Area | Design | Actual |
|------|--------|--------|
| Shared utilities | Not specified | `tools/cache_utils.py` extracts `check_staleness(isa)`, `render_ast()`, and `CACHE_DIR`/`ARM_ARM_CACHE` path constants; all four query scripts import from it |
| `render_ast()` | Single copy in `query_feature.py` | Canonical copy in `cache_utils.py`; `query_register.py` no longer duplicates it |
| `check_staleness()` | Per-script, A64-only | Unified in `cache_utils.py` with `isa` parameter; handles arm_arm manifest for T32/A32 |
| `import re` location | Inside `render_assembly()` | Moved to module top in `query_instruction.py` |
| Eval test count | 51 (original design) | 137 (51 A64 + 16 T32/A32 + 18 GIC + 24 CoreSight + 14 PMU + 14 EX cross-routing/spec) |
| `--spec` choices | `gic`, `coresight` (design §6.4) | Extended to `aarchmrs`, `gic`, `coresight`, `pmu` (Milestone EX) |
| EX-1 cross-routing | GICD_CTLR not in AARCHMRS | GICD_CTLR IS in AARCHMRS as `ext`-state (memory-mapped); arm-gic provides GIC-specific field view |

---

## Data Reality Check

Key facts about this MRS release (v9Ap6-A, Build 445, March 2025):

| File | Size | Entries | Description fields |
|------|------|---------|-------------------|
| `Features.json` | 1 MB | 344 `FEAT_*` + 17 version params | Mostly `null` (BSD subset omits prose) |
| `Instructions.json` | 38 MB | 4,584 instruction nodes, 2,262 operations | Operation `brief`/`description` present |
| `Registers.json` | 75 MB | 1,607 registers | `title`/`purpose` mostly `null` |

The data provides **structural facts** (encodings, field layouts, bit ranges, access modes, feature
constraints), but **not prose descriptions**. Skills are designed around what is actually present.

Loading these files whole in a skill context is impossible (~100M+ tokens). The solution is
**targeted extraction** — load only the specific entity requested.

### Data model notes (verified against actual files)

**Feature constraints live in two locations:**
- `parameters[i].constraints` — per-feature constraint expressions (360 of 361 parameters have these)
- top-level `constraints` — globally scoped constraints (3 entries in this release; trivial but present)

Both arrays must be walked by the extractor. Missing the top-level array silently drops dependency
edges.

**Accessor types in Registers.json (actual distribution):**

| `_type` | Count |
|---------|-------|
| `Accessors.SystemAccessor` | 2,098 |
| `Accessors.MemoryMapped` | 482 |
| `Accessors.ExternalDebug` | 195 |
| `Accessors.SystemAccessorArray` | 115 |
| `Accessors.BlockAccess` | 109 |
| `Accessors.BlockAccessArray` | 17 |

All six types are handled by `tools/query_register.py`.

**Instruction identity: `operation_id` is the universal key.**
The `operations` dict in `Instructions.json` is keyed by `operation_id` (e.g., `"ADC"`,
`"add_z_p_zz"`). Every instruction node in the tree also carries `operation_id`. These sets
match perfectly (2,262 entries each). This means `operation_id` is the bridge for both behavior
lookup (operations dict) and encoding lookup (instruction tree). All skills use `operation_id`
as the primary query key.

**Parameterized registers:**
150 of 1,607 registers are parameterized (e.g., `DBGBCR<n>_EL1`). Each has `index_variable`
(e.g., `"n"`) and `indexes` (a Range indicating valid values). The same parameterized name can
appear multiple times with different states (e.g., `DBGBCR<n>_EL1` exists in both `AArch64` and
`ext` states). Cache naming and query resolution account for this.

**Operation `decode` field:** Optional (null when no shared decode block). Indexing scripts must
not assume it is present.

---

## Repository Structure (as built)

```
arm-mrs-2025-03-aarchmrs/
├── .gitignore
├── tools/
│   ├── build_index.py       # One-time cache builder
│   ├── query_feature.py     # arm-feat skill backend
│   ├── query_register.py    # arm-reg skill backend
│   ├── query_instruction.py # arm-instr skill backend
│   ├── query_search.py      # arm-search skill backend
│   └── eval_skill.py        # Correctness evaluation (51 tests)
├── cache/                   # Generated, gitignored
│   ├── manifest.json        # Source file hashes for staleness detection
│   ├── features.json        # All 361 features in one file
│   ├── registers/           # One JSON per register × state (1,607 files)
│   │   ├── SCTLR_EL1__AArch64.json
│   │   ├── DBGBCR_n_EL1__AArch64.json
│   │   └── ...
│   ├── operations/          # One JSON per operation_id (2,262 files)
│   │   ├── ADC.json
│   │   └── ...
│   └── registers_meta.json  # name→[{state, cache_key}] index
└── .claude/
    └── skills/
        ├── arm-feat.md
        ├── arm-reg.md
        ├── arm-instr.md
        └── arm-search.md
```

---

## Module Plan

### Module 1: `arm-reg` — Register Queries ✅

**Trigger:** User asks about a system register, its fields, bit layout, access method, or field values.
**Do NOT use for:** instruction behavior or architecture feature dependencies.

| Sub-command | What it returns |
|-------------|----------------|
| `arm-reg SCTLR_EL1` | All named fields: bit ranges, field types, allowed values |
| `arm-reg SCTLR_EL1 UCI` | Single field detail (bit position, value enumeration) |
| `arm-reg SCTLR_EL1 UCI --values` | All allowed values for a field and their meanings |
| `arm-reg --list EL1 [--state AArch64\|AArch32\|ext]` | Registers matching name pattern |
| `arm-reg SCTLR_EL1 --access` | All accessor types, encodings, and access permissions |

**AArch32 vs AArch64 disambiguation:** When a bare name matches multiple states, prefer AArch64
and note that AArch32 variants also exist. Require `--state AArch32` to explicitly select.

**Parameterized registers:** `arm-reg DBGBCR2_EL1` → normalizes digit to `<n>` for meta lookup,
loads the parameterized cache entry, notes the specific instance. Meta keys use `<n>` notation;
cache files use `_n_` in filenames.

---

### Module 2: `arm-instr` — Instruction Queries ✅

**Trigger:** User asks about an instruction's behavior, encoding, or assembly syntax.
**Do NOT use for:** register field layout or feature dependencies.

| Sub-command | What it returns |
|-------------|----------------|
| `arm-instr ADC` | Operation brief, title, all encoding variants (instruction names) |
| `arm-instr ADC --enc` | Encoding bit fields and widths for all ADC variants |
| `arm-instr ADC --op` | ASL pseudocode; truncated to 60 lines by default |
| `arm-instr ADC --op --full` | Full ASL pseudocode without truncation |
| `arm-instr --list ADD` | All operation_ids containing the pattern |

**Note on ASL:** In the BSD MRS release, all `decode` and `operation` fields are `null` /
`// Not specified`. Skills acknowledge this; real ASL is available in the licensed XML release
(see Part II, Phase EA).

**MRS/MSR ambiguity:**
- The MRS *instruction* encoding → `arm-instr MRS`
- The MRS encoding *for a specific register* (op0/CRn/CRm/op2) → `arm-reg SCTLR_EL1 --access`

---

### Module 3: `arm-feat` — Feature / Extension Queries ✅

**Trigger:** User asks about a `FEAT_*` extension, feature dependencies, or architecture versions.
**Do NOT use for:** register fields or instruction encodings.

| Sub-command | What it returns |
|-------------|----------------|
| `arm-feat FEAT_SVE` | Feature type, all constraint expressions (rendered AST) |
| `arm-feat FEAT_SVE --deps FEAT_FP16` | yes/conditional/no dependency answer + constraint tree |
| `arm-feat --version v9Ap2` | All features introduced at or before that version |
| `arm-feat --list SVE` | All `FEAT_*` names containing the pattern |

**`--version` algorithm:** Walk all per-feature and top-level constraints; find `-->` BinaryOp
nodes where one side is a version identifier; build `feature → min_version` map; filter using
known version ordering `v8Ap0 < v8Ap1 < … < v9Ap6`.

---

### Module 4: `arm-search` — Cross-cutting Search ✅

**Trigger:** User doesn't know which module to use, or wants to discover entities by keyword.

| Sub-command | What it returns |
|-------------|----------------|
| `arm-search TCR` | Matching registers and operation_ids |
| `arm-search --reg EL2 [--state AArch64]` | Registers whose name contains the pattern |
| `arm-search --op ADD` | operation_ids containing the pattern |

---

## Implementation Phases (Completed)

### Phase 0 — Bootstrap (`tools/build_index.py`) ✅
Parse source JSON → write per-entity cache files → write manifest with SHA-256 hashes.
Produces 1,607 register files, 2,262 operation files, features.json, registers_meta.json.

### Phase 1 — Query Scripts (`tools/`) ✅
Four Python CLI scripts. Accept primary key + flags. Load only the relevant cache file(s).
Print clear error on missing cache; print warning on stale cache; never auto-rebuild.

### Phase 2 — Skills (`.claude/skills/`) ✅
One skill file per module. Resolves repo root via `ARM_MRS_CACHE_DIR` env var or
`git rev-parse --show-toplevel`. Includes positive and negative routing examples.

---

## Key Design Decisions

### 1. Cache location
Default to in-repo `cache/` (gitignored). Support `ARM_MRS_CACHE_DIR` override for multi-project use.

### 2. Output format
Formatted text (not raw JSON) for interactive use. Uniform result envelope for `arm-search`.

### 3. Null descriptions
The BSD MRS omits all prose. Skills acknowledge this explicitly and never synthesize descriptions.

### 4. Instruction identity
`operation_id` is the universal key. Users discover valid IDs via `arm-instr --list`.

### 5. Skill granularity
Each skill file includes explicit positive triggers and negative examples to prevent misrouting.

### 6. Shared infrastructure
`check_staleness()` is currently duplicated across all query scripts. When Phase E0 adds a fifth
script, extract this into `tools/cache_utils.py` to eliminate the duplication.

---

# Part II — Extension Plan

## 1. Executive Summary

The current foundation covers A64 system registers, instructions, features, and search. A practical
firmware or driver developer also needs:

| Gap | Specification | Phase |
|-----|--------------|-------|
| CPU performance counter event names and codes | PMU Events (`ARM-software/data`) | **E0** |
| Full ASL pseudocode; T32/A32 ISA | ARM ARM (DDI0487) full MRS / proprietary | **EA** |
| Interrupt controller register programming | GIC (IHI0069) | **EB** |
| Debug / trace component register programming | CoreSight (IHI0029) | **EC** |

---

## 2. Data Availability Assessment

The fundamental constraint is **whether ARM publishes machine-readable data**. The current project
works because ARM distributes AARCHMRS as structured JSON under BSD 3-clause. Other specifications
require different ingestion strategies.

| Specification | Source | Format | License | Machine-Readable? |
|---|---|---|---|---|
| **AARCHMRS JSON** (current) | ARM Exploration Tools | JSON | BSD 3-clause | ✅ Native |
| **AARCHMRS XML** (full MRA) | ARM Exploration Tools | XML | Architecture license required | ⚠️ Restricted |
| **PMU Events** (`ARM-software/data`) | GitHub | JSON | Apache 2.0 | ✅ Native |
| **GIC** (IHI0069) | developer.arm.com | PDF / HTML | Proprietary | ❌ HTML extractable |
| **CoreSight** (IHI0029) | developer.arm.com | PDF / HTML | Proprietary | ❌ HTML extractable |

**Key findings:**

1. **PMU Events** (`ARM-software/data`) is the only other immediately actionable, redistributable
   ARM dataset. ~40+ CPU JSON files with real prose descriptions — unlike the BSD AARCHMRS, the
   `PublicDescription` fields are populated. Apache 2.0 license.

2. **The AARCHMRS JSON is already the DDI0487 machine-readable form.** "Adding the ARM ARM" means
   either accessing the licensed XML release (which has ASL pseudocode) or adding T32/A32 ISA
   coverage. These are two separate sub-tasks.

3. **AARCHMRS XML** is the same underlying specification, but the XML release distributed to
   architecture licensees includes full ASL pseudocode for all instructions. This is what Sail and
   ARM's formal verification tooling are built on. It would fill the `// Not specified` gaps across
   all 2,262 A64 operation files — and the T32/A32 operation files added by Phase EA.

4. **GIC and CoreSight have no machine-readable release.** ARM has never published these as
   JSON or XML. They exist only as PDF/HTML. Any ingestion requires a custom extractor. The data
   is proprietary and must not be committed to a public repository or redistributed.

---

## 3. Repository Structure (After Extension)

```
arm-mrs-2025-03-aarchmrs/
├── Features.json              # Existing — AARCHMRS A64 features
├── Instructions.json          # Existing — AARCHMRS A64 instructions
├── Registers.json             # Existing — AARCHMRS system registers
│
├── gic/                       # NEW (Phase EB) — GIC source data (committed)
│   ├── GIC.json               # Hand-curated or extracted register data
│   ├── GIC_meta.json          # Version/build metadata
│   └── schema/
│       ├── GicRegister.json
│       ├── GicField.json
│       └── GicInterruptMap.json
│
├── coresight/                 # NEW (Phase EC) — CoreSight source data (committed)
│   ├── CoreSight.json         # Hand-curated or extracted component register data
│   ├── CoreSight_meta.json    # Version/build metadata
│   └── schema/
│       ├── CsComponent.json
│       ├── CsRegister.json
│       └── CsField.json
│
├── arm-arm/                   # NEW (Phase EA) — ARM ARM additions
│   ├── T32Instructions.json   # T32 (Thumb-2) instruction encodings
│   ├── A32Instructions.json   # A32 (ARM 32-bit) instruction encodings
│   └── schema/                # Reuse existing schema/Instruction/
│
├── schema/                    # Existing + new peripheral types
│   └── Peripheral/            # NEW
│       ├── PeripheralRegister.json
│       └── PeripheralField.json
│
├── tools/
│   ├── build_index.py         # Extended to index all AARCHMRS data
│   ├── build_pmu_index.py     # NEW (E0) — PMU event cache builder
│   ├── build_gic_index.py     # NEW (EB) — GIC cache builder
│   ├── build_coresight_index.py # NEW (EC) — CoreSight cache builder
│   ├── build_arm_arm_index.py # NEW (EA) — T32/A32 cache builder
│   ├── convert_xml_to_json.py # NEW — converts ARM XML/SVD releases to project schema
│   ├── cache_utils.py         # NEW — shared check_staleness(), load_manifest(), etc.
│   ├── query_feature.py       # Existing
│   ├── query_register.py      # Existing
│   ├── query_instruction.py   # Extended (EA) — add --isa t32|a32 flag
│   ├── query_search.py        # Extended (EB/EC) — add --spec flag, new result types
│   ├── query_pmu.py           # NEW (E0) — PMU event queries
│   ├── query_gic.py           # NEW (EB) — GIC register queries
│   ├── query_coresight.py     # NEW (EC) — CoreSight component queries
│   └── eval_skill.py          # Extended with new skill test cases
│
├── cache/                     # Generated, gitignored — all caches
│   ├── manifest.json          # Extended with new source hashes
│   ├── features.json          # Existing
│   ├── registers/             # Existing
│   ├── operations/            # Existing
│   ├── arm_arm/               # NEW (EA)
│   │   ├── t32_operations/
│   │   └── a32_operations/
│   ├── pmu/                   # NEW (E0) — one JSON per CPU
│   │   ├── cortex-a710.json
│   │   ├── neoverse-n2.json
│   │   └── ...
│   ├── pmu_meta.json          # NEW (E0) — cpu_name → { file, event_count }
│   ├── pmu_events_flat.json   # NEW (E0) — cross-CPU search index
│   ├── gic/                   # NEW (EB) — gitignored (proprietary)
│   │   ├── GICD.json
│   │   ├── GICR.json
│   │   ├── GITS.json
│   │   └── gic_meta.json
│   └── coresight/             # NEW (EC) — gitignored (proprietary)
│       ├── etm/TRCPRGCTLR.json
│       ├── cti/CTICONTROL.json
│       └── cs_meta.json
│
└── .claude/skills/
    ├── arm-feat.md            # Existing
    ├── arm-reg.md             # Existing — add ICC_* vs GICD/GICR routing note
    ├── arm-instr.md           # Existing — add T32/A32 routing once EA is done
    ├── arm-search.md          # Existing — extend for multi-spec search
    ├── arm-pmu.md             # NEW (E0)
    ├── arm-gic.md             # NEW (EB)
    └── arm-coresight.md       # NEW (EC)
```

---

## 4. New Data Schema Design

### 4.1 GIC Register Schema

GIC registers are memory-mapped peripheral registers, not CPU system registers. Key differences
from `Registers.json`:

| AARCHMRS `Registers.json` | GIC `gic/GIC.json` |
|--------------------------|-------------------|
| `state`: AArch64/AArch32/ext | No state — memory-mapped |
| `accessors` with op0/CRn/CRm | `offset` in component address space |
| AST `condition` for feature guard | `gic_version` minimum version field |
| `fieldsets[].condition` | `variants[]` for GICv3-vs-GICv4 layouts |

**`gic/GIC.json` top-level structure:**
```json
{
  "_meta": {
    "spec": "GIC",
    "doc_id": "IHI0069H",
    "version": "GICv3/v4",
    "build_date": "ISO 8601 timestamp"
  },
  "components": {
    "GICD": { "description": "Distributor", "registers": [...] },
    "GICR": { "description": "Redistributor", "registers": [...] },
    "GITS": { "description": "ITS", "registers": [...] }
  },
  "icc_system_registers": [
    {
      "name": "ICC_IAR1_EL1",
      "aarchmrs_ref": "ICC_IAR1_EL1__AArch64",
      "note": "Full definition in AARCHMRS Registers.json; cross-reference only"
    }
  ]
}
```

**`cache/gic/GICD.json` register entry example:**
```json
{
  "name": "GICD_CTLR",
  "block": "GICD",
  "offset": "0x0000",
  "width": 32,
  "description": "Distributor Control Register",
  "access": "RW",
  "fields": [
    {
      "name": "EnableGrp1S",
      "bits": [{"start": 2, "width": 1}],
      "access": "RW",
      "reset": "0",
      "description": "Enable Secure Group 1 interrupts"
    },
    {
      "name": "EnableGrp1NS",
      "bits": [{"start": 1, "width": 1}],
      "access": "RW",
      "reset": "0",
      "description": "Enable Non-secure Group 1 interrupts"
    },
    {
      "name": "EnableGrp0",
      "bits": [{"start": 0, "width": 1}],
      "access": "RW",
      "reset": "0",
      "description": "Enable Group 0 interrupts"
    }
  ]
}
```

### 4.2 CoreSight Register Schema

CoreSight components share a common identification block (32 registers at the top of every 4 KB
component frame). The schema adds a `component_type` discriminator.

**`coresight/CoreSight.json` top-level structure:**
```json
{
  "_meta": {
    "spec": "CoreSight",
    "doc_id": "IHI0029F",
    "version": "v3.0",
    "build_date": "ISO 8601 timestamp"
  },
  "common_identification_block": {
    "description": "32 word-aligned 32-bit registers at the top of each 4 KB component frame",
    "registers": [...]
  },
  "components": {
    "ETM": { "arch_id": "0x4A13", "description": "Embedded Trace Macrocell", "registers": [...] },
    "CTI": { "arch_id": "0x1A14", "description": "Cross-Trigger Interface", "registers": [...] },
    "STM": { "arch_id": "0x0A63", "description": "System Trace Macrocell", "registers": [...] },
    "ITM": { "arch_id": "0x1A01", "description": "Instrumentation Trace Macrocell", "registers": [...] },
    "ROM": { "description": "ROM Table", "registers": [...] }
  }
}
```

**`cache/coresight/etm/TRCPRGCTLR.json` example:**
```json
{
  "name": "TRCPRGCTLR",
  "component": "ETM",
  "offset": "0x004",
  "description": "Programming Control Register",
  "access": "RW",
  "fields": [
    {"name": "EN", "bits": [{"start": 0, "width": 1}], "description": "Trace enable"}
  ]
}
```

### 4.3 ARM ARM Extension Schema (T32 / A32)

T32 and A32 instructions use the **same** `schema/Instruction/` already defined. The only
addition is an `"isa"` field at the top level of each operation cache file (`"isa": "T32"` or
`"isa": "A32"`) and separate `cache/arm_arm/t32_operations/` and `cache/arm_arm/a32_operations/`
directories. No schema changes are required.

---

## 5. Extension Phases

### Phase E0 — PMU Events (`arm-pmu` skill)

**Source:** `https://github.com/ARM-software/data` (pmu/ directory)
**License:** Apache 2.0 — redistributable; cache may be committed if desired
**Effort:** Low — native JSON, same patterns as existing skills
**Blocker:** None — start immediately

#### What's available

`ARM-software/data` publishes ~40+ CPU-specific PMU event JSON files, one per microarchitecture
(Cortex-A710, Cortex-A715, Neoverse N2, Neoverse V2, etc.). Each file contains:
- `ArchitectureName`: event name (e.g., `CPU_CYCLES`, `L1D_CACHE_REFILL`)
- `Code`: hex event number written to `PMEVTYPER<n>` (e.g., `"0x0011"`)
- `PublicDescription`: human-readable prose — **this data has real descriptions**
- `Type`: Required / Recommended / Implementation-defined
- Applicable privilege levels, unit

Unlike the BSD AARCHMRS, the description fields are reliably populated. This is the only other
natively machine-readable, Apache-licensed ARM dataset available outside the current project.

#### Steps

| Step | Task |
|------|------|
| E0-1 | Probe `ARM-software/data/pmu/` — confirm field names, measure coverage, identify any null description fields, document schema |
| E0-2 | Write `tools/build_pmu_index.py`: reads all `pmu/*.json` from a cloned/downloaded snapshot; writes `cache/pmu/<cpu>.json` per CPU; writes `cache/pmu_meta.json` (cpu_name → {file, event_count}); writes `cache/pmu_events_flat.json` (flat list for cross-CPU search); updates `cache/manifest.json` with PMU source commit SHA |
| E0-3 | Extract shared staleness check and manifest handling to `tools/cache_utils.py`; update all existing query scripts to import from it |
| E0-4 | Write `tools/query_pmu.py`: `query_pmu.py cortex-a710` (all events), `query_pmu.py cortex-a710 CPU_CYCLES` (single event), `query_pmu.py --search L1D_CACHE` (cross-CPU), `query_pmu.py --list` (all CPUs) |
| E0-5 | Write `.claude/skills/arm-pmu.md`: positive triggers (PMU event codes, PMEVTYPER programming); negative examples (PMCCNTR_EL0 → `arm-reg`; instruction throughput — not in spec) |
| E0-6 | Extend `eval_skill.py` with `pmu` test cases: CPU existence, `CPU_CYCLES` code correctness for Cortex-A710, cross-CPU event search, hallucination guard |

**Exit criteria:** `python3 tools/query_pmu.py cortex-a710 CPU_CYCLES` returns the event code
and description grounded in ARM-official data.

---

### Phase EA — ARM ARM Extension (ASL Unlock + T32/A32)

**Source:** ARM proprietary MRS package (architecture license required); or PDF for hand-curation
**License:** ARM proprietary — data NOT redistributable
**Effort:** Medium (if licensed) or High (if hand-curated from PDF)
**Blocker:** Architecture license decision

This phase has two sub-parts that depend on the same licensing gate:

#### EA-a: ASL Pseudocode Unlock (enriches existing A64 skills)

The licensed XML release of AARCHMRS contains full ASL pseudocode for all instructions —
the same operations whose `decode` and `operation` fields are `null` / `// Not specified` in
the current BSD JSON. Unlocking ASL makes `arm-instr --op` actually useful.

| Step | Task |
|------|------|
| EA-a-1 | **License gate:** Determine whether an ARM Architecture License is available. If yes, download the XML MRA package. If no, skip to EA-b (T32/A32 PDF path). |
| EA-a-2 | Probe the XML release: map XML field paths to JSON cache schema fields; identify where `decode` and `operation` bodies live; assess completeness |
| EA-a-3 | Extend `tools/build_index.py` with optional `--xml-dir` argument: when supplied, merge ASL pseudocode and prose descriptions into existing `cache/operations/*.json` and `cache/registers/*.json` files; preserve the JSON-only path for users without the XML release |
| EA-a-4 | Update skill files: remove "not available in BSD MRS release" disclaimers where data is now present; `arm-instr --op` now returns real ASL |
| EA-a-5 | Add conditional eval tests: skip if `--xml-dir` was not provided; pass if real pseudocode content is present |

#### EA-b: T32/A32 ISA Coverage (new ISA in `arm-instr`)

T32 (Thumb-2) and A32 (32-bit ARM) instruction sets are absent from the current A64-only
AARCHMRS. This sub-phase adds them under the same `arm-instr` skill via a new `--isa` flag.

| Step | Task |
|------|------|
| EA-b-1 | If the licensed MRS package is available: parse T32/A32 directly from it using the existing `schema/Instruction/` schema. If unavailable: hand-curate `arm-arm/T32Instructions.json` and `arm-arm/A32Instructions.json` from the PDF. |
| EA-b-2 | Write `tools/build_arm_arm_index.py`: reads from the source (licensed JSON or hand-curated files); writes `cache/arm_arm/t32_operations/` and `cache/arm_arm/a32_operations/` in the same per-operation_id format as `cache/operations/` |
| EA-b-3 | Extend `tools/query_instruction.py` with `--isa t32\|a32\|a64` flag (default `a64` for backward compatibility) |
| EA-b-4 | Extend `.claude/skills/arm-instr.md` to document T32/A32 routing |
| EA-b-5 | Extend `tools/query_search.py` to search T32/A32 operation indexes |
| EA-b-6 | Update `cache/manifest.json` schema to include T32/A32 source hashes |

**Deliverables:** `arm-instr --isa t32 LDR`, `arm-instr --isa a32 LDR --enc`

**Exit criteria:** `arm-instr --isa t32 LDR` returns correct T32 encoding and (if licensed) real
ASL pseudocode without loading the full T32Instructions.json into context.

---

### Phase EB — GIC Extension (`arm-gic` skill)

**Source:** `https://developer.arm.com/documentation/ihi0069/latest/` (HTML)
**License:** Proprietary — NOT redistributable; `cache/gic/` must be gitignored; `gic/GIC.json`
source file may be committed as a documentation-derived summary (consult ARM Developer Relations
re: fair use before publishing)
**Effort:** High
**Blocker:** HTML extractability confirmation; XML/SVD source check

#### Phase EB-0 — Data Acquisition

| Step | Task |
|------|------|
| EB-0-1 | **Check for XML/SVD source first:** search `https://github.com/ARM-software/CMSIS_5` and community IP-XACT repositories for a machine-readable GIC description. If found with adequate field-level coverage (field names, widths, access types), use `tools/convert_xml_to_json.py` (see EB-0-2x) and skip the HTML/PDF path. |
| EB-0-2x *(XML path)* | Write `tools/convert_xml_to_json.py`: converts CMSIS-SVD or IP-XACT XML to the project's GIC JSON schema. Validate output against `gic/schema/`. |
| EB-0-2 *(HTML/PDF path)* | **Confirm static HTML:** fetch a sample GIC register page from developer.arm.com and verify register tables are present in static HTML (not JavaScript-rendered). ARM uses a CDN that can serve JS-dependent pages — confirm parseable without a headless browser before committing to this approach. |
| EB-0-3 *(HTML path)* | Write `tools/fetch_gic.py`: downloads GIC spec HTML pages; parses register tables using `html.parser` (stdlib); rate-limits requests to avoid hammering the CDN. Writes per-register JSON to a staging directory. |
| EB-0-4 | Extract GICD, GICR, and ITS registers from staging; document GICv3-vs-GICv4 field variants |
| EB-0-5 | Note: `ICC_*` system registers (e.g., `ICC_IAR1_EL1`) already exist in AARCHMRS `Registers.json`. Document cross-references in `gic/GIC.json` `icc_system_registers` array; do NOT duplicate data. |
| EB-0-6 | Produce `gic/GIC.json` and `gic/GIC_meta.json`; define and validate against `gic/schema/` |

#### Phase EB-1 — Cache Builder

| Step | Task |
|------|------|
| EB-1-1 | Write `tools/build_gic_index.py`: reads `gic/GIC.json`; writes per-component cache files `cache/gic/GICD.json`, `cache/gic/GICR.json`, `cache/gic/GITS.json` and `cache/gic/gic_meta.json` |
| EB-1-2 | Extend `cache/manifest.json` with SHA-256 of `gic/GIC.json` |
| EB-1-3 | Add `cache/gic/` to `.gitignore` |

#### Phase EB-2 — Query Tool

| Step | Task |
|------|------|
| EB-2-1 | Write `tools/query_gic.py` with sub-commands (see §6.1) |
| EB-2-2 | On missing cache: `Cache not found. Run: python3 tools/build_gic_index.py` |

#### Phase EB-3 — Agent Skill

| Step | Task |
|------|------|
| EB-3-1 | Write `.claude/skills/arm-gic.md` |
| EB-3-2 | Positive triggers: interrupt controller registers, GICD/GICR/ITS programming, GIC initialization, LPI/MSI configuration, vGIC virtualization |
| EB-3-3 | Negative examples: `ICC_*` system registers → `arm-reg`; CPU interrupt pending state → `arm-reg` |
| EB-3-4 | Document ICC_* cross-reference: when user asks about `ICC_IAR1_EL1`, route to `arm-reg`, not `arm-gic` |

#### Phase EB-4 — Search Integration

| Step | Task |
|------|------|
| EB-4-1 | Extend `tools/query_search.py`: add `--spec gic` filter; add GIC register names to default combined search results |
| EB-4-2 | Add `"gic_register"` result type to search output |
| EB-4-3 | Extend `.claude/skills/arm-search.md` to route GIC results to `arm-gic` |

**Exit criteria:** `python3 tools/query_gic.py GICD_CTLR EnableGrp0` returns field layout and
description. `arm-search EnableGrp1` returns GIC register results.

---

### Phase EC — CoreSight Extension (`arm-coresight` skill)

**Source:** `https://developer.arm.com/documentation/ihi0029/latest/` (HTML)
**License:** Proprietary — NOT redistributable; `cache/coresight/` must be gitignored
**Effort:** Very high — complex component hierarchy; same HTML extraction caveat as Phase EB
**Blocker:** Phase EB HTML extraction validation; XML/SVD source check

CoreSight is more complex than GIC because:
1. Registers are organized by **component type** — the same name (`CTICONTROL`) may appear in
   multiple components with different semantics
2. Some registers are defined once at the architecture level and appear in many components
3. The common identification block (32 registers per 4 KB frame) must be factored out

#### Phase EC-0 — Data Acquisition

| Step | Task |
|------|------|
| EC-0-1 | Check for IP-XACT or SVD community sources for CoreSight component registers. If found, use `tools/convert_xml_to_json.py`. If not, confirm static HTML as in EB-0-2. |
| EC-0-2 | Write `tools/fetch_coresight.py` (if HTML path): downloads CoreSight spec HTML; parses per-component register tables |
| EC-0-3 | Extract the **common identification block** registers (shared across all components) separately from component-specific registers |
| EC-0-4 | Determine component priority: **ETM > CTI > STM > ITM** for initial release |
| EC-0-5 | Produce `coresight/CoreSight.json` and `coresight/CoreSight_meta.json`; define and validate against `coresight/schema/` |

#### Phase EC-1 — Cache Builder

Write `tools/build_coresight_index.py`: reads `coresight/CoreSight.json`; writes per-component
cache files under `cache/coresight/<component>/` and `cache/coresight/cs_meta.json`; extends
`cache/manifest.json`.

#### Phase EC-2 — Query Tool

Write `tools/query_coresight.py` with sub-commands (see §6.2).

#### Phase EC-3 — Agent Skill

Write `.claude/skills/arm-coresight.md`:
- Positive triggers: debug infrastructure, ETM programming, trace enabling, CTI channel routing,
  ITM stimulus ports, STM trace, ROM table, `TRCPRGCTLR`/`TRCCONFIGR` registers
- Negative examples: CPU halt via `MDSCR_EL1` → `arm-reg`; JTAG protocol → out of scope

#### Phase EC-4 — Search Integration

Extend `tools/query_search.py`: add `--spec coresight` filter; add `"cs_register"` result type;
extend `.claude/skills/arm-search.md`.

**Exit criteria:** `python3 tools/query_coresight.py etm TRCPRGCTLR` returns field layout.
`arm-search TRC` returns CoreSight ETM register results.

---

### Phase EX — Integration, Evaluation, and Hardening ✅

**Depends on:** Phase E0 + Phase EA + Phase EB-3 + Phase EC-3

| Step | Task | Status |
|------|------|--------|
| EX-1 | Add `CROSS_ROUTING_TESTS` to `eval_skill.py`: ICC_PMR_EL1 via `arm-reg`, GICD_CTLR as ext-state in AARCHMRS, `arm-gic --icc-xref` routing, combined search spanning AARCHMRS + GIC | ✅ Done |
| EX-2 | Extend `query_search.py --spec` with `aarchmrs` and `pmu`; add `SEARCH_SPEC_AARCHMRS_TESTS` and `SEARCH_SPEC_PMU_TESTS` to `eval_skill.py`; add `search_pmu_events()` function | ✅ Done |
| EX-3 | Run full eval suite across all six skills; all 137 tests pass (100%); no regressions | ✅ Done |
| EX-4 | Update `README.md` (full tool documentation), `CLAUDE.md` (corrected eval count + new skill examples), `AARCH64_AGENT_SKILL_DEV_PLAN.md` (deviations table), `ROADMAP.md` (status) | ✅ Done |

**Note on EX-1 cross-routing finding:** GICD_CTLR IS present in AARCHMRS `Registers.json` as an
`ext`-state (memory-mapped) register. The `arm-gic` skill provides the GIC-specific field view
and routing. Both tools are complementary, not exclusive.

---

## 6. New Query Tool APIs

### 6.1 `tools/query_gic.py`

```
# Show all fields of a GIC register
python3 query_gic.py GICD_CTLR

# Show a single field
python3 query_gic.py GICD_CTLR EnableGrp1S

# Show all registers for a component block
python3 query_gic.py --block GICD
python3 query_gic.py --block GICR
python3 query_gic.py --block GITS

# List register names matching a pattern
python3 query_gic.py --list CTLR

# Show GICv3 vs GICv4 field variants for a register
python3 query_gic.py GICD_CTLR --version v3
python3 query_gic.py GICD_CTLR --version v4

# Cross-reference: show which AARCHMRS system register corresponds to ICC_IAR1_EL1
python3 query_gic.py --icc-xref ICC_IAR1_EL1
```

### 6.2 `tools/query_coresight.py`

```
# Show all fields of a CoreSight component register
python3 query_coresight.py etm TRCPRGCTLR

# Show a single field
python3 query_coresight.py etm TRCPRGCTLR EN

# Show all registers for a component
python3 query_coresight.py --component etm
python3 query_coresight.py --component cti

# List all known CoreSight component types
python3 query_coresight.py --list-components

# List register names matching a pattern across all components
python3 query_coresight.py --list CTRL

# Show the common identification block registers
python3 query_coresight.py --id-block
```

### 6.3 Extensions to `tools/query_instruction.py`

```
# T32 instruction query (new --isa flag; default a64 is backward-compatible)
python3 query_instruction.py LDR --isa t32
python3 query_instruction.py LDR --isa t32 --enc
python3 query_instruction.py LDR --isa a32
python3 query_instruction.py --list MOV --isa t32
python3 query_instruction.py ADC                 # unchanged: same as --isa a64
```

### 6.4 Extensions to `tools/query_search.py`

```
# Spec-filtered search
python3 query_search.py --spec gic EnableGrp
python3 query_search.py --spec coresight TRC
python3 query_search.py --spec aarchmrs TCR

# Default: search all specs
python3 query_search.py CTRL
```

### 6.5 `tools/query_pmu.py`

```
# All events for a CPU
python3 query_pmu.py cortex-a710

# Single event detail
python3 query_pmu.py cortex-a710 CPU_CYCLES

# Cross-CPU event search
python3 query_pmu.py --search L1D_CACHE

# List all CPUs with event counts
python3 query_pmu.py --list
```

---

## 7. New Agent Skills

### 7.1 `arm-pmu` — PMU Event Queries

**Trigger:** User asks about performance counter event names, event codes for PMEVTYPER, or
which PMU events are available on a specific CPU.

**Do NOT use for:** PMCCNTR_EL0 programming → `arm-reg PMCCNTR_EL0`; instruction latency /
throughput (not in spec data).

**Note:** Unlike AARCHMRS, PMU event descriptions ARE available in this data.

| Sub-command | What it returns |
|-------------|----------------|
| `arm-pmu cortex-a710` | All events with codes and truncated descriptions |
| `arm-pmu cortex-a710 CPU_CYCLES` | Full detail: code, description, type, privilege |
| `arm-pmu --search L1D_CACHE` | All CPUs that have matching events |
| `arm-pmu --list` | All CPUs with event counts |

### 7.2 `arm-gic` — GIC Register and Interrupt Model Queries

**Trigger:** User asks about interrupt controller registers, interrupt programming, GICD/GICR/ITS
registers, GIC initialization, LPI/MSI configuration, or vGIC virtualization.

**Do NOT use for:** `ICC_*` system registers (e.g., `ICC_IAR1_EL1`) → `arm-reg` (in AARCHMRS).

| Sub-command | What it returns |
|-------------|----------------|
| `arm-gic GICD_CTLR` | All fields with bit ranges, access types, reset values |
| `arm-gic GICD_CTLR EnableGrp1S` | Single field detail |
| `arm-gic --block GICD` | All Distributor registers |
| `arm-gic --list ENABL` | Register names matching pattern |
| `arm-gic --icc-xref ICC_IAR1_EL1` | Cross-reference to AARCHMRS system register |

### 7.3 `arm-coresight` — CoreSight Component Queries

**Trigger:** User asks about debug infrastructure, ETM programming, trace enabling, CTI channel
routing, ITM stimulus ports, STM trace, ROM table parsing, or `TRCPRGCTLR`/`TRCCONFIGR`.

**Do NOT use for:** CPU halt/debug via `MDSCR_EL1` → `arm-reg`; JTAG protocol → out of scope.

| Sub-command | What it returns |
|-------------|----------------|
| `arm-coresight etm TRCPRGCTLR` | Field layout and access type |
| `arm-coresight cti CTICONTROL` | CTI register detail |
| `arm-coresight --component etm` | All ETM registers |
| `arm-coresight --list-components` | All CoreSight component types |
| `arm-coresight --id-block` | Common identification register block |

---

## 8. Complete Skill Routing Summary

| User Query | Primary Skill | Notes |
|-----------|---------------|-------|
| "What fields does SCTLR_EL1 have?" | `arm-reg` | Existing |
| "What is bit 26 (UCI) of SCTLR_EL1?" | `arm-reg` | Existing |
| "How do I read SCTLR_EL1 from EL1?" | `arm-reg --access` | Existing |
| "What op0/CRn/CRm selects TCR_EL2?" | `arm-reg --access` | Existing |
| "Does FEAT_SVE require FEAT_FP16?" | `arm-feat` | Existing |
| "What features does ARMv9.2 add?" | `arm-feat --version` | Existing |
| "What does the ADC instruction do?" | `arm-instr` | Existing |
| "Show me the T32 LDR encoding" | `arm-instr --isa t32` | Phase EA |
| "Find all EL2 registers" | `arm-search` | Existing |
| "Find anything named CTRL" | `arm-search` | Searches all specs (Phase EB/EC) |
| "What PMU events does Cortex-A710 have?" | `arm-pmu` | Phase E0 |
| "What code does CPU_CYCLES use on Neoverse N2?" | `arm-pmu` | Phase E0 |
| "How do I acknowledge an interrupt?" | `arm-gic` + `arm-reg` | GICD_CTLR flow + ICC_IAR1_EL1 |
| "What does GICD_CTLR.EnableGrp1 mean?" | `arm-gic` | Phase EB |
| "What is ICC_IAR1_EL1?" | `arm-reg` | ICC_* is in AARCHMRS |
| "How do I enable ETM tracing?" | `arm-coresight` | Phase EC |
| "What does TRCPRGCTLR.EN do?" | `arm-coresight` | Phase EC |

---

## 9. Implementation Priority

| Phase | Skill | Value | Effort | Blocker |
|---|---|---|---|---|
| **E0** | `arm-pmu` | High | Low | None — start immediately |
| **EA-a** | ASL unlock | Very high | Medium | Architecture license |
| **EA-b** | T32/A32 ISA | High | Medium–High | Architecture license (or PDF) |
| **EB** | `arm-gic` | High | High | HTML confirmation; SVD check |
| **EC** | `arm-coresight` | Medium | Very high | Phase EB validation |

**Recommended sequence:** E0 → EB-0 probe (parallel) → EA (if licensed) → EB full → EC

---

## 10. Dependency Graph

```
Phase E0 (PMU Events)
  ├── No dependency on EA/EB/EC
  └── Enables: arm-pmu skill + cache_utils.py refactor

Phase EA (ARM ARM / ASL + T32/A32)
  ├── EA-a (ASL unlock) → depends on architecture license decision
  ├── EA-b (T32/A32) → depends on EA-a license gate (or PDF fallback)
  └── Enables: arm-instr --isa t32|a32; real pseudocode in arm-instr --op

Phase EB (GIC)
  ├── EB-0 (Data) → EB-1 (Cache) → EB-2 (Query) → EB-3 (Skill) → EB-4 (Search)
  ├── EB-3 depends on: existing arm-reg skill (for ICC_* cross-ref routing)
  └── Enables: complete interrupt controller programming workflow

Phase EC (CoreSight)
  ├── EC-0 (Data) → EC-1 (Cache) → EC-2 (Query) → EC-3 (Skill) → EC-4 (Search)
  ├── No hard dependency on Phase EB (can be developed in parallel)
  └── Enables: complete debug infrastructure programming workflow

Phase EX (Integration)
  └── Depends on: E0 complete + EA complete + EB-3 complete + EC-3 complete
```

Phases E0, EA, EB, and EC can be started independently after the data acquisition decisions are
made. Phase EX requires all of them.

---

## 11. Licensing Considerations

| Specification | License | Action Required |
|--------------|---------|----------------|
| AARCHMRS JSON (current) | BSD 3-clause | Already compliant |
| PMU Events (ARM-software/data) | Apache 2.0 | May commit cache if desired |
| ARM ARM (DDI0487) XML MRS | ARM proprietary | Evaluate before ingesting; may require private repo |
| ARM ARM PDF | Free download, no redistribution | Do not commit PDF |
| GIC (IHI0069) HTML/PDF | Proprietary | Do not commit PDF; treat curated JSON as a documentation-derived summary — consult ARM Developer Relations before publishing |
| CoreSight (IHI0029) HTML/PDF | Proprietary | Same as GIC |

**Recommended approach for GIC and CoreSight `gic/GIC.json` / `coresight/CoreSight.json`:**
Treat these as documentation-derived summaries rather than verbatim extracts. Include the IHI
document number and version as attribution in the `_meta` field. Cache files (`cache/gic/`,
`cache/coresight/`) must be gitignored in all cases.

For the ARM ARM MRS XML package: if the proprietary license permits internal tool use but not
redistribution, keep the raw XML in a separate private directory pointed to by `--xml-dir`, and
commit only the schema extensions and query tool changes.

---

## 12. Not in Scope

| Candidate | Reason to skip |
|---|---|
| SMMU (IHI0070) | Closely related to GIC/CoreSight; large enough to be its own future project after Phase EB/EC |
| GICv5 (in development) | Spec not yet finalized; plan targets GICv3/v4 (IHI0069H) |
| CMSIS-SVD microcontroller files | Microcontroller peripherals, not ARM system architecture |
| Linux kernel device tree bindings | Linux device model, not the ARM spec |
| TrustZone / TF-A registers | Already defined within AARCHMRS `Registers.json` |
| AMBA bus protocol (APB, AXI) | No register-level spec; signal-level only |
| ARM Compiler documentation | Tool documentation, not hardware spec |
| CoreSight SoC-specific variants | Only architecture-defined register set from IHI0029; vendor ETM variants excluded |
| Auto-rebuild inside skill invocations | Too slow for interactive use; cache must be pre-built |
| Third-party Python dependencies | All tools remain stdlib-only (Python 3.8+) |
| Prose synthesis | Skills must never synthesize descriptions; emit "Description not available" for null fields |

---

## 13. Open Questions Before Starting

1. **Phase E0 (PMU):** Which CPUs in `ARM-software/data` are in scope? The repo includes ~40+
   CPUs from Cortex-A53 to Neoverse V3. Should the cache include all, or a curated subset (e.g.,
   only CPUs with stable, complete event lists)?

2. **Phase EA:** Does an ARM Architecture License exist in this context? If yes, what format is
   the XML download — does it include the full `aarch64.xml` / `aarch32.xml` hierarchy?

3. **Phase EB/EC (HTML):** ARM's documentation is served via a CDN. Confirm that register tables
   are present in static HTML — parseable without a headless browser — before committing to the
   extraction approach. Check this for a sample GICD_CTLR page before starting EB-0-3.

4. **Phase EB/EC (XML):** Does `https://github.com/ARM-software/CMSIS_5` provide adequate
   field-level coverage for GIC and CoreSight (field names, widths, access types, reset values)?
   Evaluate before committing to the HTML extraction path.

5. **Schema versioning:** Should the new GIC/CoreSight schemas reuse `schema/Meta.json` with
   a new `spec_id` field, or define a separate versioning namespace? Recommended: reuse
   `schema/Meta.json` with `spec_id` to maintain consistency.

6. **Cache storage:** PMU adds ~50 files (~5 MB). GIC/CoreSight would add ~300+ files (~30 MB).
   These fit comfortably in the existing `cache/` structure.
