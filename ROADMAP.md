# AArch64 Agent Skills — Roadmap

> See `AARCH64_AGENT_SKILL_DEV_PLAN.md` for full design rationale behind each decision.

---

## Milestone 0 — Foundation

**Goal:** Repo infrastructure required by all later milestones.

- [ ] **M0-1** Create `.gitignore` with `cache/` entry
- [ ] **M0-2** Create `tools/` directory
- [ ] **M0-3** Write `tools/build_index.py`
  - Parse `Features.json` → `cache/features.json`
  - Parse `Instructions.json` → `cache/operations/OPERATION_ID.json` (operation data merged with linked instruction node encodings)
  - Parse `Registers.json` → `cache/registers/NAME__STATE.json` (sanitize `<n>` → `_n_` in filenames; include `index_variable` and `indexes`)
  - Write `cache/registers_meta.json` (name → [{state, cache_key}] index)
  - Write `cache/manifest.json` (SHA-256 hashes of all three source files)
- [ ] **M0-4** Validate generated cache: spot-check `SCTLR_EL1__AArch64.json`, `ADC.json`, `cache/features.json`
- [ ] **M0-5** Document cache rebuild command in `CLAUDE.md`

**Exit criteria:** Running `python tools/build_index.py` produces a complete `cache/` with no errors. All three source files are represented.

---

## Milestone 1 — Feature Skill (`arm-feat`)

**Goal:** Ground feature/extension queries in spec data. First milestone because the data is small, complete, and foundational for capability-conditional code.

- [ ] **M1-1** Write `tools/query_feature.py`
  - `query_feature.py FEAT_SVE` — feature entry + raw constraints
  - `query_feature.py FEAT_SVE --deps` — dependency tree (walk both `parameters[i].constraints` and top-level `constraints`; answer direct yes/no before showing tree)
  - `query_feature.py --version v9Ap2` — AST traversal to find `FEAT_X --> vNApM` patterns, filtered by version ceiling
  - `query_feature.py --list SVE` — name pattern search
  - On missing cache: print `Cache not found. Run: python tools/build_index.py` and exit non-zero
  - On stale cache (manifest hash mismatch): print warning, continue
- [ ] **M1-2** Write `.claude/skills/arm-feat.md`
  - Include positive trigger examples and negative examples (routing guards)
  - Path resolution: check `ARM_MRS_CACHE_DIR` env var, fall back to `git rev-parse --show-toplevel`
- [ ] **M1-3** Manual test: "Does FEAT_SVE require FEAT_FP16?", "What features does v9Ap2 introduce?"

**Exit criteria:** Skill returns spec-grounded answers without loading full `Features.json` into context.

---

## Milestone 2 — Register Skill (`arm-reg`)

**Goal:** Ground register field, value, and access queries in spec data. Highest firmware/driver value.

- [ ] **M2-1** Write `tools/query_register.py`
  - `query_register.py SCTLR_EL1` — all named fields with bit ranges, field types, allowed values; default to AArch64 when multiple states match; note when AArch32 variant also exists
  - `query_register.py SCTLR_EL1 UCI` — single field detail
  - `query_register.py SCTLR_EL1 UCI --values` — full value enumeration and meanings
  - `query_register.py SCTLR_EL1 --access` — all accessor types and encodings (handle all six `_type` variants: `SystemAccessor`, `MemoryMapped`, `ExternalDebug`, `SystemAccessorArray`, `BlockAccess`, `BlockAccessArray`)
  - `query_register.py --list EL1 [--state AArch64|AArch32|ext]` — name pattern search with optional state filter
  - Parameterized register resolution: `DBGBCR2_EL1` → normalize digit sequence → load `DBGBCR_n_EL1__AArch64.json`, note the requested instance index
  - On missing cache: same error as M1-1
- [ ] **M2-2** Write `.claude/skills/arm-reg.md`
  - Positive triggers: register field layout, bit positions, field values, MRS/MSR encoding for a specific register
  - Negative examples: "how does ADC work?" (→ `arm-instr`), "does this CPU support SVE?" (→ `arm-feat`)
  - Path resolution: same pattern as M1-2
- [ ] **M2-3** Manual test: SCTLR_EL1 fields, TCR_EL1 access encoding, DBGBCR2_EL1 parameterized lookup, `arm-reg-list EL2 --state AArch64`

**Exit criteria:** Skill returns correct field layout and accessor encoding for common AArch64 system registers without loading `Registers.json` into context.

---

## Milestone 3 — Search Skill (`arm-search`)

**Goal:** Cross-cutting discovery when the user doesn't know which module to query.

- [ ] **M3-1** Write `tools/query_search.py`
  - `query_search.py TCR` — search `registers_meta.json` + operation key index; return uniform JSON envelope:
    ```json
    {"query": "TCR", "results": [
      {"type": "register", "name": "TCR_EL1", "state": "AArch64"},
      {"type": "operation", "name": "TCANCEL"}
    ]}
    ```
  - `query_search.py --reg EL2 [--state AArch64]` — register-only search with state filter
- [ ] **M3-2** Write `.claude/skills/arm-search.md`
  - Instruct skill to follow up matching results with a targeted `arm-reg`, `arm-feat`, or `arm-instr` call for the entity the user actually wants
- [ ] **M3-3** Manual test: "find all EL2 registers", "anything related to TCR"

**Exit criteria:** Search returns structured results and correctly hands off to the right module skill.

---

## Milestone 4 — Instruction Skill (`arm-instr`)

**Goal:** Ground instruction behavior and encoding queries in spec data.

- [ ] **M4-1** Write `tools/query_instruction.py`
  - `query_instruction.py ADC` — operation title, brief, all encoding variants (instruction names linked via `operation_id`)
  - `query_instruction.py ADC --enc` — encoding bit fields and widths for all variants
  - `query_instruction.py ADC --op` — ASL pseudocode, truncated to 60 lines by default; `decode` block and `operation` block returned separately; `--full` flag for complete output
  - `query_instruction.py --list ADD` — all `operation_id` values containing the pattern
  - Handle optional `decode` field (null when no shared decode block)
- [ ] **M4-2** Write `.claude/skills/arm-instr.md`
  - Positive triggers: instruction behavior, encoding bit layout, assembly syntax, ASL pseudocode
  - Negative examples: "how do I read SCTLR_EL1?" (→ `arm-reg-access`), "does the CPU support SVE?" (→ `arm-feat`)
  - Clarify MRS ambiguity: "MRS instruction encoding" → `arm-instr MRS`; "encoding used to select a register via MRS" → `arm-reg-access REG_NAME`
  - Path resolution: same pattern as M1-2
- [ ] **M4-3** Manual test: ADC encoding, ADD variants list, FADD_advsimd operation (truncated + full), MRS instruction encoding

**Exit criteria:** Skill returns correct instruction encoding and operation semantics without loading `Instructions.json` into context.

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
