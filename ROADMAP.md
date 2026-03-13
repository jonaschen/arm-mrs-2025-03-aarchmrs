# ARM Agent Skills — Roadmap

> See `AARCH64_AGENT_SKILL_DEV_PLAN.md` for full design rationale behind each decision.

---

## Status summary

| Milestone | Description | Status |
|-----------|-------------|--------|
| M0 | Foundation (cache builder) | ✅ Complete |
| M1 | `arm-feat` — Feature skill | ✅ Complete |
| M2 | `arm-reg` — Register skill | ✅ Complete |
| M3 | `arm-search` — Search skill | ✅ Complete |
| M4 | `arm-instr` — Instruction skill | ✅ Complete |
| ME | Skill correctness evaluation (51 tests) | ✅ Complete |
| M5 | Integration and hardening | 🔲 Pending |
| E0 | `arm-pmu` — PMU events skill | 🔲 Pending |
| EA | ARM ARM extension (ASL unlock + T32/A32) | 🔲 Pending |
| EB | `arm-gic` — GIC register skill | 🔲 Pending |
| EC | `arm-coresight` — CoreSight skill | 🔲 Pending |
| EX | Cross-extension integration and eval | 🔲 Pending |

---

# Phase 1 — Foundation Skills (Complete)

## Milestone 0 — Cache Builder ✅

**Goal:** Repo infrastructure required by all later milestones.

- [x] **M0-1** Create `.gitignore` with `cache/` entry
- [x] **M0-2** Create `tools/` directory
- [x] **M0-3** Write `tools/build_index.py`
  - Parse `Features.json` → `cache/features.json`
  - Parse `Instructions.json` → `cache/operations/OPERATION_ID.json` (operation data merged with linked instruction node encodings via two-pass bit-level merge algorithm)
  - Parse `Registers.json` → `cache/registers/NAME__STATE.json` (sanitize `<n>` → `_n_`; include `index_variable` and `indexes`)
  - Write `cache/registers_meta.json` (name → [{state, cache_key}] index)
  - Write `cache/manifest.json` (SHA-256 hashes of all three source files)
  - Wipe and recreate `cache/` on each run to prevent stale files
- [x] **M0-4** Validate generated cache: spot-check `SCTLR_EL1__AArch64.json`, `ADC.json`, `ADD_addsub_imm.json`, `cache/features.json`
- [x] **M0-5** Document cache rebuild command in `CLAUDE.md`

**Exit criteria:** ✅ `python3 tools/build_index.py` produces 1,607 register files, 2,262 operation files, `features.json`, `registers_meta.json`, and `manifest.json` with no errors.

---

## Milestone 1 — Feature Skill (`arm-feat`) ✅

**Goal:** Ground feature/extension queries in spec data.

- [x] **M1-1** Write `tools/query_feature.py`
  - `FEAT_SVE` — feature entry + rendered constraints
  - `FEAT_SVE --deps FEAT_FP16` — yes/conditional/no dependency answer + full constraint tree
  - `--version v9Ap2` — AST traversal for `FEAT_X --> vNApM` patterns, filtered by version ceiling
  - `--list SVE` — name pattern search
  - On missing cache: prints error and exits non-zero; on stale cache: warns and continues
- [x] **M1-2** Write `.claude/skills/arm-feat.md` — positive/negative triggers, path resolution
- [x] **M1-3** Manual test: `FEAT_SVE --deps FEAT_FP16` → Yes; `--deps FEAT_PMUv3p1` → Conditional; `--deps FEAT_NEON` → No; `--version v9Ap2` → 261 features; `--list SVE` → 19 results

**Exit criteria:** ✅ Skill returns spec-grounded answers without loading full `Features.json` into context.

---

## Milestone 2 — Register Skill (`arm-reg`) ✅

**Goal:** Ground register field, value, and access queries in spec data.

- [x] **M2-1** Write `tools/query_register.py`
  - `SCTLR_EL1` — all named fields with bit ranges, field types, allowed values; default AArch64
  - `SCTLR_EL1 UCI` — single field detail
  - `SCTLR_EL1 UCI --values` — full value enumeration and meanings
  - `SCTLR_EL1 --access` — all accessor types and encodings
  - `--list EL1 [--state AArch64|AArch32|ext]` — name pattern search with optional state filter
  - Parameterized register resolution: `DBGBCR2_EL1` → `DBGBCR<n>_EL1` meta lookup
- [x] **M2-2** Write `.claude/skills/arm-reg.md` — positive/negative triggers, path resolution
- [x] **M2-3** Manual test: SCTLR_EL1 fields, TCR_EL1 access encoding, DBGBCR2_EL1 parameterized lookup, `--list EL2 --state AArch64`; 12 eval tests (100%)

