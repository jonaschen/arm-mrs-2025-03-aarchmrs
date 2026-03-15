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
| M5 | Integration and hardening | ✅ Complete |
| E0 | `arm-pmu` — PMU events skill | ✅ Complete |
| EA | ARM ARM extension (ASL unlock + T32/A32) | ✅ Complete (EA-b; EA-a deferred — no ARM Architecture License) |
| EB | `arm-gic` — GIC register skill | ✅ Complete |
| EC | `arm-coresight` — CoreSight skill | ✅ Complete |
| EX | Cross-extension integration and eval | ✅ Complete |
| H1 | Allowlist output + `query_allowlist.py` | ✅ Complete |
| H2 | Hierarchical RAG on ARM ARM | 🔲 Pending (blocked: ARM Architecture License) |
| H3 | GDB-MCP debugging skill | ✅ Complete |
| H4 | QEMU emulation automation | ✅ Complete |
| H5 | Cross-compilation & static linking | ✅ Complete |
| H6 | Advanced ISA optimization (SVE2/SME/PAC/BTI/MTE) | ✅ Complete |
| H7 | Linter-in-the-loop (VIXL) | ✅ Complete |
| H8 | Multi-agent orchestration | 🔲 Pending |

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

## Milestone 5 — Integration and Hardening ✅

**Goal:** Cross-skill polish and real-world validation before extension work begins.

- [x] **M5-1** Test skill routing with ambiguous queries; routing disambiguation verified in all four skill files (MRS ambiguity, ISA routing, FEAT vs register, search handoff)
- [x] **M5-2** Validate all skills correctly emit "Description not available in BSD MRS release" for null fields — verified in eval tests and confirmed in Important Constraints sections of all skill files
- [x] **M5-3** Document `ARM_MRS_CACHE_DIR` env var in `CLAUDE.md` for multi-project use
- [x] **M5-4** Update `CLAUDE.md` with final build invocations and skill usage quick reference (all four query scripts with example commands)
- [x] **M5-5** Extract shared `check_staleness()`, `render_ast()`, and path setup into `tools/cache_utils.py`; all four query scripts now import from it; `import re` moved to module top in `query_instruction.py`

**Exit criteria:** ✅ All four skills pass ambiguous routing tests. `cache_utils.py` exists. `CLAUDE.md` is up to date. 67/67 eval tests pass.

---

# Phase 2 — Extensions

## Milestone E0 — PMU Events Skill (`arm-pmu`) ✅

**Goal:** Ground PMU performance counter queries in ARM-official data. Highest-priority extension: natively machine-readable, Apache 2.0, no license barrier, real prose descriptions.

**Source:** `https://github.com/ARM-software/data` (pmu/ directory)
**Prerequisite:** M5 (cache_utils.py must exist)

- [x] **E0-1** Probe `ARM-software/data/pmu/` — confirmed field names (`name`, `code`, `description`, `architectural`, `type`, `component`); 56 CPU files; descriptions present for all events; Apache 2.0 license; starter set of 8 representative CPUs committed to `pmu/`
- [x] **E0-2** Write `tools/build_pmu_index.py`
  - Reads all `pmu/*.json` from a cloned/downloaded snapshot
  - Writes `cache/pmu/<cpu>.json` per CPU
  - Writes `cache/pmu_meta.json` (cpu_name → {file, event_count})
  - Writes `cache/pmu_events_flat.json` (flat cross-CPU search index)
  - Updates `cache/manifest.json` with PMU source file SHA-256 hashes
- [x] **E0-3** Write `tools/query_pmu.py`
  - `cortex-a710` — all events with codes and truncated description
  - `cortex-a710 CPU_CYCLES` — single event full detail
  - `--search L1D_CACHE` — cross-CPU event name search
  - `--list` — all CPUs with event counts
- [x] **E0-4** Write `.claude/skills/arm-pmu.md`
  - Positive triggers: PMU event codes, PMEVTYPER programming, cross-CPU event comparison
  - Negative examples: `PMCCNTR_EL0` programming → `arm-reg`; instruction throughput → out of scope
  - Note: descriptions ARE available in this dataset (unlike BSD AARCHMRS)
- [x] **E0-5** Extend `eval_skill.py` with `pmu` test cases: CPU existence, `CPU_CYCLES` code for Cortex-A710, cross-CPU `L1D_CACHE_REFILL` search, hallucination guard (14 tests, all pass)

