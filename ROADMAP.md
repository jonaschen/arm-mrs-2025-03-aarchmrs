# AArch64 Agent Skills — Roadmap

> See `AARCH64_AGENT_SKILL_DEV_PLAN.md` for full design rationale behind each decision.

---

## Milestone 0 — Foundation ✅

**Goal:** Repo infrastructure required by all later milestones.

- [x] **M0-1** Create `.gitignore` with `cache/` entry
- [x] **M0-2** Create `tools/` directory
- [x] **M0-3** Write `tools/build_index.py`
  - Parse `Features.json` → `cache/features.json`
  - Parse `Instructions.json` → `cache/operations/OPERATION_ID.json` (operation data merged with linked instruction node encodings via two-pass bit-level merge algorithm)
  - Parse `Registers.json` → `cache/registers/NAME__STATE.json` (sanitize `<n>` with following `_` absorbed → `_n_`; include `index_variable` and `indexes`)
  - Write `cache/registers_meta.json` (name → [{state, cache_key}] index)
  - Write `cache/manifest.json` (SHA-256 hashes of all three source files)
  - Wipe and recreate `cache/` on each run to prevent stale files
- [x] **M0-4** Validate generated cache: spot-check `SCTLR_EL1__AArch64.json`, `ADC.json`, `ADD_addsub_imm.json`, `cache/features.json`
- [x] **M0-5** Document cache rebuild command in `CLAUDE.md`

**Exit criteria:** ✅ `python tools/build_index.py` produces 1,607 register files, 2,262 operation files, `features.json`, `registers_meta.json`, and `manifest.json` with no errors.

---

## Milestone 1 — Feature Skill (`arm-feat`) ✅

**Goal:** Ground feature/extension queries in spec data. First milestone because the data is small, complete, and foundational for capability-conditional code.

- [x] **M1-1** Write `tools/query_feature.py`
  - `query_feature.py FEAT_SVE` — feature entry + rendered constraints
  - `query_feature.py FEAT_SVE --deps FEAT_FP16` — yes/conditional/no dependency answer + full constraint tree; handles compound RHS (`FEAT_X --> (A && B)`)
  - `query_feature.py --version v9Ap2` — AST traversal for `FEAT_X --> vNApM` patterns, filtered by version ceiling
  - `query_feature.py --list SVE` — name pattern search
  - On missing cache: prints error and exits non-zero
  - On stale cache: prints warning, continues
- [x] **M1-2** Write `.claude/skills/arm-feat.md`
  - Positive/negative trigger examples; routing guards
  - Path resolution via `ARM_MRS_CACHE_DIR` or `git rev-parse --show-toplevel`
- [x] **M1-3** Manual test: `FEAT_SVE --deps FEAT_FP16` → Yes; `--deps FEAT_PMUv3p1` → Conditional; `--deps FEAT_NEON` → No; `--version v9Ap2` → 261 features; `--list SVE` → 19 results

**Exit criteria:** ✅ Skill returns spec-grounded answers without loading full `Features.json` into context.

---

## Milestone 2 — Register Skill (`arm-reg`) ✅

**Goal:** Ground register field, value, and access queries in spec data. Highest firmware/driver value.

- [x] **M2-1** Write `tools/query_register.py`
  - `query_register.py SCTLR_EL1` — all named fields with bit ranges, field types, allowed values; default to AArch64 when multiple states match; note when AArch32 variant also exists
  - `query_register.py SCTLR_EL1 UCI` — single field detail
  - `query_register.py SCTLR_EL1 UCI --values` — full value enumeration and meanings
  - `query_register.py SCTLR_EL1 --access` — all accessor types and encodings (`SystemAccessor`, `MemoryMapped`, `ExternalDebug`, `SystemAccessorArray`)
  - `query_register.py --list EL1 [--state AArch64|AArch32|ext]` — name pattern search with optional state filter
  - Parameterized register resolution: `DBGBCR2_EL1` → normalize digit → load `DBGBCR_n_EL1__AArch64.json`, note the requested instance index
  - On missing cache: same error as M1-1
- [x] **M2-2** Write `.claude/skills/arm-reg.md`
  - Positive triggers: register field layout, bit positions, field values, MRS/MSR encoding for a specific register
  - Negative examples: "how does ADC work?" (→ `arm-instr`), "does this CPU support SVE?" (→ `arm-feat`)
  - Path resolution: same pattern as M1-2
- [x] **M2-3** Manual test: SCTLR_EL1 fields, TCR_EL1 access encoding, DBGBCR2_EL1 parameterized lookup, `--list EL2 --state AArch64`; all pass; 12 eval tests (100%)

**Exit criteria:** ✅ Skill returns correct field layout and accessor encoding for common AArch64 system registers without loading `Registers.json` into context.

---

## Milestone 3 — Search Skill (`arm-search`) ✅

**Goal:** Cross-cutting discovery when the user doesn't know which module to query.

- [x] **M3-1** Write `tools/query_search.py`
  - `query_search.py TCR` — search `registers_meta.json` + operation key index; returns grouped plain-text results
  - `query_search.py --reg EL2 [--state AArch64]` — register-only search with state filter
  - `query_search.py --op ADD` — operation-only search
