# EXTEND_DEV_PLAN.md — Extending the ARM Specification Repository

This document is the development plan for adding three additional ARM specifications
to this repository alongside the existing A-profile Machine Readable Specification
(AARCHMRS v9Ap6-A, Build 445):

1. **GIC** — Generic Interrupt Controller Architecture Specification (IHI0069)
2. **CoreSight** — CoreSight Architecture Specification (IHI0029)
3. **ARM ARM** — Architecture Reference Manual for A-profile (DDI0487)

---

## 1. Executive Summary

The current repository provides A-profile instruction encodings, system registers, and
architecture features in machine-readable JSON. A practical firmware or driver developer
also needs:

| Gap | Specification |
|-----|--------------|
| Interrupt controller register programming | GIC (IHI0069) |
| Debug / trace component register programming | CoreSight (IHI0029) |
| Prose descriptions, T32/A32 ISA, memory model, exception model | ARM ARM (DDI0487) |

Each specification has different data-availability characteristics that determine how
the data must be acquired and the level of effort required.

---

## 2. Specifications Overview

### 2.1 GIC — IHI0069 (GICv3/v4)

**What it covers:**
- Memory-mapped Distributor registers (`GICD_*`) — SPI routing and control
- Memory-mapped Redistributor registers (`GICR_*`) — per-PE SGI/PPI/LPI control
- CPU Interface system registers (`ICC_*`) accessible via MSR/MRS (GICv3+)
- ITS (Interrupt Translation Service) registers for LPI/MSI routing
- GICv4 virtual interrupt handling (`GITS_BASER`, `GICV_*`)

**Relationship to existing AARCHMRS:**
The `ICC_*` system registers (e.g., `ICC_IAR1_EL1`, `ICC_PMR_EL1`) already exist in
`Registers.json` because they are AArch64 system registers. The GIC extension adds the
**memory-mapped peripheral registers** (GICD, GICR, ITS) that are not CPU registers and
therefore absent from the current AARCHMRS. This extension also provides the
interrupt programming model that links ICC system registers to GICD/GICR operation.

**Latest public release:** IHI0069H (GICv3/v4, including GICv4.1 for direct vLPI injection)

**Data availability:** Arm does not publish an official machine-readable JSON or XML
release for IHI0069. However, before resorting to PDF extraction, check whether an XML
source exists via community projects (e.g., CMSIS-SVD at
`https://github.com/ARM-software/CMSIS_5`, IP-XACT distributions) — an XML source is
significantly easier to parse reliably than a PDF. If no XML source is found, the
register tables must be extracted from the PDF and encoded into structured JSON as part
of this project.

### 2.2 CoreSight — IHI0029

**What it covers:**
- Debug APB bus registers
- Embedded Trace Macrocell (ETM) registers
- Program Trace Macrocell (PTM) registers
- System Trace Macrocell (STM) registers
- Instrumentation Trace Macrocell (ITM) registers
- Cross-Trigger Interface (CTI) registers
- Embedded Cross-Trigger (ECT) registers
- ROM Table structure and component identification registers
- Trace Bus Protocol registers (ATB)

**Relationship to existing AARCHMRS:**
CoreSight components are external to the CPU core. None of their registers appear in
the existing AARCHMRS. This is a purely additive new dataset.

**Latest public release:** IHI0029F (CoreSight Architecture Specification v3.0)

**Data availability:** Same situation as GIC — no official JSON/XML release from Arm.
Before resorting to PDF extraction, check whether an IP-XACT or SVD description exists
for CoreSight components in community repositories. If an XML source is available,
prefer it over PDF parsing. Otherwise, register tables must be extracted and encoded
into JSON manually.

### 2.3 ARM Architecture Reference Manual — DDI0487

