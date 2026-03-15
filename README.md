# AARCHMRS — ARM A-profile Architecture Machine Readable Specification + Agent Skills

## Introduction

This is the Arm Architecture Machine Readable Specification (v9Ap6-A, Build 445, March 2025)
containing JSON files representing the architecture in machine-readable format.

This package contains a subset of the information provided in the packages with Arm proprietary
licenses. Content that is not currently in a machine-readable format, as well as all descriptive
content, is omitted. The [notice](docs/notice.html) gives details of the license terms.

The repository also bundles **Claude Code agent skills** (Phases 1–3) that ground AI responses
in the MRS data — eliminating hallucination for register, instruction, feature, GIC, CoreSight,
PMU, cross-compilation, and code-generation queries. See `AARCH64_AGENT_SKILL_DEV_PLAN.md` and
`ROADMAP.md` for the full design and implementation plan.

> **Alpha release** — all Phase 1–3 skills are implemented and passing 292 evaluation tests.
> See [Alpha Testing](#alpha-testing) below for how to report gaps and contribute feedback.

---

## System Requirements

| Requirement | Minimum |
|-------------|---------|
| Python | 3.8+ (stdlib only — no pip install needed) |
| RAM | ~512 MB free during `build_index.py` (reads 113 MB of JSON) |
| Disk | ~200 MB for the generated `cache/` directory |
| Claude Code | Latest version (for agent skill integration) |
| Optional | `gdb-multiarch` (for H3 GDB debugging skill) |
| Optional | `qemu-aarch64` (for H4 QEMU emulation skill) |
| Optional | `gcc-aarch64-linux-gnu` (for H5 cross-compilation skill) |

No internet access is required after cloning. All data is self-contained in the repository.

---

## Quick Start

See [QUICKSTART.md](QUICKSTART.md) for the full first-time setup walkthrough.

**In brief:**

```bash
# 1. Clone the repository
git clone https://github.com/jonaschen/arm-mrs-2025-03-aarchmrs.git
cd arm-mrs-2025-03-aarchmrs

# 2. Build all caches (run once; repeat only when source JSON files change)
python3 tools/build_index.py           # A64 cache (~300–600 MB RAM, several minutes)
python3 tools/build_arm_arm_index.py   # T32/A32 cache (fast)
python3 tools/build_gic_index.py       # GIC cache (fast)
python3 tools/build_coresight_index.py # CoreSight cache (fast)
python3 tools/build_pmu_index.py       # PMU event cache (fast)

# 3. Verify all 292 eval tests pass
python3 tools/eval_skill.py

# 4. Try a query
python3 tools/query_register.py SCTLR_EL1
python3 tools/query_feature.py FEAT_SVE
python3 tools/query_instruction.py ADC --enc
```

---

## Claude Code Integration

The skills in `.claude/skills/` are loaded automatically when you open this repository in
[Claude Code](https://claude.ai/code). No additional configuration is required.

1. **Open the repository** in Claude Code (File → Open Folder).
2. **Build the caches** (see Quick Start above) so the query tools can find data.
3. **Ask hardware questions naturally** — Claude Code will invoke the right skill automatically.

Example prompts that invoke the skills:

| Prompt | Skill invoked |
|--------|--------------|
| "What are the fields of SCTLR_EL1?" | `arm-reg` |
| "Does FEAT_SVE require FEAT_FP16?" | `arm-feat` |
| "Show ADC encoding" | `arm-instr` |
| "Search for TCR registers" | `arm-search` |
| "What does GICD_CTLR.EnableGrp0 do?" | `arm-gic` |
| "Show ETM trace enable register" | `arm-coresight` |
| "What is the CPU_CYCLES event code on Cortex-A710?" | `arm-pmu` |
| "What instructions are valid at v9Ap4?" | `arm-allowlist` |
| "Generate SVE2 dot-product kernel for v9Ap4" | `arm-isa-opt` |
| "Cross-compile hello.c for AArch64 v9Ap0 with SVE2" | `arm-cross` |
| "Lint my AArch64 assembly for PAC/BTI violations" | `arm-linter` |

**Shared cache across projects:** Set `ARM_MRS_CACHE_DIR` to a persistent path to reuse one
cache directory from multiple workspaces pointing at the same MRS data.

---

## Package contents

 - `Features.json` — architecture feature constraints (344 `FEAT_*` + 17 version params).
 - `Instructions.json` — complete A64 ISA (2,262 operations, 4,584 instruction nodes).
 - `Registers.json` — AArch32, AArch64, and MemoryMapped System Registers (1,607 registers).
 - [`schema/`](schema/) — 138 JSON Schema files defining the data model.
 - [`docs/`](docs/index.html) — rendered schema documentation and user guides.
 - `arm-arm/` — hand-curated T32/A32 instruction data (starter set, 6 T32 + 6 A32).
 - `gic/` — GIC v3/v4 register data (24 registers: GICD, GICR, GITS blocks).
 - `coresight/` — CoreSight component register data (40 registers: ETM, CTI, STM, ITM).
 - `pmu/` — ARM PMU event data (Apache 2.0, 8 CPU files, ~900 events total).
 - `tools/` — cache builders, query scripts, and agent skill support tools.
 - `.claude/skills/` — Claude Code skill files (auto-loaded when repo is open).

## Package quality

  - The architectural content contained within the data files has the same quality
    as the equivalent XML releases.
  - The schema is still under development and is subject to change.
  - BSD MRS omits all prose: `title`, `purpose`, and `description` fields are `null`.
    Skills emit "Description not available in BSD MRS release" for these — prose is
    never synthesised.

---

## Skills overview

All 14 skills are implemented across Phases 1–3. Every skill uses only Python stdlib
(no `pip install` needed) and queries pre-built caches rather than loading multi-MB JSON files.

### Phase 1 — Foundation (M0–M5, complete)

| Skill | Script | Cache builder | Coverage |
|-------|--------|--------------|----------|
| `arm-feat` | `query_feature.py` | `build_index.py` | AARCHMRS features (361 params) |
| `arm-reg` | `query_register.py` | `build_index.py` | AARCHMRS registers (1,607) |
| `arm-instr` | `query_instruction.py` | `build_index.py` + `build_arm_arm_index.py` | A64 (2,262 ops) + T32/A32 |
| `arm-search` | `query_search.py` | all caches | Cross-spec keyword discovery |

### Phase 2 — Extensions (E0–EX, complete)

| Skill | Script | Cache builder | Coverage |
|-------|--------|--------------|----------|
| `arm-pmu` | `query_pmu.py` | `build_pmu_index.py` | PMU events (8 CPUs, ~900 events) |
| `arm-gic` | `query_gic.py` | `build_gic_index.py` | GIC v3/v4 (24 registers) |
| `arm-coresight` | `query_coresight.py` | `build_coresight_index.py` | CoreSight (40 registers) |

### Phase 3 — Active Hardware Engineering (H1–H7, complete)

| Skill | Script | Description |
|-------|--------|-------------|
| `arm-allowlist` | `query_allowlist.py` | Feature-qualified instruction allowlist + register blocklist |
| `arm-gdb` | `query_gdb.py` + `gdb_session.py` | GDB/MI debugging — step, inspect, assert registers |
| `arm-qemu` | `gen_qemu_launch.py` | QEMU launch-script generator + user-mode runner |
| `arm-cross` | `setup_cross_compile.py` | Cross-compilation (`aarch64-linux-gnu-gcc`), 20 repair rules |
| `arm-isa-opt` | `isa_optimize.py` | SVE2/SME templates, PAC/BTI insertion, MTE helpers, 18 security rules |
| `arm-linter` | `isa_linter.py` | 50 AArch64 lint rules, auto-repair, lint-green gate |

---

## Building the caches

All query scripts read from a `cache/` directory that must be built once before first use.
Re-run the relevant builder whenever a source file changes. The `cache/` directory is
gitignored and never committed.

```bash
# A64 AARCHMRS cache (requires ~300–600 MB RAM, several minutes)
python3 tools/build_index.py

# T32/A32 instruction cache (fast — reads arm-arm/*.json)
python3 tools/build_arm_arm_index.py

# GIC register cache (fast — reads gic/GIC.json)
python3 tools/build_gic_index.py

# CoreSight register cache (fast — reads coresight/CoreSight.json)
python3 tools/build_coresight_index.py

# PMU event cache (fast — reads pmu/*.json)
python3 tools/build_pmu_index.py
```

| Source file(s) changed | Re-run |
|------------------------|--------|
| `Features.json`, `Instructions.json`, `Registers.json` | `build_index.py` |
| `arm-arm/T32Instructions.json`, `arm-arm/A32Instructions.json` | `build_arm_arm_index.py` |
| `gic/GIC.json` | `build_gic_index.py` |
| `coresight/CoreSight.json` | `build_coresight_index.py` |
| any `pmu/*.json` | `build_pmu_index.py` |

---

## Phase 1 & 2 query tools

### tools/query_feature.py

Queries architecture features (`FEAT_*`) and extensions from the AARCHMRS cache.

```bash
python3 tools/query_feature.py FEAT_SVE
python3 tools/query_feature.py FEAT_SVE --deps FEAT_FP16
python3 tools/query_feature.py --version v9Ap2
python3 tools/query_feature.py --list SVE
```

### tools/query_register.py

Queries system register fields, bit positions, access encodings, and field values.

```bash
python3 tools/query_register.py SCTLR_EL1
python3 tools/query_register.py SCTLR_EL1 UCI
python3 tools/query_register.py SCTLR_EL1 UCI --values
python3 tools/query_register.py SCTLR_EL1 --access
python3 tools/query_register.py DBGBCR2_EL1
python3 tools/query_register.py --list EL1 --state AArch64
```

### tools/query_instruction.py

Queries A64 (default), T32, and A32 instruction encodings and assembly syntax.

```bash
python3 tools/query_instruction.py ADC
python3 tools/query_instruction.py ADC --enc
python3 tools/query_instruction.py LDR --isa t32 --enc
python3 tools/query_instruction.py LDR --isa a32
python3 tools/query_instruction.py --list ADD
```

### tools/query_search.py

Cross-cutting keyword search across all supported specifications.

```bash
python3 tools/query_search.py TCR
python3 tools/query_search.py --reg EL2 --state AArch64
python3 tools/query_search.py --op ADD --isa all
python3 tools/query_search.py --spec aarchmrs TCR
python3 tools/query_search.py --spec gic EnableGrp1
python3 tools/query_search.py --spec coresight TRC
python3 tools/query_search.py --spec pmu CPU_CYCLES
```

### tools/query_gic.py

Queries GIC v3/v4 memory-mapped registers (GICD, GICR, GITS blocks).

```bash
python3 tools/query_gic.py GICD_CTLR
python3 tools/query_gic.py GICD_CTLR EnableGrp0
python3 tools/query_gic.py --block GICD
python3 tools/query_gic.py --list CTLR
python3 tools/query_gic.py --icc-xref ICC_PMR_EL1
```

### tools/query_coresight.py

Queries CoreSight component registers (ETM, CTI, STM, ITM, ID_BLOCK).

```bash
python3 tools/query_coresight.py etm TRCPRGCTLR
python3 tools/query_coresight.py cti CTICONTROL GLBEN
python3 tools/query_coresight.py --component etm
python3 tools/query_coresight.py --id-block
python3 tools/query_coresight.py --list-components
```

### tools/query_pmu.py

Queries ARM PMU event codes and descriptions (sourced from ARM-software/data, Apache 2.0).

```bash
python3 tools/query_pmu.py cortex-a710
python3 tools/query_pmu.py cortex-a710 CPU_CYCLES
python3 tools/query_pmu.py --search L1D_CACHE
python3 tools/query_pmu.py --list
```

---

## Phase 3 query tools

### tools/query_allowlist.py

Generates a feature-qualified instruction allowlist and register blocklist for a target
architecture version. Useful for determining which instructions are valid for a given BSP.

```bash
python3 tools/query_allowlist.py --arch v9Ap4 --summary
python3 tools/query_allowlist.py --arch v9Ap4 --feat FEAT_SVE2 --summary
python3 tools/query_allowlist.py --arch v9Ap4 --output json
python3 tools/query_allowlist.py --list-features v9Ap4
```

### tools/query_gdb.py + tools/gdb_session.py

GDB/MI session manager for AArch64 debugging — step, inspect registers, assert values,
and diagnose SIGILL. Requires `gdb-multiarch` (install: `apt install gdb-multiarch`).

```bash
python3 tools/query_gdb.py --check
python3 tools/query_gdb.py ./my_binary --break main --registers
python3 tools/query_gdb.py ./my_binary --step 3 --assert "x0=0"
python3 tools/query_gdb.py ./my_binary --suite suite.json
python3 tools/query_gdb.py --sigill-hint v9Ap4 --pc 0x4004f0
```

### tools/gen_qemu_launch.py

Generates QEMU launch scripts and runs AArch64 binaries in user-mode QEMU.
Requires `qemu-aarch64` (install: `apt install qemu-user-static`).

```bash
python3 tools/gen_qemu_launch.py --check
python3 tools/gen_qemu_launch.py --mode user --cpu max
python3 tools/gen_qemu_launch.py --mode system --cpu cortex-a57
python3 tools/gen_qemu_launch.py --run ./my_binary --cpu cortex-a57
python3 tools/gen_qemu_launch.py --list-cpus
```

### tools/setup_cross_compile.py

Manages the `aarch64-linux-gnu-gcc` cross-toolchain. Includes 20 compile-error
auto-repair rules and `-march` flag generation from AARCHMRS version strings.
Requires `gcc-aarch64-linux-gnu` (install: `apt install gcc-aarch64-linux-gnu`).

```bash
python3 tools/setup_cross_compile.py --check
python3 tools/setup_cross_compile.py --compile hello.c
python3 tools/setup_cross_compile.py --compile hello.c --arch v9Ap4 --link static
python3 tools/setup_cross_compile.py --march-flag --arch v9Ap0 --feat FEAT_SVE2
python3 tools/setup_cross_compile.py --repair-hint "illegal instruction"
```

### tools/isa_optimize.py

Generates high-performance and security-hardened AArch64 code: 12 SVE2/SME templates,
PAC/BTI auto-insertion, MTE tag-management helpers, and 18 security rules.

```bash
python3 tools/isa_optimize.py --list-templates
python3 tools/isa_optimize.py --template sve2-dotproduct --arch v9Ap4
python3 tools/isa_optimize.py --template sme-matmul --arch v9Ap2
python3 tools/isa_optimize.py --auto-pac-bti --arch v9Ap0 --input func.s
python3 tools/isa_optimize.py --mte-helpers --arch v8Ap5
python3 tools/isa_optimize.py --list-rules
```

### tools/isa_linter.py

AArch64 assembly linter with 50 rules (security, alignment, register, branch, encoding),
auto-repair suggestions, and a lint-green blocking gate. Optionally integrates with VIXL.

```bash
python3 tools/isa_linter.py --list-rules
python3 tools/isa_linter.py --list-rules --category security
python3 tools/isa_linter.py --lint test.s --arch v9Ap0
python3 tools/isa_linter.py --lint-green test.s --arch v9Ap4
python3 tools/isa_linter.py --check-vixl
```

---

## Correctness evaluation

`tools/eval_skill.py` runs 292 ground-truth tests across all skills, verifying that every
query tool returns spec-grounded answers with no hallucination. All 292 tests must pass
before the caches are considered valid for daily use.

```bash
# Full suite (all 292 tests; requires all caches)
python3 tools/eval_skill.py

# Per-skill subsets (faster iteration)
python3 tools/eval_skill.py --skill feat
python3 tools/eval_skill.py --skill reg
python3 tools/eval_skill.py --skill instr
python3 tools/eval_skill.py --skill search
python3 tools/eval_skill.py --skill gic
python3 tools/eval_skill.py --skill coresight
python3 tools/eval_skill.py --skill pmu
python3 tools/eval_skill.py --skill cross_routing
python3 tools/eval_skill.py --skill allowlist
python3 tools/eval_skill.py --skill gdb
python3 tools/eval_skill.py --skill qemu
python3 tools/eval_skill.py --skill cross
python3 tools/eval_skill.py --skill isa_opt
python3 tools/eval_skill.py --skill linter
```

---

## tools/probe.py

Development utility — validates data structure assumptions and previews cache JSON schemas
directly from the MRS source files without requiring a pre-built cache. Useful when
modifying `build_index.py` or exploring the raw JSON structure.

```bash
python3 tools/probe.py                        # all probes
python3 tools/probe.py --register SCTLR_EL1
python3 tools/probe.py --operation ADC
python3 tools/probe.py --feat-version v9Ap2
python3 tools/probe.py --feat FEAT_SVE
python3 tools/probe.py --list ADD
```

---

## Known limitations

| Limitation | Detail |
|-----------|--------|
| No prose in BSD MRS | `title`/`purpose`/`description` fields are `null` throughout `Features.json`, `Instructions.json`, and `Registers.json`. Skills emit "Description not available in BSD MRS release". |
| ASL pseudocode deferred | `decode`/`operation` bodies are `null` in the BSD release. Unlock requires an ARM Architecture License (Milestone H2/EA-a — deferred). |
| T32/A32 starter set | `arm-arm/` contains only 6 T32 + 6 A32 hand-curated instructions. A full T32/A32 set requires the proprietary MRS XML package. |
| GIC and CoreSight coverage | `gic/GIC.json` has 24 GICv3/v4 registers; `coresight/CoreSight.json` has 40 registers across 5 components. More registers can be added incrementally. |
| H8 multi-agent not yet started | The Developer/Critic/Judge/Executor orchestration loop (Milestone H8) depends on H3+H4+H5+H7 and is next in the roadmap. |
| GDB/QEMU/cross-compiler optional | H3/H4/H5 skills degrade gracefully when the tools are not installed; use `--check` to verify availability. |

---

## Alpha Testing

This project is in alpha. If you are evaluating it as a BSP engineer, your feedback is
the most valuable input for closing gaps before a wider release.
See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide on reporting issues and
submitting data or code improvements.

### How to report issues

Open a GitHub Issue with:

1. **The query or prompt** that produced wrong or missing output.
2. **The actual output** (paste the terminal output or Claude Code response).
3. **The expected output** (what the ARM spec says, or what you expected to see).
4. **Your environment** (OS, Python version, Claude Code version, which caches are built).

Label the issue `alpha-feedback` so it is triaged promptly.

### Categories of feedback most needed

| Category | Example gap |
|----------|------------|
| Wrong register field layout | "SCTLR_EL1.UCI bit position is wrong" |
| Missing instruction | "MOV (register) encoding not found" |
| Wrong feature dependency | "FEAT_SVE2 dependency chain is incorrect" |
| GIC/CoreSight gap | "GICD_IROUTER register is missing" |
| PMU event discrepancy | "Cortex-A53 CPU_CYCLES event code is wrong" |
| Cross-compile failure | "Compile error not covered by repair rules" |
| Lint false positive/negative | "Rule L27 fires incorrectly on XZR destination" |
| Claude skill misrouting | "Claude answered a register question without calling arm-reg" |

### Sharing with colleagues

This repository is self-contained — no in-house database or proprietary tooling is required.
Clone it, build the caches, and open it in Claude Code. The only optional dependencies are
standard Linux development tools (`gdb-multiarch`, `qemu-aarch64`, `gcc-aarch64-linux-gnu`),
all available via `apt`.

For team setups, set `ARM_MRS_CACHE_DIR` to a shared NFS/local path so the large
`build_index.py` run is done once and all team members reuse the same cache directory.

