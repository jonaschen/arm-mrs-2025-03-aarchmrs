# AArch64 Agent Skills — Development Plan

## Goal

Create a set of Claude Code agent skills that ground hardware-related AI responses in the official ARM Machine Readable Specification (MRS), eliminating hallucination for tasks involving registers, instructions, and architecture features.

---

## Data Reality Check

Before planning, key facts about this MRS release (v9Ap6-A, Build 445, March 2025):

| File | Size | Entries | Description fields |
|------|------|---------|-------------------|
| `Features.json` | 1 MB | 344 `FEAT_*` + 17 version params | Mostly `null` (BSD subset omits prose) |
| `Instructions.json` | 38 MB | 4,584 instruction nodes, 2,262 operations | Operation `brief`/`description` present |
| `Registers.json` | 75 MB | 1,607 registers | `title`/`purpose` mostly `null` |

The data provides **structural facts** (encodings, field layouts, bit ranges, access modes, feature constraints), but **not prose descriptions**. Skills are designed around what is actually present in the data.

Loading these files whole in a skill context is impossible (~100M+ tokens). The solution is **targeted extraction** — load only the specific entity requested.

---

## Repository Structure

```
arm-mrs-2025-03-aarchmrs/
├── tools/
│   ├── build_index.py       # One-time: builds cache/
│   ├── query_register.py    # CLI: query_register.py SCTLR_EL1
│   ├── query_instruction.py # CLI: query_instruction.py ADC
│   └── query_feature.py     # CLI: query_feature.py FEAT_SVE
├── cache/                   # Generated, gitignored
│   ├── registers/           # One JSON file per register (~1607 files)
│   │   ├── SCTLR_EL1.json
│   │   └── ...
│   ├── operations/          # One JSON file per operation (~2262 files)
│   │   ├── ADC.json
│   │   └── ...
│   ├── features.json        # All 361 features in one file (small enough)
│   └── registers_meta.json  # name→state→groups index (for listing/search)
└── .claude/
    └── skills/
        ├── arm-reg.md
        ├── arm-instr.md
        ├── arm-feat.md
        └── arm-search.md
```

---

## Module Plan

### Module 1: `arm-reg` — Register Queries

**Trigger:** User asks about a system register, its fields, bit layout, or access method.

| Sub-command | What it returns |
|-------------|----------------|
| `arm-reg SCTLR_EL1` | All named fields with bit ranges, access type, field values |
| `arm-reg SCTLR_EL1 UCI` | Single field detail (bit position, values) |
| `arm-reg-list EL1` | All registers whose name matches a pattern |
| `arm-reg-access SCTLR_EL1` | Accessor type (MRS/MSR/memory-mapped), encoding, permissions |

**Data used:** `cache/registers/REG_NAME.json`

---

### Module 2: `arm-instr` — Instruction Queries

**Trigger:** User asks about an instruction's behavior, encoding, or syntax.

| Sub-command | What it returns |
|-------------|----------------|
| `arm-instr ADC` | Operation brief + assembly syntax symbols |
| `arm-instr-enc ADD_immediate` | Encoding bit fields and width |
| `arm-instr-list ADD` | All instruction nodes matching the mnemonic prefix |
| `arm-instr-op FADD_advsimd` | Full operation text (ASL pseudocode) |

**Note:** Instruction names in the data are internal identifiers (e.g., `add_z_p_zz_`), while operation names are uppercase mnemonics (e.g., `ADC`). Skills query by operation name (the dict key in `operations`), which maps to human-readable mnemonics.

**Data used:** `cache/operations/OP_NAME.json`

---

### Module 3: `arm-feat` — Feature / Extension Queries

**Trigger:** User asks what a `FEAT_*` requires, whether features conflict, or what a version introduces.

| Sub-command | What it returns |
|-------------|----------------|
| `arm-feat FEAT_SVE` | Feature type, constraint expressions (dependencies) |
| `arm-feat-deps FEAT_SVE` | Rendered dependency tree (what it implies/requires) |
| `arm-feat-version v9Ap2` | All features introduced at or before this version |
| `arm-feat-list SVE` | All matching `FEAT_*` names |