**Exit criteria:** ✅ `python3 tools/query_pmu.py cortex-a710 CPU_CYCLES` returns the ARM-official event code and description. All pmu eval tests pass.

---

## Milestone EA — ARM ARM Extension (ASL + T32/A32) ✅

**Goal:** Unlock ASL pseudocode for existing A64 skills (EA-a) and add T32/A32 ISA coverage (EA-b). Both sub-tasks share the same licensing gate.

**Source:** ARM Architecture License (proprietary MRS XML package); or ARM ARM PDF for hand-curation
**Prerequisite:** Architecture license decision; M5

### EA-a — ASL Pseudocode Unlock

- [x] **EA-a-1** Determine whether an ARM Architecture License is available. **Result: no ARM Architecture License is available.** EA-a-2 through EA-a-4 are deferred until a license is obtained.
- [ ] **EA-a-2** Map XML field paths → JSON cache schema fields for `decode` and `operation` bodies *(deferred — no license)*
- [ ] **EA-a-3** Extend `tools/build_index.py` with optional `--xml-dir` argument: merge ASL pseudocode and prose descriptions into existing `cache/operations/*.json` and `cache/registers/*.json`; preserve JSON-only path for users without the XML release *(deferred — no license)*
- [ ] **EA-a-4** Update skill files: remove "not available in BSD MRS release" disclaimers where data is now present; `arm-instr --op` returns real ASL *(deferred — no license)*
- [x] **EA-a-5** Add conditional eval tests that skip when no real ASL is present in cache (`instr_t32`, `instr_a32`, `search_t32` skill groups added to `eval_skill.py`)

### EA-b — T32/A32 ISA Coverage

- [x] **EA-b-1** Source T32/A32 data: hand-curated `arm-arm/T32Instructions.json` (LDR, STR, ADD, B, BL, MOV) and `arm-arm/A32Instructions.json` (LDR, STR, ADD, SUB, B, BL) from ARM DDI0487
- [x] **EA-b-2** Write `tools/build_arm_arm_index.py`: writes `cache/arm_arm/t32_operations/` and `cache/arm_arm/a32_operations/` in the same per-operation_id format as `cache/operations/`; updates `manifest.json`
- [x] **EA-b-3** Extend `tools/query_instruction.py` with `--isa t32|a32|a64` flag (default `a64` for backward compatibility)
- [x] **EA-b-4** Extend `tools/query_search.py` to include T32/A32 operation indexes (new `--isa a64|t32|a32|all` flag; default `all`)
- [x] **EA-b-5** Update `.claude/skills/arm-instr.md` to document T32/A32 routing

**Exit criteria:** ✅ `python3 tools/query_instruction.py LDR --isa t32` returns correct T32 encoding. `arm-instr --op ADC` ASL is deferred (no license). All 16 EA eval tests pass (7 T32 + 6 A32 + 3 search).

---

## Milestone EB — GIC Skill (`arm-gic`) ✅

**Goal:** Ground GIC register queries in spec data. Adds the memory-mapped GICD/GICR/ITS registers absent from AARCHMRS, with cross-references to the ICC_* system registers already in `arm-reg`.

**Source:** `https://developer.arm.com/documentation/ihi0069/latest/` (HTML); or CMSIS-SVD if available
**License:** Proprietary — `cache/gic/` must be gitignored; `gic/GIC.json` may be committed as a documentation-derived summary (consult ARM Developer Relations before publishing)
**Prerequisite:** M5; HTML extractability confirmed

### EB-0 — Data Acquisition

- [x] **EB-0-1** Check for XML/SVD source: search `ARM-software/CMSIS_5` and community IP-XACT repos for a machine-readable GIC description with field-level coverage. If found, write `tools/convert_xml_to_json.py` and use it; skip HTML path.
- [x] **EB-0-2** If no XML source: confirm ARM's HTML documentation is parseable as static HTML (not JavaScript-rendered). Fetch a sample GICD_CTLR page and verify register tables are present without a headless browser. Do not proceed to EB-0-3 until confirmed.
- [x] **EB-0-3** Write `tools/fetch_gic.py`: downloads GIC spec HTML; parses register tables using `html.parser` (stdlib); rate-limits requests; writes staging JSON per register
- [x] **EB-0-4** Extract and organise GICD, GICR, ITS registers; document GICv3-vs-GICv4 field variants
- [x] **EB-0-5** Document `ICC_*` cross-references in `gic/GIC.json` `icc_system_registers` array — do NOT duplicate data already in AARCHMRS
- [x] **EB-0-6** Produce `gic/GIC.json` and `gic/GIC_meta.json`; define and validate `gic/schema/`

