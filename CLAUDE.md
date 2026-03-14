# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

This repository has two layers:

1. **AARCHMRS data distribution** — the Arm A-profile Architecture Machine Readable Specification (v9Ap6-A, Build 445, March 2025) in machine-readable JSON format.
2. **Agent skills project** — a Python toolchain that grounds Claude Code responses in the MRS data (Phases 1–3; see `AARCH64_AGENT_SKILL_DEV_PLAN.md`).

## Core Data Files

| File | Size | Content |
|------|------|---------|
| `Features.json` | ~1 MB | Architecture features, versions, and constraint expressions |
| `Instructions.json` | ~38 MB | Complete A64 ISA (encodings, assembly syntax, operations) |
| `Registers.json` | ~75 MB | AArch32/AArch64/Memory-mapped system registers and fields |

All JSON files include a `_meta` property with version/build/timestamp metadata and conform to JSON Schema draft-04.

## Schema Organization (`schema/`)

138 JSON Schema files define the data model:

- **Core:** `Meta.json`, `Description.json`, `Encoding.json`, `Fieldset.json`, `Register.json`
- **Instructions** (`schema/Instruction/`): `Instruction.json`, `Assembly.json`, `Operation.json`, `Encodeset/`, `Rules/`
- **Registers** (`schema/Accessors/`): `SystemAccessor.json`, `MemoryMapped.json`, `ExternalDebug.json`, `Permission/`
- **AST** (`schema/AST/`): Constraint expression nodes — `BinaryOp`, `UnaryOp`, `If`, `ForLoop`, `Function`, `Identifier`, `Slice`, etc.
- **Supporting:** `Parameters/`, `Values/`, `Types/`, `Traits/`, `Enums/`, `References/`

## Key Architectural Concepts

**Features model:** Defines architecture feature constraints using AST expressions. Parameters represent `FEAT_*` identifiers and version strings (e.g., `v9Ap6`). Constraints use implication (`-->`), equivalence (`<->`), and logical/comparison operators.

**Registers model:** Each register has a state (`AArch64`, `AArch32`, `ext`), conditional fieldsets (bit field layouts), typed fields, accessors (how to read/write), and optional existence conditions.

**Instructions model:** The top-level `Instructions` wrapper contains `assembly_rules` (token patterns for assembly text), `operations` (semantic behavior in ASL), and `instructions` (encoding groups). Each instruction links to an operation and has assemble/disassemble blocks with ASL pseudocode.

**AST nodes:** Constraint and operation expressions are stored as `{"_type": "AST.*", ...}` objects throughout the data. See `schema/AST/` for node types.

## Documentation

- `docs/index.html` — Main documentation index
- `docs/userguide/` — Practical guides for features, registers, and ISA data models
- `docs/schema_specification.html` — Schema overview
- Individual `*_schema.html` files in `docs/` — Rendered per-type documentation
- `schema/Instruction/index.md`, `schema/AST/index.md` — Markdown guides per subsystem

## Versioning

- Architecture: v9Ap6-A
- Schema: 2.5.5
- Build: 445 (Fri Mar 21 17:42:54 2025)
- License: BSD 3-clause (see `docs/notice.html`)

---

## Agent Skills Development

Claude Code agent skills ground hardware-related AI responses in the MRS data, eliminating hallucination for register, instruction, feature, GIC, CoreSight, and PMU queries.

See `AARCH64_AGENT_SKILL_DEV_PLAN.md` for the full design (Parts I–III) and `ROADMAP.md` for the implementation checklist.

**Phase summary:**
- **Phase 1 (M0–M5):** Foundation spec-grounding skills — ✅ Complete
- **Phase 2 (E0, EA, EB, EC, EX):** Extensions (PMU, T32/A32, GIC, CoreSight, integration) — ✅ Complete
- **Phase 3 (H1–H8):** Active hardware engineering (code generation, GDB-MCP, QEMU, linter, multi-agent) — 🔲 Planned

### Structure

