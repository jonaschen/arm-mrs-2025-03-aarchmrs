# Quick Start Guide

This guide gets you from zero to a working ARM agent-skills environment in about 10 minutes.
No proprietary databases, no in-house tooling, no internet access after the initial clone.

---

## Step 1 — Prerequisites

| Requirement | Check |
|-------------|-------|
| Python 3.8 or later | `python3 --version` |
| ~512 MB free RAM | Needed during `build_index.py` only |
| ~200 MB free disk | For the generated `cache/` directory |
| [Claude Code](https://claude.ai/code) | For the AI-assisted skill interface |

The Phase 3 hardware engineering tools (H3/H4/H5) also need Linux dev tools, but they
are **optional** — all Phase 1/2 skills and the evaluation suite work without them:

```bash
# Optional — install only what you intend to use
sudo apt install gdb-multiarch           # H3: GDB debugging skill
sudo apt install qemu-user-static        # H4: QEMU emulation skill
sudo apt install gcc-aarch64-linux-gnu   # H5: cross-compilation skill
```

---

## Step 2 — Clone the repository

```bash
git clone https://github.com/jonaschen/arm-mrs-2025-03-aarchmrs.git
cd arm-mrs-2025-03-aarchmrs
```

The repository is self-contained (~116 MB of JSON data). No `pip install` or
dependency manager is required — all tools use Python stdlib only.

---

## Step 3 — Build the caches

The query tools read from a pre-built `cache/` directory. Build it once; rebuild only
when the corresponding source JSON file changes.

```bash
# Mandatory for all Phase 1/2 skills (A64 registers, instructions, features)
# Takes a few minutes; uses ~512 MB RAM during the Instructions.json pass
python3 tools/build_index.py

# Mandatory for T32/A32 instruction queries
python3 tools/build_arm_arm_index.py

# Mandatory for GIC register queries
python3 tools/build_gic_index.py

# Mandatory for CoreSight register queries
python3 tools/build_coresight_index.py

# Mandatory for PMU event queries
python3 tools/build_pmu_index.py
```

Expected output from each builder ends with a line like:

```
Cache written to /path/to/cache/  (N files, X.Xs)
```

---

## Step 4 — Verify the setup

Run the full evaluation suite. All 292 tests should pass:

```bash
python3 tools/eval_skill.py
```

Expected final line:

```
ALL TESTS PASSED (292/292)
```

If any tests fail, check that all five cache builders completed without errors.
The Phase 3 tool tests (gdb, qemu, cross) do not require the optional tools to be
installed — they test the Python logic only.

---

## Step 5 — Try a few queries

```bash
# Register field layout
python3 tools/query_register.py SCTLR_EL1

# Feature dependency
python3 tools/query_feature.py FEAT_SVE --deps FEAT_FP16

# Instruction encoding
python3 tools/query_instruction.py ADC --enc

# Cross-spec search
python3 tools/query_search.py TCR

# GIC register
python3 tools/query_gic.py GICD_CTLR EnableGrp0

# PMU event code
python3 tools/query_pmu.py cortex-a710 CPU_CYCLES

# Feature-qualified instruction allowlist
python3 tools/query_allowlist.py --arch v9Ap4 --summary

# Cross-compilation -march flag
python3 tools/setup_cross_compile.py --march-flag --arch v9Ap0 --feat FEAT_SVE2

# ISA optimization: list SVE2 templates
python3 tools/isa_optimize.py --list-templates --category sve2

# Linter rules
python3 tools/isa_linter.py --list-rules --category security
```

---

## Step 6 — Open in Claude Code

1. Open Claude Code.
2. Open the cloned repository folder (File → Open Folder).
3. The `.claude/skills/` files are loaded automatically — no extra configuration.
4. Ask questions in natural language; Claude Code will call the right query tool.

**Example conversation:**

> _"What are the fields of TCR_EL1 and how do I set the T0SZ field?"_

Claude Code will invoke `arm-reg` → `tools/query_register.py TCR_EL1 T0SZ --values`
and return the spec-grounded answer.

**Shared cache for teams:**

If multiple engineers share the same filesystem, set `ARM_MRS_CACHE_DIR` to a shared
path so each person does not need to build their own cache:

```bash
export ARM_MRS_CACHE_DIR=/shared/arm-mrs-cache
# then open the repo in Claude Code — the skills will use the shared cache
```

---

## Environment variables reference

| Variable | Default | Purpose |
|----------|---------|---------|
| `ARM_MRS_CACHE_DIR` | `<repo>/cache` | Override cache root for all skills |
| `ARM_GDB_PATH` | auto-detect | Path to `gdb-multiarch` or `gdb` |
| `ARM_QEMU_USER_PATH` | auto-detect | Path to `qemu-aarch64` |
| `ARM_QEMU_SYSTEM_PATH` | auto-detect | Path to `qemu-system-aarch64` |
| `ARM_CC_AARCH64` | auto-detect | Path to `aarch64-linux-gnu-gcc` |
| `ARM_CXX_AARCH64` | auto-detect | Path to `aarch64-linux-gnu-g++` |
| `ARM_SYSROOT` | auto-detect | Sysroot for cross-compilation |

---

## Troubleshooting

**`Cache not found. Run: python3 tools/build_index.py`**
→ You need to build the A64 cache first (Step 3).

**`Manifest stale — source file has changed since cache was built`**
→ Re-run the affected cache builder (see the table in README.md).

**`python3: command not found`**
→ Your system may call it `python` (verify with `python --version`). The scripts
require Python 3.8+.

**`eval_skill.py` reports failures in `gdb`/`qemu`/`cross` tests**
→ These test the Python module logic; they should pass even without the optional tools
installed. If they fail, check that all caches were built successfully.

**`build_index.py` is killed / out-of-memory**
→ You need ~512 MB free RAM. Close other applications or run on a machine with more
available memory.

---

## Where to go next

| Document | When to read it |
|----------|----------------|
| [README.md](README.md) | Full skills reference — all commands and options |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to report issues, submit data fixes, and add tests |
| [CLAUDE.md](CLAUDE.md) | Detailed context for Claude Code (loaded automatically) |
| [ROADMAP.md](ROADMAP.md) | Milestone status and implementation notes |
| [docs/userguide/](docs/userguide/) | User guides for registers, instructions, and features |
| GitHub Issues | Report gaps or incorrect answers (label: `alpha-feedback`) |