**Exit criteria:** ✅ Skill returns correct field layout and accessor encoding for common AArch64 system registers without loading `Registers.json` into context.

---

## Milestone 3 — Search Skill (`arm-search`) ✅

**Goal:** Cross-cutting discovery when the user doesn't know which module to query.

- [x] **M3-1** Write `tools/query_search.py`
  - `TCR` — search `registers_meta.json` + operation key index; grouped plain-text results
  - `--reg EL2 [--state AArch64]` — register-only search with state filter
  - `--op ADD` — operation-only search
- [x] **M3-2** Write `.claude/skills/arm-search.md` — instructs skill to follow up with targeted calls
- [x] **M3-3** Manual test: `--reg EL2 --state AArch64` → 131 results; `TCR` → 15 results incl. TCR_EL1; 5 eval tests (100%)

**Exit criteria:** ✅ Search returns structured results and correctly hands off to the right skill.

---

## Milestone 4 — Instruction Skill (`arm-instr`) ✅

**Goal:** Ground instruction behavior and encoding queries in spec data.

- [x] **M4-1** Write `tools/query_instruction.py`
  - `ADC` — operation title, brief, all encoding variants linked via `operation_id`
  - `ADC --enc` — encoding bit fields and widths for all variants
  - `ADC --op [--full]` — ASL pseudocode blocks (null in BSD release — skill notes unavailability)
  - `--list ADD` — all `operation_id` values containing the pattern
  - Handles null `decode` field gracefully
- [x] **M4-2** Write `.claude/skills/arm-instr.md` — positive/negative triggers; MRS ambiguity clarified
- [x] **M4-3** Manual test: ADC encoding (sf/Rd/Rn/Rm operands correct), `--list ADD` → 129 results, MRS --enc; 11 eval tests (100%)

**Note:** ASL pseudocode is `null` / `// Not specified` across all 2,262 operations in the BSD MRS release. See Milestone EA for the unlock path.

**Exit criteria:** ✅ Skill returns correct instruction encoding and assembly templates without loading `Instructions.json` into context.

---

## Milestone E — Skill Correctness Evaluation ✅

**Goal:** Reproducible correctness measurement proving the skills eliminate AArch64 hardware hallucination.

- [x] **ME-1** Write `tools/eval_skill.py`
  - 51 ground-truth test cases across four skills
  - Categories: existence, non-existence (hallucination detection), field correctness, encoding accuracy, dependency classification, version counts, list counts, BSD prose disclaimer
  - Framework extensible: `ALL_SKILLS` dict adds new skills as extensions are implemented
- [x] **ME-2** Run evaluation: all 51 tests pass (100%) against v9Ap6-A, Build 445
  - feat: 23 tests · reg: 12 tests · search: 5 tests · instr: 11 tests

**Exit criteria:** ✅ `python3 tools/eval_skill.py` exits 0 with "ALL TESTS PASSED".

---

## Milestone 5 — Integration and Hardening 🔲

**Goal:** Cross-skill polish and real-world validation before extension work begins.

- [ ] **M5-1** Test skill routing with ambiguous queries; add routing examples to each skill file where gaps are found
- [ ] **M5-2** Validate all skills correctly emit "Description not available in BSD MRS release" for null fields rather than synthesizing prose
- [ ] **M5-3** Document `ARM_MRS_CACHE_DIR` env var in `CLAUDE.md` for multi-project use
- [ ] **M5-4** Update `CLAUDE.md` with final `build_index.py` invocation and skill usage examples
- [ ] **M5-5** Extract shared `check_staleness()` and manifest logic from all query scripts into `tools/cache_utils.py` (prerequisite for Phase 2 extensions)

**Exit criteria:** All four skills pass ambiguous routing tests. `cache_utils.py` exists. `CLAUDE.md` is up to date.

---

# Phase 2 — Extensions

## Milestone E0 — PMU Events Skill (`arm-pmu`) 🔲

**Goal:** Ground PMU performance counter queries in ARM-official data. Highest-priority extension: natively machine-readable, Apache 2.0, no license barrier, real prose descriptions.

**Source:** `https://github.com/ARM-software/data` (pmu/ directory)
**Prerequisite:** M5 (cache_utils.py must exist)

