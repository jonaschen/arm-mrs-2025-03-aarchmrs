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

### tools/build_index.py

Parses all three MRS source files and writes the `cache/` directory. Must be run
once before any query script or skill can be used. Clears and rebuilds the cache
on every run to prevent stale files.

**Requirements:** Python 3.8+, no third-party dependencies. ~300–600 MB RAM.

```bash
python tools/build_index.py
```

Outputs: `cache/features.json` (361 entries), `cache/registers/` (1,607 files),
`cache/operations/` (2,262 files), `cache/registers_meta.json`, `cache/manifest.json`.
Re-run whenever the MRS source files are updated.

### tools/query_feature.py

Queries architecture features and extensions from the cache.

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