### EB-1 — Cache Builder

- [x] **EB-1-1** Write `tools/build_gic_index.py`: reads `gic/GIC.json`; writes `cache/gic/GICD.json`, `cache/gic/GICR.json`, `cache/gic/GITS.json`, and `cache/gic/gic_meta.json`
- [x] **EB-1-2** Extend `cache/manifest.json` with SHA-256 of `gic/GIC.json`
- [x] **EB-1-3** Add `cache/gic/` to `.gitignore`

### EB-2 — Query Tool

- [x] **EB-2-1** Write `tools/query_gic.py`
  - `GICD_CTLR` — all fields with bit ranges, access types, reset values
  - `GICD_CTLR EnableGrp1S` — single field detail
  - `--block GICD|GICR|GITS` — all registers in a component block
  - `--list CTLR` — register names matching pattern
  - `GICD_CTLR --version v3|v4` — GICv3 vs GICv4 field variants
  - `--icc-xref ICC_IAR1_EL1` — cross-reference to AARCHMRS system register

### EB-3 — Agent Skill

- [x] **EB-3-1** Write `.claude/skills/arm-gic.md`
  - Positive triggers: GICD/GICR/ITS registers, GIC initialisation, LPI/MSI configuration, vGIC
  - Negative examples: `ICC_*` system registers → `arm-reg`; CPU interrupt pending state → `arm-reg`

### EB-4 — Search Integration

- [x] **EB-4-1** Extend `tools/query_search.py`: add `--spec gic` filter; add `"gic_register"` result type; include GIC register names in default combined search
- [x] **EB-4-2** Update `.claude/skills/arm-search.md` to route GIC results to `arm-gic`
- [x] **EB-4-3** Extend `eval_skill.py` with `gic` test cases: register existence, field bit position, access type, `--icc-xref` output, hallucination guard

**Exit criteria:** ✅ `python3 tools/query_gic.py GICD_CTLR EnableGrp0` returns correct bit position and access type. `arm-search EnableGrp1` returns GIC results. All gic eval tests pass (15 gic + 3 gic_search = 18 total).

---

## Milestone EC — CoreSight Skill (`arm-coresight`) ✅

**Goal:** Ground CoreSight debug/trace component register queries in spec data.

**Source:** `https://developer.arm.com/documentation/ihi0029/latest/` (HTML); or IP-XACT if available
**License:** Proprietary — `cache/coresight/` must be gitignored
**Prerequisite:** EB HTML extraction approach validated; M5

### EC-0 — Data Acquisition

- [x] **EC-0-1** Check for IP-XACT or SVD sources for CoreSight component registers. If found, use `tools/convert_xml_to_json.py`. If not, confirm static HTML (same check as EB-0-2).
- [x] **EC-0-2** Write `tools/fetch_coresight.py` (if HTML path): downloads CoreSight spec HTML; parses per-component register tables; handles component type scoping
- [x] **EC-0-3** Extract the common identification block (32 registers per 4 KB frame) separately from component-specific registers
- [x] **EC-0-4** Initial component priority: ETM → CTI → STM → ITM
- [x] **EC-0-5** Produce `coresight/CoreSight.json` and `coresight/CoreSight_meta.json`; define and validate `coresight/schema/`

### EC-1 — Cache Builder

- [x] **EC-1-1** Write `tools/build_coresight_index.py`: reads `coresight/CoreSight.json`; writes per-component cache files under `cache/coresight/<component>/` and `cache/coresight/cs_meta.json`; extends `cache/manifest.json`
- [x] **EC-1-2** Add `cache/coresight/` to `.gitignore`

### EC-2 — Query Tool

- [x] **EC-2-1** Write `tools/query_coresight.py`
  - `etm TRCPRGCTLR` — field layout and access type for a component register
  - `etm TRCPRGCTLR EN` — single field detail
  - `--component etm|cti|stm|itm` — all registers for a component
  - `--list-components` — all known component types
  - `--list CTRL` — register names matching pattern across all components
  - `--id-block` — common identification block registers