- [x] **M3-2** Write `.claude/skills/arm-search.md`
  - Instructs skill to follow up matching results with a targeted `arm-reg`, `arm-feat`, or `arm-instr` call
- [x] **M3-3** Manual test: "find all EL2 registers" (131 AArch64 results), "anything related to TCR" (15 results incl. TCR_EL1); 5 eval tests (100%)

**Exit criteria:** ✅ Search returns structured results and correctly hands off to the right module skill.

---

## Milestone 4 — Instruction Skill (`arm-instr`) ✅

**Goal:** Ground instruction behavior and encoding queries in spec data.

- [x] **M4-1** Write `tools/query_instruction.py`
  - `query_instruction.py ADC` — operation title, brief, all encoding variants (instruction names linked via `operation_id`)
  - `query_instruction.py ADC --enc` — encoding bit fields and widths for all variants
  - `query_instruction.py ADC --op` — ASL pseudocode blocks (null in BSD release — skill notes unavailability); `--full` flag for complete output
  - `query_instruction.py --list ADD` — all `operation_id` values containing the pattern
  - Handles null `decode` field gracefully
- [x] **M4-2** Write `.claude/skills/arm-instr.md`
  - Positive triggers: instruction behavior, encoding bit layout, assembly syntax, ASL pseudocode
  - Negative examples: "how do I read SCTLR_EL1?" (→ `arm-reg --access`), "does the CPU support SVE?" (→ `arm-feat`)
  - MRS ambiguity clarified in skill file
  - Path resolution: same pattern as M1-2
- [x] **M4-3** Manual test: ADC encoding (sf/Rd/Rn/Rm operands correct), ADD --list (129 results), MRS --enc; 11 eval tests (100%)

**Note:** ASL pseudocode (`decode`, `operation`) is `null`/`// Not specified` across all 2,262 operations in the BSD MRS release. The skill acknowledges this explicitly.

**Exit criteria:** ✅ Skill returns correct instruction encoding and assembly templates without loading `Instructions.json` into context.

---

## Milestone E — Skill Correctness Evaluation ✅

**Goal:** Provide a reproducible method to measure skill correctness and prove the skill eliminates ARM AArch64 hardware hallucination.

- [x] **ME-1** Write `tools/eval_skill.py`
  - Battery of 23 ground-truth test cases for the `arm-feat` skill
  - Test categories: feature existence, known non-existence (hallucination detection), `min_version` accuracy, dependency classification (yes/conditional/no), version-to-features count, list/search count and content, anti-hallucination sentinel (BSD prose disclaimer)
  - Checks are derived from: ROADMAP §M1-3 manual tests, DESIGN.md verified examples, and ARM MRS source data
  - Computes a percentage score; exits non-zero on any failure
  - Framework is extensible: add a list to `ALL_SKILLS` as `arm-reg`, `arm-instr`, and `arm-search` are implemented
  - One notable test: the ARM spec uses `FEAT_AdvSIMD`, not the marketing name `FEAT_NEON`; the eval verifies this distinction to catch a common agent hallucination
- [x] **ME-2** Run evaluation: all 51 tests pass (100%) against v9Ap6-A, Build 445
  - feat: 23 tests, reg: 12 tests, search: 5 tests, instr: 11 tests

**Exit criteria:** ✅ `python3 tools/eval_skill.py` exits 0 with "ALL TESTS PASSED" message confirming all facts match the official ARM specification.

---

## Milestone 5 — Integration and Hardening

**Goal:** Cross-skill polish and real-world validation.

- [ ] **M5-1** Test skill routing with ambiguous queries; add routing examples to each skill file where gaps are found
- [ ] **M5-2** Validate that all skills correctly emit "Description not available in BSD MRS release" for null fields rather than synthesizing prose
- [ ] **M5-3** Document `ARM_MRS_CACHE_DIR` env var in `CLAUDE.md` for multi-project use
- [ ] **M5-4** Update `CLAUDE.md` with final `build_index.py` invocation and skill usage examples
- [ ] **M5-5** Update `AARCH64_AGENT_SKILL_DEV_PLAN.md` with any decisions made during implementation that deviated from the plan

---

## Dependency Graph

```
M0 (Foundation)
 ├── M1 (arm-feat)      ← no dependency on M2/M3/M4
 │       └── ME (Eval)  ← tests arm-feat; extends as M2/M3/M4 are added
 ├── M2 (arm-reg)       ← no dependency on M1/M3/M4
 ├── M3 (arm-search)    ← depends on M1 + M2 cache being built (M0)
 └── M4 (arm-instr)     ← no dependency on M1/M2/M3
         └── M5 (Integration) ← depends on all of M1–M4
```

M1, M2, and M4 can be developed in parallel after M0 completes. M3 can start as soon as M0 is done (it only needs the index files, not the skill implementations). M5 requires all four skills to exist.

---

## Not in Scope

- Auto-rebuild of cache inside a skill invocation (too slow for interactive use)
- Prose description synthesis (BSD MRS omits all prose; skills must acknowledge this)
- AArch32-only workflows (AArch64 is the default; AArch32 accessible via `--state` flag)
- Third-party Python dependencies (stdlib only: `json`, `hashlib`, `os`, `argparse`, Python 3.8+)
