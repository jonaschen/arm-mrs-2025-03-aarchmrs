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

### tools/probe.py

A data structure validation script that reads directly from the MRS source files
(no cache required) and prints the proposed cache JSON schema for each entity type.
Run this to verify data extraction assumptions before building the cache.

**Requirements:** Python 3.8+, no third-party dependencies.

```bash
# Run all probes (SCTLR_EL1 register, ADC instruction, v9Ap2 features, FEAT_SVE)
python tools/probe.py

# Probe a specific register
python tools/probe.py --register SCTLR_EL1
python tools/probe.py --register TCR_EL1
python tools/probe.py --register DBGBCR2_EL1   # parameterised register

# Probe a specific instruction operation
python tools/probe.py --operation ADC
python tools/probe.py --operation MRS

# List all operation IDs matching a mnemonic prefix
python tools/probe.py --list ADD

# Feature version traversal: all features introduced at or before a version
python tools/probe.py --feat-version v9Ap2

# Probe a specific feature
python tools/probe.py --feat FEAT_SVE
```