**What it covers beyond the current AARCHMRS:**
- Full prose descriptions for all registers and instructions (BSD AARCHMRS omits prose)
- A32 instruction set (32-bit ARM instructions, absent from current A64-only AARCHMRS)
- T32 instruction set (Thumb-2 instructions, absent from current AARCHMRS)
- AArch32 execution state system registers (partial in current AARCHMRS via `state=AArch32`)
- Memory model specification (VMSA, PMSA, memory types, shareability)
- Exception model (EL0–EL3, Secure, Non-secure, Realm)
- Translation table walk pseudocode
- Armv8/v9 extension chapters (SVE, SME, MPAM, RAS, etc.) with prose context

**Relationship to existing AARCHMRS:**
The AARCHMRS is a machine-readable *subset* of the ARM ARM: same encodings, same
register bit fields, but without prose. The ARM ARM (DDI0487) is the superset.
ARM publishes the full ARM ARM as a PDF, but also releases a companion MRS package
(the same JSON format as the current repo) that covers the complete A-profile including
T32 and A32. This companion MRS is distinct from the BSD-licensed package and is
subject to Arm proprietary licensing.

**Latest public release:** DDI0487 Maa (December 2024)

---

## 3. Data Availability Analysis

| Spec | Official machine-readable format | License |
|------|----------------------------------|---------|
| AARCHMRS (current) | JSON (this repo) | BSD 3-clause |
| ARM ARM (DDI0487) | PDF (authoritative); partial MRS (JSON) via Arm proprietary license | PDF: free download; full MRS: Arm proprietary |
| GIC (IHI0069) | PDF only | Free download |
| CoreSight (IHI0029) | PDF only | Free download |

**Key implication:** GIC and CoreSight data must be hand-curated or PDF-extracted.
The ARM ARM extension can leverage the existing MRS JSON schema if the full proprietary
MRS package is obtained, but falls back to hand-curation for T32/A32 if unavailable.

---

## 4. Repository Structure (After Extension)

```
arm-mrs-2025-03-aarchmrs/
├── Features.json              # Existing — AARCHMRS A64 features
├── Instructions.json          # Existing — AARCHMRS A64 instructions
├── Registers.json             # Existing — AARCHMRS system registers
│
├── gic/                       # NEW — GIC data files
│   ├── GIC.json               # Hand-curated or PDF-extracted register data
│   ├── GIC_meta.json          # Version/build metadata (_meta field)
│   └── schema/                # JSON schema for GIC data model
│       ├── GicRegister.json
│       ├── GicField.json
│       └── GicInterruptMap.json
│
├── coresight/                 # NEW — CoreSight data files
│   ├── CoreSight.json         # Hand-curated or PDF-extracted component register data
│   ├── CoreSight_meta.json    # Version/build metadata
│   └── schema/                # JSON schema for CoreSight data model
│       ├── CsComponent.json
│       ├── CsRegister.json
│       └── CsField.json
│
├── arm-arm/                   # NEW — ARM ARM additions (T32, A32, prose)
│   ├── T32Instructions.json   # T32 (Thumb-2) instruction encodings
│   ├── A32Instructions.json   # A32 (ARM 32-bit) instruction encodings
│   └── schema/                # Reuse/extend existing Instruction schema
│
├── schema/                    # Existing + extensions
│   ├── ... (existing files)
│   └── Peripheral/            # NEW — peripheral register schema (GIC, CoreSight)
│       ├── PeripheralRegister.json
│       └── PeripheralField.json
│
├── tools/                     # Existing + new
│   ├── build_index.py         # Extended to index GIC and CoreSight caches
│   ├── build_gic_index.py     # NEW — GIC-specific cache builder
│   ├── build_coresight_index.py  # NEW — CoreSight cache builder
│   ├── build_arm_arm_index.py # NEW — T32/A32 ISA cache builder
│   ├── convert_xml_to_json.py # NEW — converts ARM XML spec releases to the project JSON schema
│   ├── query_feature.py       # Existing
│   ├── query_register.py      # Extended — add --spec gic|coresight flag
│   ├── query_instruction.py   # Extended — add --isa t32|a32 flag
│   ├── query_gic.py           # NEW — GIC register queries
│   ├── query_coresight.py     # NEW — CoreSight component queries
│   └── query_search.py        # Extended — search across all spec namespaces
│
├── cache/                     # Generated, gitignored
│   ├── manifest.json          # Existing — extended with new spec file hashes
│   ├── features.json          # Existing
│   ├── registers/             # Existing — AARCHMRS system registers
│   ├── operations/            # Existing — AARCHMRS instructions
│   ├── registers_meta.json    # Existing — extended with GIC/CoreSight references
│   ├── gic/                   # NEW
│   │   ├── GICD.json          # Distributor registers
│   │   ├── GICR.json          # Redistributor registers
│   │   ├── GITS.json          # ITS registers
│   │   └── gic_meta.json      # Spec version index
│   ├── coresight/             # NEW
│   │   ├── ETM.json           # ETM component registers
│   │   ├── CTI.json           # CTI component registers
│   │   ├── STM.json
│   │   └── cs_meta.json       # Component inventory
│   └── arm_arm/               # NEW
│       ├── t32_operations/    # T32 operation JSON files
│       └── a32_operations/    # A32 operation JSON files
│
└── .claude/skills/
    ├── arm-feat.md            # Existing
    ├── arm-reg.md             # Existing — add note about ICC_* vs GICD/GICR
    ├── arm-instr.md           # Existing — add T32/A32 routing once available
    ├── arm-search.md          # Existing — extended for multi-spec search
    ├── arm-gic.md             # NEW — GIC register and interrupt model queries
    └── arm-coresight.md       # NEW — CoreSight component and register queries
```