```
tools/
  cache_utils.py       # [DONE] Shared path resolution, staleness checking, AST renderer
  probe.py             # [DONE] Data validation and cache schema preview (no cache needed)
  build_index.py       # [DONE] One-time cache builder (run before using any A64 skill)
  build_arm_arm_index.py # [DONE] T32/A32 cache builder (Milestone EA)
  build_gic_index.py   # [DONE] GIC cache builder (Milestone EB)
  build_coresight_index.py # [DONE] CoreSight cache builder (Milestone EC)
  build_pmu_index.py       # [DONE] PMU event cache builder (Milestone E0)
  query_feature.py     # [DONE] Feature/extension and version queries
  query_register.py    # [DONE] Register/field/accessor queries
  query_instruction.py # [DONE] Instruction encoding and operation queries (--isa a64|t32|a32)
  query_search.py      # [DONE] Cross-cutting keyword search (--isa a64|t32|a32|all; --spec aarchmrs|gic|coresight|pmu)
  query_gic.py         # [DONE] GIC register field, version, and cross-reference queries
  query_coresight.py   # [DONE] CoreSight component register field and access queries
  query_pmu.py         # [DONE] PMU event code and description queries (Milestone E0)
  eval_skill.py        # [DONE] Correctness evaluation (137 tests: 51 A64 + 16 T32/A32 + 18 GIC + 24 CoreSight + 14 PMU + 14 EX)
arm-arm/               # Hand-curated T32/A32 instruction data (committed)
  T32Instructions.json # T32 (Thumb-2) instruction encodings — starter set
  A32Instructions.json # A32 (classic ARM 32-bit) instruction encodings — starter set
gic/                   # Hand-curated GIC register data (committed)
  GIC.json             # GIC v3/v4 register data (GICD, GICR, GITS blocks + ICC cross-refs)
  GIC_meta.json        # GIC metadata (block titles, version descriptions)
  schema/              # JSON Schema for GIC data
coresight/             # Hand-curated CoreSight register data (committed)
  CoreSight.json       # CoreSight component register data (ETM, CTI, STM, ITM, ID_BLOCK)
  CoreSight_meta.json  # CoreSight metadata (component titles, version descriptions)
  schema/              # JSON Schema for CoreSight data
pmu/                   # ARM PMU event data (Apache 2.0, sourced from ARM-software/data)
  cortex-a53.json      # Cortex-A53 PMU events (armv8-a, 59 events)
  cortex-a55.json      # Cortex-A55 PMU events (armv8.2-a, 111 events)
  cortex-a76.json      # Cortex-A76 PMU events (armv8-a, 107 events)
  cortex-a510.json     # Cortex-A510 PMU events (armv9-a, 144 events)
  cortex-a710.json     # Cortex-A710 PMU events (armv9-a, 151 events)
  cortex-x2.json       # Cortex-X2 PMU events (armv9-a, 151 events)
  neoverse-n1.json     # Neoverse N1 PMU events (armv8.2-a, 110 events)
  neoverse-n2.json     # Neoverse N2 PMU events (armv9-a, 155 events)
cache/                 # Generated by build_index.py — gitignored
  manifest.json        # Source file hashes for staleness detection
  features.json        # All 361 features (loaded whole — small)
  registers/           # One JSON per register × state (1,607 files)
  operations/          # One JSON per A64 operation_id (2,262 files)
  registers_meta.json  # Name→state index for listing and search
  arm_arm/             # Generated by build_arm_arm_index.py — gitignored
    t32_operations/    # One JSON per T32 operation_id
    a32_operations/    # One JSON per A32 operation_id
    manifest.json      # T32/A32 source hashes
  gic/                 # Generated by build_gic_index.py — gitignored
    GICD.json          # GICD block registers
    GICR.json          # GICR block registers
    GITS.json          # GITS block registers
    gic_meta.json      # Name→block index and field index
  coresight/           # Generated by build_coresight_index.py — gitignored
    ETM.json           # ETM component registers
    CTI.json           # CTI component registers
    STM.json           # STM component registers
    ITM.json           # ITM component registers
    ID_BLOCK.json      # Common identification block registers
    cs_meta.json       # Name→component index and field index
  pmu/                 # Generated by build_pmu_index.py — gitignored
    cortex-a710.json   # Cortex-A710 normalised event cache (one file per CPU)
    ...                # One JSON per CPU slug
  pmu_meta.json        # CPU slug → {cpu_name, architecture, event_count}
  pmu_events_flat.json # Cross-CPU event name → [{cpu_slug, code, description}]
.claude/skills/
  arm-feat.md          # [DONE] Feature/extension queries
  arm-reg.md           # [DONE] Register field, value, and access queries
  arm-search.md        # [DONE] Cross-cutting discovery (includes T32/A32, GIC, CoreSight)
  arm-instr.md         # [DONE] Instruction encoding and behavior queries (A64 + T32/A32)
  arm-gic.md           # [DONE] GIC register queries (GICD/GICR/GITS)
  arm-coresight.md     # [DONE] CoreSight component register queries (ETM/CTI/STM/ITM)
  arm-pmu.md           # [DONE] PMU event code and description queries (Milestone E0)
```

