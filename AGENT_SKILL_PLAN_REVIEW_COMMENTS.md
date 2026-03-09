# Review Comments: AARCH64_AGENT_SKILL_DEV_PLAN.md

**Reviewer:** Copilot  
**Date:** 2026-03-09  
**Document reviewed:** `AARCH64_AGENT_SKILL_DEV_PLAN.md`  

---

## Overall Assessment

The plan is well-structured and practically grounded. It correctly acknowledges the limitations of the BSD MRS release (no prose, mostly-null description fields) and addresses the core engineering challenge — that loading 100+ MB of JSON is infeasible in a single context — with a sensible cache/index strategy.

The four-module breakdown maps naturally to the three source files, and the phased implementation (bootstrap → query tools → skills) is the right order. The key design decision section is a strength: it documents trade-offs explicitly rather than leaving them implicit.

The following comments aim to sharpen the plan and surface gaps before implementation begins.

---

## Section-by-Section Comments

### Data Reality Check

**C-01 — Feature constraint data lives in two places (schema gap)**  
The plan describes Features.json as containing "constraint expressions" but the actual schema (`schema/Features.json`) stores constraints in *two* separate locations:
- `parameters[i].constraints` — per-feature constraints attached to each `Parameters.Boolean` entry
- top-level `constraints` — globally scoped constraint expressions

The `cache/features.json` extractor and the `arm-feat-deps` renderer must walk both arrays. Failing to include global constraints will silently miss some dependency edges.

**C-02 — SystemAccessor schema has a deprecated and a current form**  
`schema/Accessors/SystemAccessor.json` defines two `oneOf` variants:
1. Deprecated form: uses a `_type` enum of specific instruction names (e.g., `Accessors.A64.MRS`, `Accessors.A32.MCR`) and no `name` property.
2. Current form: `_type: "Accessors.SystemAccessor"` with a `name` property.

Both formats appear in `Registers.json`. The `arm-reg-access` query tool must handle both or it will drop accessors from older-format registers.

**C-03 — Operation.json fields are all required**  
The plan states operations have `brief`/`description` present, which is correct. The schema (`schema/Instruction/Operation.json`) marks `operation`, `brief`, `title`, and `description` as all required. Importantly, `decode` (the shared decode ASL block) is *optional* (null when no shared decode). The indexing script should not assume `decode` is always present.

---

### Module Plan

**C-04 — `arm-instr-enc` identifier format is undefined**  
The plan uses `arm-instr-enc ADD_immediate` as an example but the instruction tree in the data uses hierarchical path identifiers (e.g., `A64.data_processing.arithmetic.immediate.ADD`). There is no `ADD_immediate` key. Either:
- Clarify that the argument is the instruction's internal node path, or
- Define a lookup by mnemonic + variant type (e.g., `arm-instr-enc ADD --variant immediate`), or
- Build a secondary index mapping short forms to full paths.

Without this clarification, users will be confused about what to pass.

**C-05 — `arm-feat-version` requires non-trivial AST traversal**  
`arm-feat-version v9Ap2` is described as returning "all features introduced at or before this version." In the data, the version relationship is encoded as AST constraint expressions of the form:

```json
{
  "_type": "AST.BinaryOp",
  "left":  { "_type": "AST.Identifier", "value": "FEAT_SVE" },
  "op":    "-->",
  "right": { "_type": "AST.Identifier", "value": "v9Ap2" }
}
```

To answer this query, the script must parse every constraint, identify implications `FEAT_X --> vNApM`, collect the minimum version for each feature, then filter by the requested version ceiling. The plan should describe this algorithm explicitly, since a naive string search on the JSON would miss nested expressions.

**C-06 — `arm-reg-list` should support state filtering**  
`arm-reg-list EL1` is described as matching by name pattern. However, many registers exist in both AArch32 and AArch64 states. The Register schema has a `state` field (`"AArch64"`, `"AArch32"`, `"ext"`). Useful extensions:
- `arm-reg-list EL1 --state AArch64` to filter by architecture state
- `arm-reg-list --state ext` to list all memory-mapped external registers