- [ ] **E0-1** Probe `ARM-software/data/pmu/` — confirm field names (`ArchitectureName`, `Code`, `PublicDescription`), measure CPU coverage, identify any null description fields; document schema
- [ ] **E0-2** Write `tools/build_pmu_index.py`
  - Reads all `pmu/*.json` from a cloned/downloaded snapshot
  - Writes `cache/pmu/<cpu>.json` per CPU
  - Writes `cache/pmu_meta.json` (cpu_name → {file, event_count})
  - Writes `cache/pmu_events_flat.json` (flat cross-CPU search index)
  - Updates `cache/manifest.json` with PMU source commit SHA
- [ ] **E0-3** Write `tools/query_pmu.py`
  - `cortex-a710` — all events with codes and truncated description
  - `cortex-a710 CPU_CYCLES` — single event full detail
  - `--search L1D_CACHE` — cross-CPU event name search
  - `--list` — all CPUs with event counts
- [ ] **E0-4** Write `.claude/skills/arm-pmu.md`
  - Positive triggers: PMU event codes, PMEVTYPER programming, cross-CPU event comparison
  - Negative examples: `PMCCNTR_EL0` programming → `arm-reg`; instruction throughput → out of scope
  - Note: descriptions ARE available in this dataset (unlike BSD AARCHMRS)
- [ ] **E0-5** Extend `eval_skill.py` with `pmu` test cases: CPU existence, `CPU_CYCLES` code for Cortex-A710, cross-CPU `L1D_CACHE_REFILL` search, hallucination guard

**Exit criteria:** `python3 tools/query_pmu.py cortex-a710 CPU_CYCLES` returns the ARM-official event code and description. All pmu eval tests pass.

---

## Milestone EA — ARM ARM Extension (ASL + T32/A32) 🔲

**Goal:** Unlock ASL pseudocode for existing A64 skills (EA-a) and add T32/A32 ISA coverage (EA-b). Both sub-tasks share the same licensing gate.

**Source:** ARM Architecture License (proprietary MRS XML package); or ARM ARM PDF for hand-curation
**Prerequisite:** Architecture license decision; M5

### EA-a — ASL Pseudocode Unlock

- [ ] **EA-a-1** Determine whether an ARM Architecture License is available. If yes, download the XML MRA package and probe its structure. If no, skip EA-a entirely.
- [ ] **EA-a-2** Map XML field paths → JSON cache schema fields for `decode` and `operation` bodies
- [ ] **EA-a-3** Extend `tools/build_index.py` with optional `--xml-dir` argument: merge ASL pseudocode and prose descriptions into existing `cache/operations/*.json` and `cache/registers/*.json`; preserve JSON-only path for users without the XML release
- [ ] **EA-a-4** Update skill files: remove "not available in BSD MRS release" disclaimers where data is now present; `arm-instr --op` returns real ASL
- [ ] **EA-a-5** Add conditional eval tests that skip when `--xml-dir` was not provided

### EA-b — T32/A32 ISA Coverage

- [ ] **EA-b-1** Source T32/A32 data: parse from licensed MRS package (if available) using existing `schema/Instruction/`, or hand-curate `arm-arm/T32Instructions.json` and `arm-arm/A32Instructions.json` from the PDF
- [ ] **EA-b-2** Write `tools/build_arm_arm_index.py`: writes `cache/arm_arm/t32_operations/` and `cache/arm_arm/a32_operations/` in the same per-operation_id format as `cache/operations/`; updates `manifest.json`
- [ ] **EA-b-3** Extend `tools/query_instruction.py` with `--isa t32|a32|a64` flag (default `a64` for backward compatibility)
- [ ] **EA-b-4** Extend `tools/query_search.py` to include T32/A32 operation indexes
- [ ] **EA-b-5** Update `.claude/skills/arm-instr.md` to document T32/A32 routing

**Exit criteria:** `python3 tools/query_instruction.py LDR --isa t32` returns correct T32 encoding. `arm-instr --op ADC` returns real ASL pseudocode (if licensed).

---

## Milestone EB — GIC Skill (`arm-gic`) 🔲

**Goal:** Ground GIC register queries in spec data. Adds the memory-mapped GICD/GICR/ITS registers absent from AARCHMRS, with cross-references to the ICC_* system registers already in `arm-reg`.

**Source:** `https://developer.arm.com/documentation/ihi0069/latest/` (HTML); or CMSIS-SVD if available
**License:** Proprietary — `cache/gic/` must be gitignored; `gic/GIC.json` may be committed as a documentation-derived summary (consult ARM Developer Relations before publishing)
**Prerequisite:** M5; HTML extractability confirmed

### EB-0 — Data Acquisition