### Development workflow

Use `python3` throughout — `python` on this system is Python 2.7.

**Probe the MRS data** (no cache needed — useful when exploring the raw JSON structure):

```bash
python3 tools/probe.py                        # all probes
python3 tools/probe.py --register SCTLR_EL1  # register schema preview
python3 tools/probe.py --operation ADC        # instruction schema preview
python3 tools/probe.py --feat-version v9Ap2  # feature version traversal
python3 tools/probe.py --feat FEAT_SVE        # single feature
python3 tools/probe.py --list ADD             # discover operation_id values
```

**Build all caches** before running any query or eval command:

```bash
python3 tools/build_index.py           # A64 cache (~300–600 MB RAM, several minutes)
python3 tools/build_arm_arm_index.py   # T32/A32 cache (fast)
python3 tools/build_gic_index.py       # GIC cache (fast)
python3 tools/build_coresight_index.py # CoreSight cache (fast)
python3 tools/build_pmu_index.py       # PMU event cache (fast)
```

Re-run the relevant builder whenever a source file changes:

| Source file(s) changed | Re-run |
|------------------------|--------|
| `Features.json`, `Instructions.json`, `Registers.json` | `build_index.py` |
| `arm-arm/T32Instructions.json`, `arm-arm/A32Instructions.json` | `build_arm_arm_index.py` |
| `gic/GIC.json` | `build_gic_index.py` |
| `coresight/CoreSight.json` | `build_coresight_index.py` |
| any `pmu/*.json` | `build_pmu_index.py` |

### Path resolution in skills

Skills resolve the repo root via the `ARM_MRS_CACHE_DIR` environment variable (if set) or `git rev-parse --show-toplevel` at invocation time. Set `ARM_MRS_CACHE_DIR` to reuse the cache across multiple projects pointing at the same MRS data.

### Skill usage quick reference

```bash
# Feature queries
python3 tools/query_feature.py FEAT_SVE
python3 tools/query_feature.py FEAT_SVE --deps FEAT_FP16
python3 tools/query_feature.py --version v9Ap2
python3 tools/query_feature.py --list SVE

# Register queries
python3 tools/query_register.py SCTLR_EL1
python3 tools/query_register.py SCTLR_EL1 UCI --values
python3 tools/query_register.py SCTLR_EL1 --access
python3 tools/query_register.py DBGBCR2_EL1
python3 tools/query_register.py --list EL1 --state AArch64

# Instruction queries (A64 default; use --isa t32 or --isa a32 for T32/A32)
python3 tools/query_instruction.py ADC
python3 tools/query_instruction.py ADC --enc
python3 tools/query_instruction.py LDR --isa t32 --enc
python3 tools/query_instruction.py --list ADD

# Cross-cutting search
python3 tools/query_search.py TCR
python3 tools/query_search.py --reg EL2 --state AArch64
python3 tools/query_search.py --op ADD --isa all
python3 tools/query_search.py TRC
python3 tools/query_search.py --spec aarchmrs TCR
python3 tools/query_search.py --spec coresight TRC
python3 tools/query_search.py --spec gic EnableGrp1
python3 tools/query_search.py --spec pmu CPU_CYCLES

# GIC queries
python3 tools/query_gic.py GICD_CTLR
python3 tools/query_gic.py GICD_CTLR EnableGrp0
python3 tools/query_gic.py --block GICR
python3 tools/query_gic.py --list CTLR

# CoreSight queries
python3 tools/query_coresight.py etm TRCPRGCTLR
python3 tools/query_coresight.py etm TRCPRGCTLR EN
python3 tools/query_coresight.py cti CTICONTROL GLBEN
python3 tools/query_coresight.py --component etm
python3 tools/query_coresight.py --list-components
python3 tools/query_coresight.py --id-block

# PMU event queries
python3 tools/query_pmu.py cortex-a710
python3 tools/query_pmu.py cortex-a710 CPU_CYCLES
python3 tools/query_pmu.py cortex-a710 L1D_CACHE_REFILL
python3 tools/query_pmu.py --search L1D_CACHE
python3 tools/query_pmu.py --search STALL
python3 tools/query_pmu.py --list
python3 tools/query_pmu.py --list neoverse

# Correctness evaluation (all 137 tests should pass)
python3 tools/eval_skill.py
python3 tools/eval_skill.py --skill gic
python3 tools/eval_skill.py --skill coresight
python3 tools/eval_skill.py --skill pmu
python3 tools/eval_skill.py --skill cross_routing
```