### EC-3 — Agent Skill

- [x] **EC-3-1** Write `.claude/skills/arm-coresight.md`
  - Positive triggers: ETM programming, trace enabling, CTI channel routing, ITM stimulus ports, STM trace, ROM table, `TRCPRGCTLR`/`TRCCONFIGR`
  - Negative examples: CPU halt via `MDSCR_EL1` → `arm-reg`; JTAG protocol → out of scope

### EC-4 — Search Integration

- [x] **EC-4-1** Extend `tools/query_search.py`: add `--spec coresight` filter; add `"cs_register"` result type
- [x] **EC-4-2** Update `.claude/skills/arm-search.md` to route CoreSight results to `arm-coresight`
- [x] **EC-4-3** Extend `eval_skill.py` with `coresight` test cases (20 coresight + 4 coresight_search = 24 tests)

**Exit criteria:** `python3 tools/query_coresight.py etm TRCPRGCTLR` returns field layout. `arm-search TRC` returns CoreSight ETM results. All coresight eval tests pass.

---

## Milestone EX — Cross-Extension Integration ✅

**Goal:** Validate all six skills work together correctly; update all documentation.

**Prerequisite:** E0 complete · EA complete · EB-3 complete · EC-3 complete

- [x] **EX-1** Test cross-skill routing for queries that span multiple specs (e.g., "How do I configure interrupt priority?" — involves GICD_CTLR + ICC_PMR_EL1)
- [x] **EX-2** Test `arm-search` with `--spec` flag across all specs (`aarchmrs`, `gic`, `coresight`, `pmu`)
- [x] **EX-3** Run full eval suite across all six skills; confirm no regressions (137/137 pass)
- [x] **EX-4** Update `README.md`, `CLAUDE.md`, and `AARCH64_AGENT_SKILL_DEV_PLAN.md` with new build commands, supported specifications, and skill usage examples

**Exit criteria:** All eval tests across all skills pass. Cross-spec routing is validated. Documentation is complete.

**Implementation notes:**
- `query_search.py --spec` extended from `{gic, coresight}` to `{aarchmrs, gic, coresight, pmu}`; `search_pmu_events()` function added
- `eval_skill.py` now has 137 tests (added `CROSS_ROUTING_TESTS`, `SEARCH_SPEC_AARCHMRS_TESTS`, `SEARCH_SPEC_PMU_TESTS`)
- Cross-routing finding: GICD_CTLR IS in AARCHMRS as `ext`-state (memory-mapped); `arm-gic` provides the GIC-specific view

---

# Phase 3 — Active Hardware Engineering

## Milestone H1 — AARCHMRS Feature-Qualified Allowlist ✅

**Goal:** Given a target architecture version and optional explicit feature flags, produce the set of
valid AArch64 operation_ids (instruction allowlist) and unavailable register names (blocklist).

**Prerequisite:** M0 (cache builder) complete · M1 (arm-feat) complete

- [x] **H1-1** Define allowlist/blocklist JSON output schema (`schema_version`, `query`, `stats`,
  `allowed_operations`, `prohibited_operations`, `allowed_registers`, `prohibited_registers`)
- [x] **H1-2** Write `tools/query_allowlist.py`
  - `--arch v9Ap4` — compute allowed/prohibited lists for the given arch version
  - `--arch v9Ap4 --feat FEAT_SVE2` — add explicit features on top of the arch baseline
  - `--arch v9Ap4 --output json` — machine-readable JSON output matching the schema
  - `--arch v9Ap4 --summary` — summary counts only (no full lists)
  - `--list-features v9Ap4` — show all FEAT_* names active at the version
  - Evaluates `IsFeatureImplemented(FEAT_X)` conditions using `&&`, `||`, `!` operators
  - Conservatively treats non-feature conditions (hardware register queries) as True
- [x] **H1-3** ASL pseudocode parser for instruction semantics simulation — **deferred**
  (blocked: requires ARM Architecture License for full MRS XML)
- [x] **H1-4** Programmatic API wrapper `query_allowlist(arch, extra_features)` so downstream
  skills (H3, H6) can call H1 without subprocess invocation