- [ ] **EB-0-1** Check for XML/SVD source: search `ARM-software/CMSIS_5` and community IP-XACT repos for a machine-readable GIC description with field-level coverage. If found, write `tools/convert_xml_to_json.py` and use it; skip HTML path.
- [ ] **EB-0-2** If no XML source: confirm ARM's HTML documentation is parseable as static HTML (not JavaScript-rendered). Fetch a sample GICD_CTLR page and verify register tables are present without a headless browser. Do not proceed to EB-0-3 until confirmed.
- [ ] **EB-0-3** Write `tools/fetch_gic.py`: downloads GIC spec HTML; parses register tables using `html.parser` (stdlib); rate-limits requests; writes staging JSON per register
- [ ] **EB-0-4** Extract and organise GICD, GICR, ITS registers; document GICv3-vs-GICv4 field variants
- [ ] **EB-0-5** Document `ICC_*` cross-references in `gic/GIC.json` `icc_system_registers` array — do NOT duplicate data already in AARCHMRS
- [ ] **EB-0-6** Produce `gic/GIC.json` and `gic/GIC_meta.json`; define and validate `gic/schema/`

### EB-1 — Cache Builder

- [ ] **EB-1-1** Write `tools/build_gic_index.py`: reads `gic/GIC.json`; writes `cache/gic/GICD.json`, `cache/gic/GICR.json`, `cache/gic/GITS.json`, and `cache/gic/gic_meta.json`
- [ ] **EB-1-2** Extend `cache/manifest.json` with SHA-256 of `gic/GIC.json`
- [ ] **EB-1-3** Add `cache/gic/` to `.gitignore`

### EB-2 — Query Tool

- [ ] **EB-2-1** Write `tools/query_gic.py`
  - `GICD_CTLR` — all fields with bit ranges, access types, reset values
  - `GICD_CTLR EnableGrp1S` — single field detail
  - `--block GICD|GICR|GITS` — all registers in a component block
  - `--list CTLR` — register names matching pattern
  - `GICD_CTLR --version v3|v4` — GICv3 vs GICv4 field variants
  - `--icc-xref ICC_IAR1_EL1` — cross-reference to AARCHMRS system register

### EB-3 — Agent Skill

- [ ] **EB-3-1** Write `.claude/skills/arm-gic.md`
  - Positive triggers: GICD/GICR/ITS registers, GIC initialisation, LPI/MSI configuration, vGIC
  - Negative examples: `ICC_*` system registers → `arm-reg`; CPU interrupt pending state → `arm-reg`

### EB-4 — Search Integration

- [ ] **EB-4-1** Extend `tools/query_search.py`: add `--spec gic` filter; add `"gic_register"` result type; include GIC register names in default combined search
- [ ] **EB-4-2** Update `.claude/skills/arm-search.md` to route GIC results to `arm-gic`
- [ ] **EB-4-3** Extend `eval_skill.py` with `gic` test cases: register existence, field bit position, access type, `--icc-xref` output, hallucination guard

**Exit criteria:** `python3 tools/query_gic.py GICD_CTLR EnableGrp0` returns correct bit position and access type. `arm-search EnableGrp1` returns GIC results. All gic eval tests pass.

---

## Milestone EC — CoreSight Skill (`arm-coresight`) 🔲

**Goal:** Ground CoreSight debug/trace component register queries in spec data.

**Source:** `https://developer.arm.com/documentation/ihi0029/latest/` (HTML); or IP-XACT if available
**License:** Proprietary — `cache/coresight/` must be gitignored
**Prerequisite:** EB HTML extraction approach validated; M5

### EC-0 — Data Acquisition

- [ ] **EC-0-1** Check for IP-XACT or SVD sources for CoreSight component registers. If found, use `tools/convert_xml_to_json.py`. If not, confirm static HTML (same check as EB-0-2).
- [ ] **EC-0-2** Write `tools/fetch_coresight.py` (if HTML path): downloads CoreSight spec HTML; parses per-component register tables; handles component type scoping
- [ ] **EC-0-3** Extract the common identification block (32 registers per 4 KB frame) separately from component-specific registers
- [ ] **EC-0-4** Initial component priority: ETM → CTI → STM → ITM
- [ ] **EC-0-5** Produce `coresight/CoreSight.json` and `coresight/CoreSight_meta.json`; define and validate `coresight/schema/`

### EC-1 — Cache Builder

- [ ] **EC-1-1** Write `tools/build_coresight_index.py`: reads `coresight/CoreSight.json`; writes per-component cache files under `cache/coresight/<component>/` and `cache/coresight/cs_meta.json`; extends `cache/manifest.json`
- [ ] **EC-1-2** Add `cache/coresight/` to `.gitignore`