### Important constraints

- **BSD MRS omits all prose.** Most `title`, `purpose`, and `description` fields are `null`. Skills emit "Description not available in BSD MRS release" for these — never synthesize prose.
- **AArch64 is the default state.** When a register name matches both AArch32 and AArch64, AArch64 is returned. Use `--state AArch32` to explicitly request the AArch32 variant.
- **Parameterized registers** (e.g., `DBGBCR<n>_EL1`) are cached as `DBGBCR_n_EL1__AArch64.json`. Queries like `arm-reg DBGBCR2_EL1` are normalized automatically.
- **`operation_id` is the instruction key.** It is shared between the `operations` dict (behavior) and instruction tree nodes (encoding). Use `--list` in the probe or `arm-instr-list` in the skill to discover valid `operation_id` values for a mnemonic.
- **Instruction encoding is assembled from the hierarchy.** Each instruction node only carries discriminating opcode bits; operand field definitions live in parent `InstructionGroup` nodes. `build_index.py` resolves this via a two-pass bit-level merge so each `cache/operations/*.json` file contains a complete, self-contained 32-bit field layout with `kind=fixed|operand|class` classification. Query scripts read from the cache only — they do not re-parse the tree.
- **PMU event descriptions are available.** Unlike the BSD AARCHMRS release, `pmu/*.json` data (Apache 2.0, from ARM-software/data) has real prose descriptions for every event.
- **T32/A32 coverage is a starter set.** `arm-arm/` contains 6 T32 + 6 A32 instructions hand-curated from ARM DDI0487. Use `--isa t32/a32` to query them; A64 is still the default.

---

## Phase 3 — Active Hardware Engineering (H1–H8)

Phase 3 builds a code-generation and verification loop on top of the spec-grounding foundation. It is **planned, not yet implemented**. See `AARCH64_AGENT_SKILL_DEV_PLAN.md` Part III for full detail.

| Skill | Description | Blocker |
|-------|-------------|---------|
| H1 | AARCHMRS allowlist output (`query_allowlist.py`) | None |
| H2 | Hierarchical RAG on ARM ARM (DDI 0487) | ARM Architecture License required |
| H3 | GDB-MCP debugging (step, inspect, assert registers) | None |
| H4 | QEMU-AArch64 emulation automation | None |
| H5 | Cross-compilation & static linking (`aarch64-linux-gnu-gcc`) | None |
| H6 | Advanced ISA optimization (SVE2, SME, PAC, BTI, MTE) | Depends on H1 |
| H7 | Linter-in-the-loop (VIXL, ≥50 AArch64 lint rules) | Depends on H6 |
| H8 | Multi-agent orchestration (Developer/Critic/Judge/Executor) | Depends on H3 + H4 + H5 |

H3, H4, and H5 have no blockers and can be started independently.