---

## 5. New Data Schema Design

### 5.1 GIC Register Schema

GIC registers are memory-mapped peripheral registers, not CPU system registers. The
data model differs from `Registers.json` in the following ways:

- **No `state` field** (AArch64/AArch32/ext): GIC registers are memory-mapped
- **Address offset** replaces system register encoding (`op0/CRn/CRm/op2`)
- **Block** identifies the GIC component (GICD, GICR, GITS, etc.)
- **Interrupt range** links registers to interrupt number ranges

**Cache schema for `cache/gic/GICD.json`:**

```json
{
  "_meta": {
    "spec": "GIC",
    "version": "IHI0069H",
    "component": "GICD"
  },
  "registers": [
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
  ]
}
```

**Key differences from AARCHMRS register schema:**
| AARCHMRS `Registers.json` | GIC `gic/GIC.json` |
|--------------------------|-------------------|
| `state`: AArch64/AArch32/ext | No state — memory-mapped |
| `accessors` with op0/CRn/CRm | `offset` in component address space |
| AST `condition` for feature guard | `gic_version` minimum version field |
| `fieldsets[].condition` for conditional layouts | `variants[]` for GICv3-vs-GICv4 layouts |

### 5.2 CoreSight Register Schema

CoreSight components share a common identification block (32 Component ID / Peripheral ID
registers at the top of every 4KB component frame). The schema extends the GIC model
with a `component_type` discriminator.

**Cache schema for `cache/coresight/ETM.json`:**

```json
{
  "_meta": {
    "spec": "CoreSight",
    "version": "IHI0029F",
    "component_type": "ETM",
    "arch_id": "0x4A13"
  },
  "identification_registers": [
    {
      "name": "TRCDEVTYPE",
      "offset": "0xFCC",
      "description": "Device Type Register",
      "fields": [
        {"name": "SUB", "bits": [{"start": 4, "width": 4}]},
        {"name": "MAJOR", "bits": [{"start": 0, "width": 4}]}
      ]
    }
  ],
  "registers": [
    {
      "name": "TRCPRGCTLR",
      "offset": "0x004",
      "description": "Programming Control Register",
      "access": "RW",
      "fields": [
        {"name": "EN", "bits": [{"start": 0, "width": 1}], "description": "Trace enable"}
      ]
    }
  ]
}
```

### 5.3 ARM ARM Extension Schema (T32 / A32)

T32 and A32 instructions use the **same** `Instruction.json` schema already defined
in `schema/Instruction/`. The only addition is a new `isa` field at the top level of
each operation cache file (`"isa": "T32"` or `"isa": "A32"`) and a separate
`cache/arm_arm/t32_operations/` directory. No schema changes are required.