- [x] Write `.claude/skills/arm-allowlist.md` — positive/negative triggers, schema docs,
  programmatic import pattern
- [x] Add 18 eval tests to `eval_skill.py` (`ALLOWLIST_TESTS`, `--skill allowlist`): exit
  criteria, baseline instruction (ADC), SVE prohibition at v8Ap0, --list-features, JSON schema,
  error handling

**Exit criteria:** ✅ `python3 tools/query_allowlist.py --arch v9Ap4 --summary` produces correct
counts. `--output json` produces valid JSON matching the schema. 18/18 eval tests pass.

**Implementation notes:**
- Feature set derivation: features.json cache consulted for `min_version ≤ arch`; features
  with no `min_version` are always included (baseline features, e.g. `FEAT_AA64`)
- Condition evaluation: only `IsFeatureImplemented(FEAT_X)` calls are evaluated; complex
  conditions involving hardware registers (MPAMF_IDR, ERRDEVID, HaveEL, …) are treated as True
- An operation is allowed if ANY of its instruction variants satisfies the condition
- At v9Ap4: 2216/2262 operations allowed, 1398/1607 registers allowed (209 blocked)
- At v8Ap0: 1706/2262 operations allowed, 759/1607 registers allowed (848 blocked)

---

## Milestone H3 — AArch64 GDB-MCP Debugging Skill ✅

**Goal:** Let Claude directly control GDB/MI to step through generated AArch64 assembly and
verify register state against expected values.

**Prerequisite:** H1 (allowlist output for SIGILL repair integration)

- [x] **H3-1** Write `tools/gdb_session.py` — GDB/MI session manager class
  - `GdbSession(executable)` — context manager that drives GDB in MI mode over subprocess
  - `step()`, `next()`, `stepi()`, `nexti()` — execution control
  - `continue_()`, `run()` — resume and start
  - `set_breakpoint(location)`, `list_breakpoints()` — breakpoint management
  - `get_registers()` → dict (x0–x30, sp, pc, pstate)
  - `get_register(name)`, `examine_memory(addr, count)` — data inspection
  - `get_backtrace()`, `select_frame(level)` — stack analysis
  - `assert_register(reg, expected)` — raises `AssertionFailedError` on mismatch
  - `assert_registers(expected_dict)` — batch assertion; returns list of failures
  - `run_assertion_suite(steps)` — orchestrates a JSON step/assert sequence
  - `suggest_sigill_repair(arch, pc)` — static helper; emits H1 query command
  - `SigilDetectedError`, `AssertionFailedError`, `GdbNotAvailableError` exceptions
  - Auto-discovers `gdb-multiarch` then `gdb`; respects `ARM_GDB_PATH` env var
- [x] **H3-2** Write `tools/query_gdb.py` — CLI tool for GDB debugging operations
  - `--check` — verify gdb-multiarch is installed
  - `--version` — print GDB version
  - `<binary> --break LOCATION --step N --registers` — run to breakpoint, step, inspect
  - `<binary> --assert "x0=0 x1=0x42"` — assert register values; exits non-zero on failure
  - `<binary> --nexti N` — step N machine instructions (step-over)
  - `<binary> --backtrace` — print call stack
  - `<binary> --suite SUITE.json` — run a JSON step/assert batch suite
  - `--sigill-hint ARCH [--pc ADDR]` — print H1-based SIGILL repair hint
  - Exit code 2 on SIGILL
- [x] **H3-3** Write `.claude/skills/arm-gdb.md` — positive/negative triggers, suite format,
  SIGILL repair workflow, programmatic API docs, register reference table
- [x] **H3-4** Add 14 eval tests to `eval_skill.py` (`GDB_TESTS`, `--skill gdb`):
  CLI sanity, sigill-hint content, module import, API attribute checks (no GDB install needed)

**Exit criteria:** ✅ `python3 tools/query_gdb.py --sigill-hint v9Ap4` emits H1 query command.
`python3 tools/eval_skill.py --skill gdb` — 14/14 tests pass with no GDB installation required.

---

## Milestone H4 — QEMU-AArch64 Emulation Automation ✅

**Goal:** Auto-generate QEMU launch scripts and run AArch64 binaries in user-mode QEMU,
classifying exit conditions for integration with H3 (GDB) and H5 (re-compile).

**Prerequisite:** H3 (for routing SIGILL/SIGSEGV failures back to GDB)