### EC-2 — Query Tool

- [ ] **EC-2-1** Write `tools/query_coresight.py`
  - `etm TRCPRGCTLR` — field layout and access type for a component register
  - `etm TRCPRGCTLR EN` — single field detail
  - `--component etm|cti|stm|itm` — all registers for a component
  - `--list-components` — all known component types
  - `--list CTRL` — register names matching pattern across all components
  - `--id-block` — common identification block registers

### EC-3 — Agent Skill

- [ ] **EC-3-1** Write `.claude/skills/arm-coresight.md`
  - Positive triggers: ETM programming, trace enabling, CTI channel routing, ITM stimulus ports, STM trace, ROM table, `TRCPRGCTLR`/`TRCCONFIGR`
  - Negative examples: CPU halt via `MDSCR_EL1` → `arm-reg`; JTAG protocol → out of scope

### EC-4 — Search Integration

- [ ] **EC-4-1** Extend `tools/query_search.py`: add `--spec coresight` filter; add `"cs_register"` result type
- [ ] **EC-4-2** Update `.claude/skills/arm-search.md` to route CoreSight results to `arm-coresight`
- [ ] **EC-4-3** Extend `eval_skill.py` with `coresight` test cases

**Exit criteria:** `python3 tools/query_coresight.py etm TRCPRGCTLR` returns field layout. `arm-search TRC` returns CoreSight ETM results. All coresight eval tests pass.

---

## Milestone EX — Cross-Extension Integration 🔲

**Goal:** Validate all six skills work together correctly; update all documentation.

**Prerequisite:** E0 complete · EA complete · EB-3 complete · EC-3 complete

- [ ] **EX-1** Test cross-skill routing for queries that span multiple specs (e.g., "How do I configure interrupt priority?" — involves GICD_CTLR + ICC_PMR_EL1)
- [ ] **EX-2** Test `arm-search` with `--spec` flag across all specs
- [ ] **EX-3** Run full eval suite across all six skills; confirm no regressions
- [ ] **EX-4** Update `README.md`, `CLAUDE.md`, and `AARCH64_AGENT_SKILL_DEV_PLAN.md` with new build commands, supported specifications, and skill usage examples

**Exit criteria:** All eval tests across all skills pass. Cross-spec routing is validated. Documentation is complete.

---

# Dependency Graph

```
M0 (Cache builder)
 ├── M1 (arm-feat) ──────────────────────────────────────────┐
 ├── M2 (arm-reg)  ──────────────────────────────────────────┤
 ├── M3 (arm-search) ────────────────────────────────────────┤
 ├── M4 (arm-instr) ─────────────────────────────────────────┤
 │       └── ME (Eval: 51 tests) ──────────────────────────  ┤
 └── ──────── M5 (Integration + cache_utils.py) ────────────┘
                │
                ├── E0 (arm-pmu)              ← Apache 2.0; no blockers
                │       └── ─────────────────────────────────────────┐
                ├── EA (ASL unlock + T32/A32) ← needs architecture license
                │       └── ─────────────────────────────────────────┤
                ├── EB (arm-gic)              ← needs HTML confirm / SVD check
                │       └── ─────────────────────────────────────────┤
                └── EC (arm-coresight)        ← needs EB validation
                        └── ──────────────────────────────────────── ┤
                                                        EX (Integration)
```

**Parallelism:** E0, EA, and EB-0 probe (data acquisition only) can all start immediately after M5.
EA and EB/EC have no code dependencies on each other. EX requires all of E0, EA, EB, EC.

---

# Not in Scope

| Item | Reason |
|------|--------|
| SMMU (IHI0070) | Logical next step after EB/EC; deferred as a future project |
| GICv5 | Spec not yet finalised; plan targets GICv3/v4 (IHI0069H) |
| CMSIS-SVD microcontroller files | Microcontroller peripherals, not ARM system architecture |
| Linux kernel device tree bindings | Linux device model, not the ARM spec |
| TrustZone / TF-A registers | Already in AARCHMRS `Registers.json` |
| AMBA bus protocol (APB, AXI) | No register-level spec; signal-level only |
| ARM Compiler documentation | Tool documentation, not hardware spec |
| CoreSight SoC-specific variants | Architecture-defined registers only (IHI0029) |
| Auto-rebuild inside skill invocations | Too slow for interactive use |
| Third-party Python dependencies | Stdlib only: `json`, `hashlib`, `os`, `argparse`, Python 3.8+ |
| Prose synthesis | Skills must emit "Description not available" for null fields; never synthesise |