---

## 6. Implementation Phases

### Phase A — ARM ARM Extension (T32 / A32 ISA)

**Effort:** Medium (if full MRS package obtained) or High (if T32/A32 must be
hand-curated from the PDF)

**Prerequisites:**
- Obtain the full proprietary ARM ARM MRS package from the ARM Developer portal
  (requires accepting Arm's license). If unavailable, use the PDF as primary source.

**Steps:**

| Step | Task |
|------|------|
| A-1 | Evaluate whether the full ARM ARM MRS package (proprietary) can be ingested under its license terms. Record the decision and proceed to A-1a or A-1b accordingly. |
| A-1a *(license permits)* | Adapt `build_index.py` to parse T32/A32 JSON directly from the proprietary MRS package using the existing `schema/Instruction/` schema. Skip A-2. |
| A-1b *(license prohibits or package unavailable)* | Hand-curate `arm-arm/T32Instructions.json` and `arm-arm/A32Instructions.json` from the PDF. Proceed to A-2. |
| A-2 | Write `tools/build_arm_arm_index.py`: reads the hand-curated files from A-1b, writes `cache/arm_arm/t32_operations/` and `cache/arm_arm/a32_operations/` |
| A-3 | Extend `tools/query_instruction.py` with `--isa t32\|a32\|a64` flag (default `a64` for backward compatibility) |
| A-4 | Extend `.claude/skills/arm-instr.md` to route T32/A32 queries to the correct cache namespace |
| A-5 | Extend `tools/query_search.py` to search T32/A32 operation indexes |
| A-6 | Update `cache/manifest.json` schema to include T32/A32 source file hashes |

**Deliverables:** `arm-instr --isa t32 MOV`, `arm-instr-list --isa a32 LDR`

**Exit criteria:** `arm-instr --isa t32 LDR` returns correct T32 encoding without loading
the full T32Instructions.json into context.

---

### Phase B — GIC Extension

**Effort:** High (data must be extracted from PDF and hand-curated)

**Sub-phases:**

#### Phase B-0 — Data Acquisition

| Step | Task |
|------|------|
| B-0-1 | Check for XML/SVD sources: search `https://github.com/ARM-software/CMSIS_5` and community IP-XACT repositories for a machine-readable GIC register description. If found, proceed to B-0-2x (XML path). If not, proceed to B-0-2 (PDF path). |
| B-0-2x *(XML path)* | Use `tools/convert_xml_to_json.py` to convert the XML/SVD source into the project JSON schema. Validate output and skip B-0-2. |
| B-0-2 *(PDF path)* | Download IHI0069H (latest GICv3/v4 spec PDF) from developer.arm.com and extract all GICD, GICR, and ITS register tables. Options: (a) PDF text extraction + parser script; (b) manual JSON authoring; (c) scrape the HTML online documentation version if available. |
| B-0-3 | Extract ICC_* system register cross-references (already in AARCHMRS `Registers.json`; document the cross-reference, do not duplicate) |
| B-0-4 | Produce `gic/GIC.json` and `gic/GIC_meta.json` |
| B-0-5 | Define JSON schema in `gic/schema/` and validate `gic/GIC.json` against it |

**`gic/GIC.json` top-level structure:**
```json
{
  "_meta": {
    "spec": "GIC",
    "doc_id": "IHI0069H",
    "version": "GICv3/v4",
    "build_date": "ISO 8601 timestamp (set by the cache builder at index time, e.g. 2025-03-21T17:42:54Z)"
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

#### Phase B-1 — Cache Builder

| Step | Task |
|------|------|
| B-1-1 | Write `tools/build_gic_index.py`: reads `gic/GIC.json`, writes per-component cache files `cache/gic/GICD.json`, `cache/gic/GICR.json`, `cache/gic/GITS.json`, and index `cache/gic/gic_meta.json` |
| B-1-2 | Extend `cache/manifest.json` with SHA-256 of `gic/GIC.json` |
| B-1-3 | Add `gic/` to data gitignore exceptions (the source JSON should be committed; cache/ is gitignored) |

#### Phase B-2 — Query Tool

| Step | Task |
|------|------|
| B-2-1 | Write `tools/query_gic.py` |
| B-2-2 | Sub-commands (see §7.1 below) |
| B-2-3 | On missing cache: print `Cache not found. Run: python tools/build_gic_index.py` |

#### Phase B-3 — Agent Skill

| Step | Task |
|------|------|
| B-3-1 | Write `.claude/skills/arm-gic.md` |
| B-3-2 | Positive/negative triggers; routing guards vs. `arm-reg` for ICC_* |
| B-3-3 | Document ICC_* cross-reference: when user asks about ICC_IAR1_EL1, route to `arm-reg`, not `arm-gic` |

#### Phase B-4 — Search Integration

| Step | Task |
|------|------|
| B-4-1 | Extend `tools/query_search.py` to include GIC register names in search results |
| B-4-2 | Result type `"gic_register"` in search output envelope |
| B-4-3 | Extend `.claude/skills/arm-search.md` to route GIC results to `arm-gic` skill |

**Exit criteria:** `arm-gic GICD_CTLR` returns field layout and description without
loading full `gic/GIC.json` into context. `arm-search EnableGrp1` returns GIC
register results.

---

### Phase C — CoreSight Extension

**Effort:** High (data must be extracted from PDF)

**Sub-phases:**

#### Phase C-0 — Data Acquisition

| Step | Task |
|------|------|
| C-0-1 | Check for XML/SVD sources: search community IP-XACT and SVD repositories for machine-readable CoreSight component descriptions. If found, use `tools/convert_xml_to_json.py` to convert them and proceed to C-0-3. If not, proceed to C-0-2. |
| C-0-2 *(PDF path)* | Download IHI0029F (latest CoreSight Architecture Specification PDF) and extract register tables for each component type: ETM, CTI, STM, ITM, ROM Table, DAP, etc. |
| C-0-3 | Extract Component ID / Peripheral ID block (common to all CoreSight components) |
| C-0-4 | Produce `coresight/CoreSight.json` organized by component type |
| C-0-5 | Define JSON schema in `coresight/schema/` and validate the data |

**`coresight/CoreSight.json` top-level structure:**
```json
{
  "_meta": {
    "spec": "CoreSight",
    "doc_id": "IHI0029F",
    "version": "v3.0",
    "build_date": "ISO 8601 timestamp (set by the cache builder at index time, e.g. 2025-03-21T17:42:54Z)"
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

#### Phase C-1 — Cache Builder

| Step | Task |
|------|------|
| C-1-1 | Write `tools/build_coresight_index.py`: reads `coresight/CoreSight.json`, writes per-component cache files `cache/coresight/<COMPONENT>.json` and `cache/coresight/cs_meta.json` |
| C-1-2 | Extend `cache/manifest.json` with SHA-256 of `coresight/CoreSight.json` |

#### Phase C-2 — Query Tool

| Step | Task |
|------|------|
| C-2-1 | Write `tools/query_coresight.py` |
| C-2-2 | Sub-commands (see §7.2 below) |
| C-2-3 | On missing cache: print `Cache not found. Run: python tools/build_coresight_index.py` |

#### Phase C-3 — Agent Skill

| Step | Task |
|------|------|
| C-3-1 | Write `.claude/skills/arm-coresight.md` |
| C-3-2 | Positive triggers: debug component registers, ETM programming, CTI channel routing |
| C-3-3 | Negative examples: CPU system registers (→ `arm-reg`), interrupt controllers (→ `arm-gic`) |

#### Phase C-4 — Search Integration

| Step | Task |
|------|------|
| C-4-1 | Extend `tools/query_search.py` for CoreSight component names and register names |
| C-4-2 | Result type `"cs_register"` in search output envelope |

**Exit criteria:** `arm-coresight ETM TRCPRGCTLR` returns field layout. `arm-search TRC`
returns CoreSight ETM register results.

---

## 7. New Query Tool APIs

### 7.1 `tools/query_gic.py`

```
# Show all fields of a GIC register
query_gic.py GICD_CTLR

# Show a single field
query_gic.py GICD_CTLR EnableGrp1S

# Show all GIC interrupt controller registers for a component
query_gic.py --block GICD
query_gic.py --block GICR
query_gic.py --block GITS

# List register names matching a pattern
query_gic.py --list CTLR

# Show GICv3 vs GICv4 differences for a register
query_gic.py GICD_CTLR --version v3
query_gic.py GICD_CTLR --version v4

# Cross-reference: show which AARCHMRS system register corresponds to ICC_IAR1_EL1
query_gic.py --icc-xref ICC_IAR1_EL1
```

### 7.2 `tools/query_coresight.py`

```
# Show all fields of a CoreSight component register
query_coresight.py ETM TRCPRGCTLR

# Show a single field detail
query_coresight.py ETM TRCPRGCTLR EN

# Show all registers for a component
query_coresight.py --component ETM
query_coresight.py --component CTI

# List all known CoreSight component types
query_coresight.py --list-components

# Show registers matching a pattern across all components
query_coresight.py --list CTRL

# Show the common identification block registers
query_coresight.py --id-block
```

### 7.3 Extensions to `tools/query_instruction.py`

```
# T32 instruction query (new --isa flag)
query_instruction.py LDR --isa t32
query_instruction.py LDR --isa t32 --enc

# A32 instruction query
query_instruction.py LDR --isa a32
query_instruction.py LDR --isa a32 --op

# List all variants (all ISAs by default)
query_instruction.py --list MOV
query_instruction.py --list MOV --isa t32
query_instruction.py --list MOV --isa a32

# Default (--isa a64) is backward-compatible
query_instruction.py ADC                 # same as before
```

### 7.4 Extensions to `tools/query_search.py`

```
# Cross-spec search (all specs by default)
query_search.py TCR                      # AARCHMRS registers + GIC? CoreSight?

# Spec-filtered search
query_search.py --spec gic EnableGrp     # GIC registers only
query_search.py --spec coresight TRC     # CoreSight registers only
query_search.py --spec aarchmrs TCR      # existing behavior
```

---

## 8. New Agent Skills

### 8.1 `arm-gic` — GIC Register and Interrupt Model Queries

**Trigger:** User asks about interrupt controller registers, interrupt programming,
GICD/GICR/ITS registers, GIC initialization, LPI/MSI configuration, or vGIC virtualization.

**Do NOT use this skill for:**
- `ICC_*` system registers (e.g., ICC_IAR1_EL1) → use `arm-reg` — these are in AARCHMRS
- CPU interrupt pending state from software perspective → `arm-reg`
- Which CPU is taking an interrupt (affinity routing) if asking about system registers

| Sub-command | What it returns |
|-------------|----------------|
| `arm-gic GICD_CTLR` | All fields with bit ranges and access types |
| `arm-gic GICD_CTLR EnableGrp1S` | Single field detail |
| `arm-gic --block GICD` | All Distributor registers |
| `arm-gic --list ENABL` | Register names matching pattern |
| `arm-gic --icc-xref ICC_IAR1_EL1` | Cross-reference to AARCHMRS system register |

### 8.2 `arm-coresight` — CoreSight Component Queries

**Trigger:** User asks about debug infrastructure, ETM programming, trace enabling,
CTI channel routing, ITM stimulus ports, STM trace, ROM table parsing, or
`TRCPRGCTLR`/`TRCCONFIGR` registers.

**Do NOT use this skill for:**
- CPU halt/debug via MDSCR_EL1 → use `arm-reg` — that is a system register
- JTAG protocol details (out of scope for this project)

| Sub-command | What it returns |
|-------------|----------------|
| `arm-coresight ETM TRCPRGCTLR` | Field layout and access type |
| `arm-coresight CTI CTICONTROL` | CTI register detail |
| `arm-coresight --component ETM` | All ETM registers |
| `arm-coresight --list-components` | All CoreSight component types |
| `arm-coresight --id-block` | Common identification register block |

---

## 9. Skill Routing Summary

The following table shows the updated routing rules across all skills after the extension:

| User Query | Primary Skill | Notes |
|-----------|---------------|-------|
| "What fields does SCTLR_EL1 have?" | `arm-reg` | Existing |
| "How do I acknowledge an interrupt?" | `arm-gic` | Uses `ICC_IAR1_EL1` (system reg) + `GICD_*` flow |
| "What does GICD_CTLR.EnableGrp1 mean?" | `arm-gic` | GIC memory-mapped register |
| "What is ICC_IAR1_EL1?" | `arm-reg` | ICC_* is a system register in AARCHMRS |
| "How do I enable ETM tracing?" | `arm-coresight` | CoreSight register |
| "What does TRCPRGCTLR.EN do?" | `arm-coresight` | ETM register field |
| "What does T32 LDR do?" | `arm-instr --isa t32` | ARM ARM T32 extension |
| "Does FEAT_SVE require FEAT_FP16?" | `arm-feat` | Existing |
| "Find all EL2 registers" | `arm-search` | Existing |
| "Find any register named CTRL" | `arm-search` | Now searches across all specs |

---

## 10. Implementation Priority and Milestones

### Milestone 0 — ARM ARM Extension (T32 / A32) — Phase A

**Rationale:** Lowest friction — uses the same JSON schema already defined. If the
proprietary MRS package is available, this is mostly plumbing. Even as hand-curation
this extends the highest-value existing skill (`arm-instr`).

**Deliverable:** `arm-instr --isa t32 LDR` works correctly.

### Milestone 1 — GIC Data Acquisition and Schema — Phase B-0

**Rationale:** GIC register data is the most requested firmware development resource
after system registers. The ICC_* cross-reference with existing AARCHMRS data
also adds immediate value with no new data.

**Deliverable:** `gic/GIC.json` authored and schema-validated.

### Milestone 2 — GIC Cache + Query Tool — Phase B-1, B-2

**Deliverable:** `python tools/query_gic.py GICD_CTLR` works.

### Milestone 3 — GIC Agent Skill + Search Integration — Phase B-3, B-4

**Deliverable:** `arm-gic GICD_CTLR` in Claude Code; GIC registers appear in `arm-search`.

### Milestone 4 — CoreSight Data Acquisition and Schema — Phase C-0

**Deliverable:** `coresight/CoreSight.json` authored for ETM, CTI, STM.

### Milestone 5 — CoreSight Cache + Query Tool — Phase C-1, C-2

**Deliverable:** `python tools/query_coresight.py ETM TRCPRGCTLR` works.

### Milestone 6 — CoreSight Agent Skill + Search Integration — Phase C-3, C-4

**Deliverable:** `arm-coresight ETM TRCPRGCTLR` in Claude Code.

### Milestone 7 — Integration, Evaluation, and Hardening

| Step | Task |
|------|------|
| 7-1 | Extend `tools/eval_skill.py` with test cases for `arm-gic`, `arm-coresight`, and T32/A32 `arm-instr` |
| 7-2 | Test cross-skill routing: queries that span AARCHMRS + GIC (e.g., "How do I configure interrupt priority?") |
| 7-3 | Validate all skills emit spec-accurate descriptions (no hallucination) |
| 7-4 | Update `README.md`, `CLAUDE.md`, and `ROADMAP.md` with new build commands, supported specifications, and skill usage examples |

---

## 11. Dependency Graph

```
Phase A (ARM ARM / T32/A32)
  ├── Depends on: existing M0–M4 (already done)
  └── Enables: richer arm-instr skill with full ISA coverage

Phase B (GIC)
  ├── B-0 (Data) → B-1 (Cache) → B-2 (Query) → B-3 (Skill) → B-4 (Search)
  ├── B-3 depends on: existing arm-reg skill (for ICC_* cross-ref routing)
  └── Enables: complete interrupt controller programming workflow

Phase C (CoreSight)
  ├── C-0 (Data) → C-1 (Cache) → C-2 (Query) → C-3 (Skill) → C-4 (Search)
  ├── No hard dependency on Phase B (can be developed in parallel)
  └── Enables: complete debug infrastructure programming workflow

Milestone 7 (Integration)
  └── Depends on: Phase A complete + Phase B-3 complete + Phase C-3 complete
```

Phases A, B, and C can be started in parallel once their data acquisition steps are
complete. Phase B and Phase C share no code dependencies; only Milestone 7 requires all.

---

## 12. Licensing Considerations

| Specification | License | Action Required |
|--------------|---------|----------------|
| AARCHMRS (existing) | BSD 3-clause | Already compliant |
| ARM ARM (DDI0487) PDF | Free download, no redistribution | Do not commit PDF |
| ARM ARM MRS (proprietary) | Arm proprietary | Evaluate license before ingesting; may require separate repo or access control |
| GIC (IHI0069) PDF | Free download, no redistribution | Do not commit PDF; commit hand-curated JSON only if derivation is permissible |
| CoreSight (IHI0029) PDF | Free download, no redistribution | Same as GIC |

**Recommended approach for GIC and CoreSight:** Treat the hand-curated JSON files
(`gic/GIC.json`, `coresight/CoreSight.json`) as documentation-derived summaries rather
than verbatim extracts. Include the IHI document number and version as attribution in
the `_meta` field. Consult Arm's fair use / developer terms before publishing.

For the ARM ARM MRS package: if the proprietary license permits internal tool use but
not redistribution, keep the raw MRS JSON files in a separate private repository or
local directory (pointed to by `ARM_MRS_CACHE_DIR`), and commit only the schema
extensions and query tool changes.

---

## 13. Not in Scope

- **SMMU (SMMUv3, IHI0070):** While closely related to GIC for DMA interrupt routing,
  SMMU register programming is a separate large project. Listed as a future extension.
- **GICv5 (in development):** The GICv5 spec is not yet finalized. Plan targets GICv3/v4 (IHI0069H).
- **CoreSight SoC-specific implementations:** Only the architecture-defined register set
  from IHI0029 is in scope; vendor-specific ETM variants are excluded.
- **Prose synthesis:** Skills must never synthesize descriptions not present in the source
  data. For fields where `description` is null, emit "Description not available."
- **Third-party Python dependencies:** All tools remain stdlib-only (Python 3.8+).
- **Auto-rebuild inside skill invocations:** Cache must be pre-built; query scripts do
  not auto-rebuild.
- **AArch32-only firmware workflows:** AArch32 registers already accessible via
  `--state AArch32` in `arm-reg`; no new work needed for the register query path.

---

## 14. Open Questions

1. **GIC and CoreSight XML source quality:** Phase B-0 and C-0 direct implementers to
   check for CMSIS-SVD / IP-XACT sources before falling back to PDF extraction. The
   open question is coverage completeness: does the CMSIS-SVD GIC description at
   `https://github.com/ARM-software/CMSIS_5` cover all GICD, GICR, and ITS registers
   at the level of detail needed (field names, widths, access types)? Evaluate before
   committing to the XML or PDF path.

2. **ARM ARM MRS licensing:** Can the full proprietary ARM ARM MRS JSON package be
   used under the same BSD 3-clause terms as the AARCHMRS, or does it require a
   separate agreement? Contact Arm Developer Relations to clarify.

3. **CoreSight component selection:** The CoreSight architecture defines many optional
   components. Which subset provides the most value for the initial release? Suggested
   priority: ETM (tracing) > CTI (cross-triggering) > STM (software trace) > ITM.

4. **Schema version:** Should the new GIC/CoreSight schemas use the same `_meta` /
   schema-version conventions as the existing `schema/Meta.json`, or define a separate
   versioning namespace? Recommended: reuse `schema/Meta.json` with a new
   `spec_id` field to identify the source specification.