- [x] **H4-1** Write `tools/gen_qemu_launch.py` — QEMU launch-script generator and runner
  - `--mode user [--cpu CPU] [--output FILE]` — generate user-mode launch script
  - `--mode system [--cpu CPU] [--memory MEM] [--accel tcg|kvm|hvf]` — system-mode script
  - `--run BINARY [--cpu CPU] [--timeout N] [--json]` — run binary and report result
  - `--check` — verify qemu-aarch64 / qemu-system-aarch64 is installed
  - `--list-cpus` — list available AArch64 CPU models with descriptions
  - System-mode: `--kernel`, `--drive`, `--accel kvm|hvf|tcg`
  - User-mode: `--static` (qemu-aarch64-static for static binaries)
  - `QemuResult` class: `exit_code`, `stdout`, `stderr`, `elapsed`, `classification`
    (`pass`/`fail`/`sigill`/`sigsegv`/`timeout`)
  - `run_binary(binary, cpu, timeout)` — programmatic API
  - `gen_user_mode_script(cpu, ...)` and `gen_system_mode_script(...)` — script generators
  - Respects `ARM_QEMU_USER_PATH` and `ARM_QEMU_SYSTEM_PATH` env vars
  - SIGILL exit code 132; SIGSEGV exit code 139; timeout exit code 124
- [x] **H4-2** CPU catalogue: 11 representative CPUs (max, cortex-a35/a53/a55/a57/a72/a76/a710,
  neoverse-n1/v1, cortex-x1) with architecture version and use-case descriptions
- [x] **H4-3** Write `.claude/skills/arm-qemu.md` — positive/negative triggers, exit-condition
  routing table, SIGILL repair workflow, CPU reference, programmatic API docs
- [x] **H4-4** Add 23 eval tests to `eval_skill.py` (`QEMU_TESTS`, `--skill qemu`):
  script generation correctness, QemuResult classification, CPU catalogue, import checks

**Exit criteria:** ✅ `python3 tools/gen_qemu_launch.py --mode system --cpu cortex-a710`
generates a valid QEMU launch script. `QemuResult` correctly classifies SIGILL/SIGSEGV/pass/
timeout. `python3 tools/eval_skill.py --skill qemu` — 23/23 tests pass.

---

## Milestone H5 — Cross-Compilation & Static Linking ✅

**Goal:** Manage the `aarch64-linux-gnu-gcc` toolchain to produce AArch64 binaries that run
in H4's QEMU environment; integrate 20 compile-error auto-repair rules.

**Prerequisite:** H4 (QEMU integration for test-compile-run loop)

- [x] **H5-1** Write `tools/setup_cross_compile.py` — cross-compilation setup and build tool
  - `--check` — detect cross-compiler and auto-detect link strategy
  - `--setup` — install `gcc-aarch64-linux-gnu` via apt
  - `--compile SOURCE [--out BINARY] [--arch VERSION] [--feat FEAT_X …]` — cross-compile
  - `--link auto|static|dynamic|musl` — link strategy selector
  - `--march-flag [--arch VERSION] [--feat FEAT_X …]` — print -march flag
  - `--link-strategy` — show decision table + auto-detected strategy
  - `--repair-hint ERROR_MSG` — look up auto-repair rules
  - `--list-archs` — all 17 supported version strings
  - `--list-feats` — all 21 FEAT_* → +extension mappings
  - `arch_to_march_flag(arch, features)` — Python API; raises `ValueError` for unknown arch
  - `find_repair_rules(error_msg)` — returns matching rules from 20-rule library
  - `cross_compile(source, out, arch, features, link, extra_flags)` — Python API
  - `detect_link_strategy()` — auto-detects `static`/`dynamic`/`musl`
  - Respects `ARM_CC_AARCH64`, `ARM_CXX_AARCH64`, `ARM_SYSROOT` env vars
- [x] **H5-2** Architecture version → `-march` mapping: all 17 versions (v8Ap0–v9Ap6)
- [x] **H5-3** FEAT_* → `-march` extension mapping: 21 extensions (SVE, SVE2, SME, SME2,
  FP16, LSE, LSE2, DOTPROD, BF16, I8MM, MTE, MTE2, BTI, PAUTH, SSBS, RNG, CRC32,
  PMULL, SHA1, SHA256, SHA3, SHA512)