**Data used:** `cache/features.json` (small, ~1 MB, loaded whole)

---

### Module 4: `arm-search` — Cross-cutting Search

**Trigger:** User doesn't know which category to look in, or wants to find things by keyword.

| Sub-command | What it returns |
|-------------|----------------|
| `arm-search TCR` | Registers, instructions, and features matching "TCR" |
| `arm-search-reg EL2` | Registers whose name contains "EL2" |

**Data used:** `cache/registers_meta.json` + operation key index from `Instructions.json`

---

## Implementation Phases

### Phase 0 — Bootstrap (`tools/build_index.py`)

- Parse all three source JSON files once
- Write `cache/registers/*.json`, `cache/operations/*.json`, `cache/features.json`, `cache/registers_meta.json`
- Runs once, or re-run when MRS is updated; `cache/` is gitignored
- Estimated cache size: ~200–400 MB total; each individual file is tiny (< 50 KB)

### Phase 1 — Query Scripts (`tools/`)

- Three Python scripts with clean CLI interfaces
- Return filtered, compact JSON (not raw MRS objects)
- Designed to be called directly by skills or by a human at the command line

### Phase 2 — Skills (`.claude/skills/`)

- One skill file per module
- Each skill instructs Claude to call the appropriate query script
- Skills define what to include/exclude in output to minimize token usage

---

## Key Design Decisions

### 1. Cache location: in-repo vs. system cache
- In-repo `cache/` (gitignored): simple, portable, no path configuration needed
- `~/.cache/arm-mrs/`: cleaner, shareable across projects
- **Default plan:** in-repo `cache/` for simplicity

### 2. Output format from query scripts: JSON or formatted text
- JSON: Claude can re-interpret it accurately, fully grounded in spec
- Formatted text: More readable in context, fewer tokens
- **Default plan:** compact JSON for fields/encoding (precision), plain text summary for descriptions

### 3. Handling null descriptions
- The BSD MRS has `null` for most prose fields
- Skills should acknowledge this clearly rather than hallucinating a description
- For human-readable descriptions, skills can note "see official ARM docs for prose"

### 4. Instruction naming: internal IDs vs. mnemonics
- Internal names: `add_z_p_zz_`, `sub_z_p_zz_` (not user-friendly)
- Operation names: `ADD`, `ADC`, `FADD_advsimd` (what users ask about)
- **Default plan:** query by operation name (dict key), which maps to human-readable mnemonics

### 5. Skill granularity: broad vs. narrow
- Option A: 4 broad skills with sub-commands (fewer files, more flexibility)
- Option B: 10+ narrow skills (one per query type, simpler prompts each)
- **Default plan:** 4 modules × ~3 sub-commands = ~12 skills total (balanced)

---

## What These Skills Enable

| User Task | Skill Used |
|-----------|-----------|
| "What fields does SCTLR_EL1 have?" | `arm-reg SCTLR_EL1` |
| "What is bit 26 of SCTLR_EL1?" | `arm-reg SCTLR_EL1 UCI` |
| "How do I read CPACR_EL1 from EL1?" | `arm-reg-access CPACR_EL1` |
| "What does the ADC instruction do?" | `arm-instr ADC` |
| "What's the encoding of MRS?" | `arm-instr-enc MRS` |
| "Does FEAT_SVE require FEAT_FP16?" | `arm-feat-deps FEAT_SVE` |
| "What features does ARMv9.2 add?" | `arm-feat-version v9Ap2` |

---

## Open Questions

1. **Priority:** Start with registers (most complex, most useful for driver/firmware work) or features (simpler, good for capability detection)?

2. **Scope:** Is the primary use case register/feature queries for driver and firmware development, or also instruction encoding/decoding for binary analysis?

3. **Cache rebuild:** Manual step (`/arm-rebuild-cache`), or triggered automatically when a skill is invoked and cache is missing?

4. **Runtime:** Python is the default choice for JSON parsing. Any constraints (shell-only, specific Python version, etc.)?

5. **Integration:** Will these skills be used only in this repo, or packaged for reuse across other projects?
