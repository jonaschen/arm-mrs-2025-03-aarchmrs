# Contributing

Thank you for evaluating and contributing to this project. As an alpha release, feedback
and incremental improvements from BSP engineers in real working environments are the most
valuable input for closing gaps before a wider release.

---

## Ways to contribute

| Type | How |
|------|-----|
| Bug report / wrong answer | Open an Issue (see [Reporting issues](#reporting-issues)) |
| Missing register / instruction / event | Open an Issue with the spec reference |
| New JSON data (GIC, CoreSight, PMU) | Open a Pull Request (see [Data contributions](#data-contributions)) |
| New or improved lint rule | Open a Pull Request (see [Code contributions](#code-contributions)) |
| Documentation fix | Open a Pull Request with your edit |
| General alpha feedback | Open an Issue labelled `alpha-feedback` |

---

## Reporting issues

Open a GitHub Issue and include:

1. **The query or prompt** that produced wrong or missing output.
2. **The actual output** — paste the full terminal output or Claude Code response.
3. **The expected output** — what the ARM spec says or what you expected to see.
4. **Spec reference** — section or page number in the relevant ARM document (DDI0487, IHI0069, IHI0029, etc.) if applicable.
5. **Environment**:
   - OS and distribution
   - `python3 --version`
   - Which caches are built (`ls cache/` output)
   - Claude Code version (if relevant)

Label the issue `alpha-feedback` so it is triaged promptly.

### Common issue categories

| Category | Example |
|----------|---------|
| Wrong register field layout | "SCTLR_EL1.UCI bit position is wrong" |
| Missing instruction | "MOV (register) encoding not found" |
| Wrong feature dependency | "FEAT_SVE2 dependency chain is incorrect" |
| GIC/CoreSight gap | "GICD_IROUTER register is missing" |
| PMU event discrepancy | "Cortex-A53 CPU_CYCLES event code is wrong" |
| Cross-compile failure | "Compile error not covered by repair rules" |
| Lint false positive/negative | "Rule L27 fires incorrectly on XZR destination" |
| Skill misrouting | "Claude answered a register question without calling arm-reg" |

---

## Setting up a development environment

```bash
git clone https://github.com/jonaschen/arm-mrs-2025-03-aarchmrs.git
cd arm-mrs-2025-03-aarchmrs

# Build all caches
python3 tools/build_index.py
python3 tools/build_arm_arm_index.py
python3 tools/build_gic_index.py
python3 tools/build_coresight_index.py
python3 tools/build_pmu_index.py

# Run the full evaluation suite — all 292 tests must pass before opening a PR
python3 tools/eval_skill.py
```

No Python package manager is needed. All tools use Python 3.8+ stdlib only — `json`,
`hashlib`, `os`, `re`, `argparse`, `subprocess`, `pathlib`. Do not add third-party
dependencies.

---

## Code contributions

### Before you start

- Check the open Issues and `ROADMAP.md` to avoid duplicate work.
- For non-trivial changes, open an Issue first to discuss the approach.

### Development rules

1. **Python 3.8+ stdlib only.** Do not add third-party packages.
2. **No auto-rebuild inside query scripts.** The cache builders run once; query scripts
   read from `cache/` only.
3. **No prose synthesis.** Skills must emit `"Description not available in BSD MRS release"`
   for `null` fields. Never fabricate descriptions from the field name or context.
4. **All 292 eval tests must pass.** Run `python3 tools/eval_skill.py` before opening
   a PR. If your change warrants new tests, add them in `tools/eval_skill.py` following
   the existing pattern (see `FEAT_TESTS`, `REG_TESTS`, etc.).
5. **Cache files are gitignored.** Never commit anything under `cache/`.
6. **Scripts must be invokable as `python3 tools/<script>.py`** from the repo root.

### Making a change

```bash
git checkout -b my-fix-branch

# edit files …

# Run the relevant subset of tests first
python3 tools/eval_skill.py --skill reg     # example

# Run the full suite before pushing
python3 tools/eval_skill.py

git push origin my-fix-branch
# open a Pull Request on GitHub
```

### Eval test conventions

Each skill has a test list constant (e.g., `REG_TESTS`) in `tools/eval_skill.py`.
Each test is a dict with at minimum:

```python
{"cmd": ["python3", "tools/query_register.py", "SCTLR_EL1"],
 "expect": "UCI",
 "desc": "SCTLR_EL1 has UCI field"}
```

- `cmd` — the command as a list (passed to `subprocess.run`).
- `expect` — a string that must appear in stdout.
- `desc` — one-line human-readable description (shown on failure).

---

## Data contributions

### Adding GIC registers (`gic/GIC.json`)

The GIC data is hand-curated from the public GIC Architecture Specification (IHI0069).
To add a missing register:

1. Find the register table in IHI0069 (downloadable from developer.arm.com).
2. Add an entry to `gic/GIC.json` following the schema in `gic/schema/`.
3. Rebuild the GIC cache: `python3 tools/build_gic_index.py`.
4. Add an eval test to `tools/eval_skill.py` in `GIC_TESTS`.
5. Run: `python3 tools/eval_skill.py --skill gic`.

### Adding CoreSight registers (`coresight/CoreSight.json`)

Same process as GIC, using the CoreSight Architecture Specification (IHI0029).

1. Add the register to `coresight/CoreSight.json` following the schema in `coresight/schema/`.
2. Rebuild: `python3 tools/build_coresight_index.py`.
3. Add an eval test in `CORESIGHT_TESTS`.
4. Run: `python3 tools/eval_skill.py --skill coresight`.

### Adding PMU events (`pmu/`)

PMU data is sourced from [ARM-software/data](https://github.com/ARM-software/data) (Apache 2.0).
To add a new CPU or update events:

1. Copy the relevant `pmu/<cpu>.json` from ARM-software/data into the `pmu/` directory.
2. Rebuild: `python3 tools/build_pmu_index.py`.
3. Add an eval test in `PMU_TESTS`.
4. Run: `python3 tools/eval_skill.py --skill pmu`.

### Adding T32/A32 instructions (`arm-arm/`)

The T32/A32 instruction data is hand-curated from ARM DDI0487 (ARM Architecture License
required for the full set; hand-curation from the public ARM ARM PDF is acceptable).

1. Add an entry to `arm-arm/T32Instructions.json` or `arm-arm/A32Instructions.json`
   following the existing schema.
2. Rebuild: `python3 tools/build_arm_arm_index.py`.
3. Add eval tests in the relevant test list.
4. Run: `python3 tools/eval_skill.py --skill instr`.

---

## Skill file contributions (`.claude/skills/`)

Skill files in `.claude/skills/` control how Claude Code routes queries. When editing them:

- Keep **positive triggers** specific — avoid over-broad patterns that would fire the wrong skill.
- Keep **negative examples** up to date so skills do not overlap.
- Test routing by asking representative queries in Claude Code after your edit.
- Do not duplicate data from the query tools — skills invoke tools; they do not embed spec data.

---

## Out of scope

These are explicitly not accepted (see `ROADMAP.md` § "Not in Scope"):

- Third-party Python dependencies
- SMMU or GICv5 (spec not finalised)
- CMSIS-SVD microcontroller files
- Linux kernel DT bindings
- Prose synthesis from null fields
- Auto-rebuild inside query script invocations

---

## License

All contributions to this repository are made under the BSD 3-Clause license that
governs the repository (see [docs/notice.html](docs/notice.html)).

PMU data files under `pmu/` are derived from ARM-software/data and remain under
their original Apache 2.0 license.
