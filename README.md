# AARCHMRS containing the JSON files for A-profile Architecture

## Introduction

This is the Arm Architecture Machine Readable Specification containing
JSON files representing the architecture as a machine readable format.

This package contains a subset of the information provided in the packages
with Arm proprietary licenses. Content that is not currently in a machine-readable
format, as well as all descriptive content, is omitted.

The [notice](docs/notice.html) gives details of the license terms and conditions
under which this package is provided.

## Package contents

 - `Features.json` contains the architecture feature constraints.
 - `Instructions.json` contains the A64 Instruction Set Architecture.
 - `Registers.json` contains the AArch32, AArch64, and MemoryMapped
   System Registers and System instructions.
 - [`schema`](schema/) contains JSON schema for the data.
 - [`docs`](docs/index.html) contains the rendered view of the schema
   as well as user guides to help understand the data above.

## Package quality

  - The architectural content contained within the data files has the same quality
    as the equivalent XML releases.
  - The schema and is still under development and is subject to change.

## Agent skills development

This repository is being extended with Claude Code agent skills for grounded,
hallucination-free hardware queries. See `AARCH64_AGENT_SKILL_DEV_PLAN.md` and
`ROADMAP.md` for the full design and implementation plan.

Six skills are implemented (Milestones M0–EX complete):

| Skill | Script | Cache builder | Specification |
|-------|--------|--------------|---------------|
| `arm-feat` | `query_feature.py` | `build_index.py` | AARCHMRS features |
| `arm-reg` | `query_register.py` | `build_index.py` | AARCHMRS registers |
| `arm-instr` | `query_instruction.py` | `build_index.py` + `build_arm_arm_index.py` | AARCHMRS A64 + T32/A32 |
| `arm-search` | `query_search.py` | all caches | Cross-spec discovery |
| `arm-gic` | `query_gic.py` | `build_gic_index.py` | GIC v3/v4 registers |
| `arm-coresight` | `query_coresight.py` | `build_coresight_index.py` | CoreSight component registers |
| `arm-pmu` | `query_pmu.py` | `build_pmu_index.py` | ARM PMU events |

### Building the caches

All query scripts require pre-built caches. Run these builders once, then
re-run only when the corresponding source data changes.

```bash
# A64 AARCHMRS cache (requires ~300–600 MB RAM, several minutes)
python tools/build_index.py

# T32/A32 instruction cache (fast — reads arm-arm/*.json)
python tools/build_arm_arm_index.py

# GIC register cache (fast — reads gic/GIC.json)
python tools/build_gic_index.py

# CoreSight register cache (fast — reads coresight/CoreSight.json)
python tools/build_coresight_index.py

# PMU event cache (fast — reads pmu/*.json)
python tools/build_pmu_index.py
```

### tools/query_feature.py

Queries architecture features (`FEAT_*`) and extensions from the AARCHMRS cache.

```bash
# Look up a single feature
python tools/query_feature.py FEAT_SVE

# Check whether one feature requires another
python tools/query_feature.py FEAT_SVE --deps FEAT_FP16

# List all features introduced at or before a version
python tools/query_feature.py --version v9Ap2

# List feature names matching a pattern
python tools/query_feature.py --list SVE
```

### tools/query_register.py

Queries system register fields, bit positions, access encodings, and field values.

```bash
# All fields of a register
python tools/query_register.py SCTLR_EL1

# Single field detail
python tools/query_register.py SCTLR_EL1 UCI

# Field values
python tools/query_register.py SCTLR_EL1 UCI --values

# MRS/MSR access encoding
python tools/query_register.py SCTLR_EL1 --access

# Parameterized register instance
python tools/query_register.py DBGBCR2_EL1

# List registers matching a pattern
python tools/query_register.py --list EL1 --state AArch64
```

### tools/query_instruction.py

Queries A64 (default), T32, and A32 instruction encodings and assembly syntax.

```bash
# A64 instruction (default)
python tools/query_instruction.py ADC
python tools/query_instruction.py ADC --enc

# T32 / A32 via --isa flag
python tools/query_instruction.py LDR --isa t32 --enc
python tools/query_instruction.py LDR --isa a32

# List operation IDs matching a pattern
python tools/query_instruction.py --list ADD
```

### tools/query_search.py

Cross-cutting keyword search across all supported specifications.

```bash
# Combined search (AARCHMRS + GIC + CoreSight + PMU)
python tools/query_search.py TCR

# Registers only
python tools/query_search.py --reg EL2 --state AArch64

# Operations only (all ISAs)
python tools/query_search.py --op ADD --isa all

# Spec-filtered search
python tools/query_search.py --spec aarchmrs TCR   # AARCHMRS registers + ops
python tools/query_search.py --spec gic EnableGrp1 # GIC registers only
python tools/query_search.py --spec coresight TRC  # CoreSight registers only
python tools/query_search.py --spec pmu CPU_CYCLES # PMU event names only
```

### tools/query_gic.py

Queries GIC v3/v4 memory-mapped registers (GICD, GICR, GITS blocks).

```bash
# All fields of a GIC register
python tools/query_gic.py GICD_CTLR

# Single field detail
python tools/query_gic.py GICD_CTLR EnableGrp0

# All registers in a block
python tools/query_gic.py --block GICD

# Register name search
python tools/query_gic.py --list CTLR

# ICC system register cross-reference (routes to arm-reg)
python tools/query_gic.py --icc-xref ICC_PMR_EL1
```

### tools/query_coresight.py

Queries CoreSight component registers (ETM, CTI, STM, ITM, ID_BLOCK).

```bash
# Register fields
python tools/query_coresight.py etm TRCPRGCTLR
python tools/query_coresight.py cti CTICONTROL GLBEN

# List component registers
python tools/query_coresight.py --component etm

# Common identification block
python tools/query_coresight.py --id-block

# List all components
python tools/query_coresight.py --list-components
```

### tools/query_pmu.py

Queries ARM PMU event codes and descriptions (sourced from ARM-software/data, Apache 2.0).

```bash
# All events for a CPU
python tools/query_pmu.py cortex-a710

# Single event detail
python tools/query_pmu.py cortex-a710 CPU_CYCLES

# Cross-CPU event search
python tools/query_pmu.py --search L1D_CACHE

# List all CPUs
python tools/query_pmu.py --list
```

### tools/eval_skill.py

Correctness evaluation — runs 137 tests across all six skills, verifying that every
query tool returns spec-grounded answers with no hallucination.

```bash
# Full suite (all 137 tests; requires all caches)
python tools/eval_skill.py

# Single skill
python tools/eval_skill.py --skill gic
python tools/eval_skill.py --skill coresight
python tools/eval_skill.py --skill pmu
python tools/eval_skill.py --skill cross_routing
```

### tools/probe.py

Development utility — validates data structure assumptions and previews the
proposed cache JSON schemas directly from the MRS source files (no cache required).
Run before modifying `build_index.py` to verify extraction logic.

```bash
python tools/probe.py                        # all probes
python tools/probe.py --register SCTLR_EL1
python tools/probe.py --operation ADC
python tools/probe.py --feat-version v9Ap2
python tools/probe.py --feat FEAT_SVE
python tools/probe.py --list ADD
```