- [x] **H5-4** 20-rule compile-error auto-repair library (R01–R20): dynamic linker missing,
  library not found, libc static, illegal instruction, -march unrecognised, wrong target,
  undefined reference, implicit declaration, undeclared symbol, relocation truncated,
  unsupported relocation, ABI mismatch, stack alignment, data alignment, SVE/SME feature
  errors, NEON range, PAC/BTI enable errors, generic ld failure
- [x] Write `.claude/skills/arm-cross.md` — positive/negative triggers, arch/feat tables,
  link strategy decision tree, repair rules reference, programmatic API docs
- [x] Add 27 eval tests to `eval_skill.py` (`CROSS_TESTS`, `--skill cross`):
  CLI sanity, --march-flag correctness, repair rule matching, API correctness,
  REPAIR_RULES count validation, ValueError for unknown arch

**Exit criteria:** ✅ `python3 tools/setup_cross_compile.py --march-flag --arch v9Ap0 --feat FEAT_SVE2`
outputs `-march=armv9-a+sve2`. 20/20 repair rules present. `--repair-hint "illegal instruction"`
returns R04. `python3 tools/eval_skill.py --skill cross` — 27/27 tests pass.

---

## Milestone H6 — Advanced ISA Optimization (SVE2/SME/PAC/BTI/MTE) ✅

**Goal:** Generate high-performance and security-hardened AArch64 code using the latest ISA
extensions (SVE2, SME, PAC, BTI, MTE); enforce feature gating through the H1 allowlist API.

**Prerequisite:** H1 (feature-qualified allowlist), H5 (cross-compilation `-march` flags)

- [x] **H6-1** Build SVE2/SME code-generation template library
  - 8 SVE2 templates: dotproduct, matrix-multiply, convolution, reduce, gather, scatter,
    scan, permute — all using `<arm_sve.h>` intrinsics with predicated VLA loops
  - 4 SME templates: matmul, accumulate, transpose, int8-matmul — all using `<arm_sme.h>`
    with `__arm_new("za")` streaming-mode functions
  - `list_templates(category)` — Python API; `--list-templates [--category sve2|sme]` CLI
  - `generate_template(name, arch)` — Python API; `--template NAME --arch VERSION` CLI
  - Feature gating: every template checks feature availability via H1 `features_for_arch()`
  - Generated code includes correct `-march` flag comments via H5 `arch_to_march_flag()`
- [x] **H6-2** Implement PAC/BTI auto-insertion (function prologue/epilogue)
  - `insert_pac_bti(asm_text, arch)` — Python API; `--auto-pac-bti --arch VERSION` CLI
  - PACIASP inserted at function entry, AUTIASP before RET (if FEAT_PAuth available)
  - BTI c inserted at function entry (if FEAT_BTI available at v8Ap5+)
  - No-op at v8Ap0 (neither PAC nor BTI available)
  - Both PAC and BTI at v9Ap0+ (both features architecturally mandated)
- [x] **H6-3** Build MTE tag-management helper utilities
  - `generate_mte_helpers(arch)` — Python API; `--mte-helpers --arch VERSION` CLI
  - C header with `<arm_acle.h>` intrinsic wrappers: IRG (`mte_create_tag`),
    STG (`mte_set_tag`), LDG (`mte_get_tag`), ADDG (`mte_increment_tag`)
  - Region tagging (`mte_tag_region`) and pool allocation (`mte_alloc_pool`) helpers
  - Feature-gated: only available at v8Ap5+ (FEAT_MTE)
- [x] **H6-4** Define security-extension usage best-practice checklist (18 rules for H7)
  - 5 PAC rules (R01–R05): prologue signing, epilogue auth, key diversity, AUT before deref, RETAA
  - 5 BTI rules (R06–R10): indirect call landing pads, jump targets, GP bit, PAC+BTI combo, no mid-func jump
  - 5 MTE rules (R11–R15): tag-on-alloc, granule alignment, clear-on-free, SCTLR_EL1.TCF, ADDG sub-objects
  - 3 general rules (R16–R18): stack tagging, defense-in-depth combo, enhanced PAC2
  - `list_security_rules(category)` — Python API; `--list-rules [--category pac|bti|mte|general]` CLI
  - JSON export for H7 linter integration: `--list-rules --output json`