Without state filtering, firmware developers querying EL2/EL3 registers may get unexpected AArch32 results mixed in.

**C-07 — `arm-instr-op` can return very large output**  
The plan says `arm-instr-op FADD_advsimd` returns "Full operation text (ASL pseudocode)." For complex vector/SVE operations, the ASL pseudocode can be hundreds of lines. A context window of 128K tokens can hold this, but it increases prompt cost significantly. Consider:
- A `--summary` flag that returns only the first N lines of the operation
- Separating `decode` (argument setup) from `operation` (execution logic) so users can request each independently

**C-08 — Parameterized register names are not addressed**  
Many registers in `Registers.json` are parameterized (e.g., `DBGBCR<n>_EL1`, `ICH_LR<n>_EL2`). The cache plan creates one file per register by name, but parameterized registers use `<n>` in their name. The plan should describe:
- How the cache file is named (e.g., `DBGBCR_n_EL1.json` or `DBGBCR<n>_EL1.json`)
- Whether the instances list (the `instances` field in Register schema) is included in the cache
- How `arm-reg DBGBCR2_EL1` resolves to the parameterized register

**C-09 — Missing field-value enumeration sub-command**  
The use-case table covers field existence and bit positions but not field values. For firmware development, the most common lookup is: "What does setting bit X to value Y mean?" The `Fieldset.values` array contains `Fields.Field` objects that include allowed value meanings. A `arm-reg-field-values SCTLR_EL1 UCI` command (or equivalent) would be high-value for driver developers.

**C-10 — AArch32 vs AArch64 disambiguation throughout**  
Several modules interact with registers that have both AArch32 and AArch64 variants (e.g., `SCTLR` exists in both states). The plan does not describe how the skill should resolve a bare name like `arm-reg SCTLR` that matches multiple registers. A tie-breaking convention (prefer AArch64, show both, require explicit state flag) should be defined.

---

### Implementation Phases

**C-11 — Phase 0 has no cache validation mechanism**  
The plan notes that `cache/` is rebuilt when "MRS is updated." There is no mechanism proposed to detect if the cache is stale relative to the source JSON files. Consider:
- Writing a manifest file (`cache/manifest.json`) with the source file modification timestamps or content hashes at build time
- Having query scripts check the manifest and emit a warning (not a failure) if the source is newer than the cache