- [x] Write `.claude/skills/arm-isa-opt.md` — positive/negative triggers, template tables,
  security rules reference, extension availability table, programmatic API docs
- [x] Add 42 eval tests to `eval_skill.py` (`ISA_OPT_TESTS`, `--skill isa_opt`):
  basic invocation (4), template generation (7), feature gating (7), PAC/BTI insertion (4),
  MTE helpers (6), security rules (5), programmatic API (6), error handling (3)

**Exit criteria:** ✅ `python3 tools/isa_optimize.py --list-templates` shows 12 templates
(8 SVE2 + 4 SME). `--template sve2-dotproduct --arch v9Ap4` produces valid C with `svdot_s32`.
`--auto-pac-bti --arch v9Ap0` inserts PACIASP/AUTIASP/BTI c. `--mte-helpers --arch v8Ap5`
produces valid C header with MTE intrinsics. `--list-rules` shows 18 security rules.
`python3 tools/eval_skill.py --skill isa_opt` — 42/42 tests pass.

---

## Milestone H7 — Linter-in-the-Loop (VIXL) ✅

**Goal:** Integrate a lint-based verification gate into the code-generation loop.
Provide 50 AArch64-specific lint rules, auto-repair suggestions, and a lint-green
blocking gate. Optionally integrates with VIXL external linter when available.

**Depends on:** H6 (security rules R01–R18), H1 (spec data)

- [x] **H7-1** Deploy VIXL Linter integration interface
  - `check_vixl()` checks for `vixl-lint` or `aarch64-linux-gnu-objdump` on PATH
  - Falls back to built-in rule engine when external tools not available
  - CLI: `--check-vixl` (text/json output)
- [x] **H7-2** Define AArch64-specific lint rule set (50 rules)
  - 18 security rules (L01–L18): imported from H6 SECURITY_RULES (R01–R18)
  - 8 alignment rules (L19–L26): SP alignment, LDP/STP, atomics, SVE, SIMD
  - 10 register constraint rules (L27–L36): XZR writeback, STXR overlap, FP/LR/X18
  - 8 branch/control flow rules (L37–L44): dead code, TBZ/TBNZ, ISB, BLR
  - 6 encoding constraint rules (L45–L50): immediate ranges, shift amounts, system registers
  - Severity levels: error (definitely wrong), warning (likely wrong), info (style)
  - Feature-gated: `--arch VERSION` filters rules by min_arch
- [x] **H7-3** Implement auto-repair suggestion generator
  - `suggest_repairs(violations)` maps each violation to a code edit suggestion
  - Context-specific repairs: SP alignment rounding, register substitution, etc.
  - JSON output includes `repairs` array with original/suggested/explanation
- [x] **H7-4** Wire Lint-Green check into CI/CD as a blocking merge gate
  - `lint_green(text, arch)` returns `{green: bool, errors: N, warnings: N, info: N}`
  - CLI: `--lint-green FILE` exits 0 only if zero errors and zero warnings
  - Verification gate flow: Lint → QEMU functional test → GDB debug → Merge
- [x] Write `.claude/skills/arm-linter.md` — positive/negative triggers, rule tables,
  verification gate flow, programmatic API docs
- [x] Add 31 eval tests to `eval_skill.py` (`LINTER_TESTS`, `--skill linter`):
  basic invocation (8), JSON output (2), VIXL integration (2), lint detection (4),
  lint-green gate (2), auto-repair (2), feature gating (2), programmatic API (6),
  error handling (3)

**Exit criteria:** ✅ `python3 tools/isa_linter.py --list-rules` shows 50 rules
(18 security + 8 alignment + 10 register + 8 branch + 6 encoding).
`--lint test.s --arch v9Ap0` detects violations with repair suggestions.
`--lint-green clean.s` exits 0. `--lint-green bad.s` exits 1.
`python3 tools/eval_skill.py --skill linter` — 31/31 tests pass.

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
                                                              │
              H1 (Allowlist) ─────────────────────────────────┤
              H3 (GDB-MCP)  ──────────┐                      │
              H4 (QEMU)     ──────────┤                      │
              H5 (Cross)    ──────────┤                      │
              H6 (ISA Opt)  ──────────┤─────── H7 (Linter) ──┤
                                      │                      │
                                      └── H8 (Multi-agent)  ─┘
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