**C-12 — Phase 0 memory requirements for Instructions.json are unaddressed**  
Parsing the 38 MB `Instructions.json` into a Python dict will require approximately 300–600 MB of RAM (Python's memory overhead for large dicts is typically 8–15× the raw JSON size). This is acceptable on a developer machine but worth documenting as a requirement, especially if the plan later targets low-RAM environments (CI containers, Codespaces free tier).

**C-13 — No `.gitignore` entry is mentioned for `cache/`**  
The plan says `cache/` is gitignored, but there is no existing `.gitignore` in the repository root. Phase 0 should include creating or updating `.gitignore` to add `cache/` before any developer accidentally commits hundreds of megabytes of generated files.

**C-14 — Skills require absolute or discoverable path to repo root**  
Skills in `.claude/skills/` call `tools/query_register.py SCTLR_EL1`. The query scripts need to know the path to `cache/`, which must be relative to the repo root (or an environment variable). Document how the skill invocation resolves this path — particularly if the user's working directory is not the repo root when invoking the skill.

---

### Key Design Decisions

**C-15 — Decision #5 (skill granularity) understates the routing problem**  
The plan chooses "4 modules × ~3 sub-commands = ~12 skills." For Claude to invoke the right sub-command, the skill text must clearly map user intent to sub-command. With 12 sub-commands across 4 skill files, there is a risk of the wrong skill being selected for edge cases (e.g., "how do I set the E0POE bit in SCTLR_EL1?" could match either `arm-reg` or `arm-reg-access`). The skills should include explicit routing examples or negative examples ("do NOT use this skill if...") to reduce misrouting.

**C-16 — Decision #2 output format omits compound queries**  
The plan chooses "compact JSON for fields/encoding, plain text for descriptions." This works for single-entity queries. For cross-cutting queries (`arm-search TCR`), returning mixed JSON and plain text from multiple entity types would be awkward. Define a uniform envelope format for search results, e.g.:

```json
{"query": "TCR", "results": [
  {"type": "register", "name": "TCR_EL1", "state": "AArch64"},
  {"type": "register", "name": "TCR_EL2", "state": "AArch64"}
]}
```

---

### Use-Case Table

**C-17 — "What's the encoding of MRS?" is in the wrong module**  
The table maps "What's the encoding of MRS?" to `arm-instr-enc MRS`. However, `MRS` (Move to Register from System register) is a system instruction accessor type, not a standalone operation in `Instructions.json`'s `operations` dict in the way `ADC` or `ADD` are. The encoding of MRS *as a system accessor* is found in `Registers.json` (under `accessors[].encoding` for registers accessed via MRS), not in `cache/operations/`. This query probably belongs to `arm-reg-access` with an accessor-type filter, not `arm-instr-enc`.

**C-18 — "Does FEAT_SVE require FEAT_FP16?" maps to wrong sub-command**  
The table shows this mapping to `arm-feat-deps FEAT_SVE`, which "renders dependency tree." However, the user is asking a yes/no question about a *specific* edge. `arm-feat-deps` is appropriate, but the skill response should first answer the direct question (yes/no), then optionally show the full tree. Skills should be instructed to extract the specific answer from the tree output rather than dumping the entire tree.

---

### Open Questions — Suggested Answers

**Q1 — Priority (registers vs. features first)**  
Suggest starting with **features** (Module 3): the cache is a single small file, the data is complete (all constraints present), and feature capability detection is the first thing needed when evaluating whether a code path applies to a given CPU. Registers second (most complex, highest firmware value), instructions last.

**Q3 — Cache rebuild trigger**  
Suggest: query scripts check for `cache/` existence at startup; if missing, print a clear error message like:
```
Cache not found. Run: python tools/build_index.py
```
This avoids silent failures. Do not auto-rebuild inside a skill invocation (too slow for interactive use).

**Q4 — Runtime**  
Python 3.8+ is sufficient (`json`, `os`, `argparse` from stdlib). Specify minimum version in `tools/requirements.txt` or a comment in `build_index.py`. No third-party dependencies are needed for the query scripts.

**Q5 — Integration across projects**  
If reuse across projects is a goal, the `cache/` path should be configurable via an environment variable (`ARM_MRS_CACHE_DIR`, defaulting to `./cache` for backward compatibility). The skill files would reference this variable so they can be copied to other repos without hardcoding the path.

---

## Summary of Recommended Additions to the Plan

| # | Category | Action |
|---|----------|--------|
| C-01 | Data model | Document that feature constraints are in two locations; extractor must walk both |
| C-02 | Data model | Handle deprecated SystemAccessor `_type` enum in `arm-reg-access` |
| C-04 | Module design | Define what identifier format `arm-instr-enc` accepts |
| C-05 | Module design | Describe the AST traversal algorithm for `arm-feat-version` |
| C-06 | Module design | Add `--state` filter to `arm-reg-list` |
| C-07 | Module design | Add `--summary` option to `arm-instr-op` to limit ASL output size |
| C-08 | Module design | Define how parameterized registers are named and queried in cache |
| C-09 | Module design | Add `arm-reg-field-values` (or equivalent) for field value enumeration |
| C-10 | Module design | Define AArch32 vs AArch64 tie-breaking convention for bare register names |
| C-11 | Phase 0 | Add cache manifest with source file hashes for staleness detection |
| C-13 | Phase 0 | Add `.gitignore` creation/update step for `cache/` |
| C-14 | Phase 2 | Document how skills resolve the path to query scripts |
| C-17 | Use cases | Move "MRS encoding" query to `arm-reg-access` module, not `arm-instr-enc` |
| C-18 | Use cases | Instruct skills to answer yes/no before showing full dependency tree |
