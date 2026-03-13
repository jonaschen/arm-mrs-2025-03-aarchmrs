# ARM Specification Extension — Development Plan

This document assesses the feasibility of extending the agent skills beyond the current
AARCHMRS JSON data (DDI0487 architecture features, registers, and instructions), and
lays out a phased implementation plan for each candidate specification.

---

## Data Availability Assessment

The fundamental constraint on what can be added is **whether ARM publishes machine-readable data**.
The current project works because ARM distributes AARCHMRS as structured JSON under BSD 3-clause.
Other specifications require different ingestion strategies.

| Specification | Source | Format | License | Machine-Readable? |
|---|---|---|---|---|
| **AARCHMRS JSON** (current) | ARM Exploration Tools | JSON | BSD 3-clause | ✅ Native |
| **AARCHMRS XML** (full MRA) | ARM Exploration Tools | XML | Architecture license required | ⚠️ Restricted |
| **PMU Events** (ARM-software/data) | GitHub ARM-software/data | JSON | Apache 2.0 | ✅ Native |
| **GIC** (IHI0069) | developer.arm.com | PDF / HTML | Proprietary | ❌ No native; HTML extractable |
| **CoreSight** (IHI0029) | developer.arm.com | PDF / HTML | Proprietary | ❌ No native; HTML extractable |
| **ARM ARM** (DDI0487) | ARM Exploration Tools | JSON/XML | JSON: BSD; XML: licensed | ✅ Already ingested (current project) |

### Key findings

1. **GIC and CoreSight have no machine-readable release.** ARM has never published these as JSON
   or XML. They exist only as PDF/HTML on developer.arm.com. Any ingestion requires building a
   custom HTML extractor against the live documentation site.

2. **The AARCHMRS JSON (current project) IS the DDI0487 machine-readable form.** Adding
   "the ARM ARM" would mean either: (a) accessing the XML release (which has ASL pseudocode
   currently null in our BSD JSON) or (b) expanding coverage within the existing data.

3. **PMU Events** are the only other ARM-published, BSD-compatible, native JSON dataset outside
   the current AARCHMRS. These are maintained in `ARM-software/data` on GitHub and cover
   CPU-specific performance counter event names and descriptions.

4. **AARCHMRS XML** is the same underlying specification as the current JSON, but the XML
   release distributed to architecture licensees includes **full ASL pseudocode** for all
   instructions. This is the single most valuable extension — it would fill the `// Not specified`
   gaps in all 2,262 operation files. However, it requires an ARM architecture license to access.

---

## Phase overview

```
Phase 1: PMU Events (arm-pmu skill)          ← ARM-native JSON, Apache 2.0, low effort
Phase 2: AARCHMRS XML / ASL unlock           ← High value, requires architecture license
Phase 3: GIC registers (HTML extraction)     ← Medium effort, proprietary data, no redistribution
Phase 4: CoreSight registers (HTML extract)  ← High effort, proprietary data, no redistribution
```

---

## Phase 1 — PMU Events (`arm-pmu` skill)

**Source:** https://github.com/ARM-software/data
**License:** Apache 2.0 (redistributable)
**Effort:** Low — native JSON, similar structure to current skills

### What's available

`ARM-software/data` publishes JSON files for CPU-specific PMU (Performance Monitoring Unit)
event definitions. Each JSON file describes one CPU microarchitecture (e.g., Cortex-A710,
Neoverse N2) with:
- Event name (e.g., `CPU_CYCLES`, `L1D_CACHE_REFILL`)
- Event number (hex encoding written to `PMEVTYPER<n>`)
- Description (human-readable — this data has real prose unlike the BSD AARCHMRS)
- Applicable privilege levels
- Unit (cycle count, byte count, etc.)

This is the highest-priority extension because:
- It is natively machine-readable (already JSON)
- It has real descriptions (not BSD-omitted null fields)
- PMU queries are extremely common in performance engineering

### Data structure

```
ARM-software/data/
  pmu/
    cortex-a710.json
    cortex-a715.json
    neoverse-n2.json
    neoverse-v2.json
    ...   (~40+ CPU JSON files)
```

Each file follows a schema like:
```json
{
  "pmu_name": "armv9-a-pmuv3",
  "events": [
    {
      "PublicDescription": "Counts ...",
      "ArchitectureName": "CPU_CYCLES",
      "Code": "0x0011",
      "Type": "Required",
      ...
    }
  ]
}
```

### Ingestion plan

**P1-1 — Probe and schema validation**
- Clone/download `ARM-software/data` (or snapshot a release)
- Run a probe script to confirm field names, identify which CPUs are present, measure coverage
- Document which fields have null/empty descriptions and which are reliably populated

**P1-2 — `build_pmu_index.py`**
- Reads all `pmu/*.json` files
- Writes `cache/pmu/` with one file per CPU (e.g., `cortex-a710.json`)
- Writes `cache/pmu_meta.json`: `{ cpu_name → { file, event_count } }` index
- Writes `cache/pmu_events_flat.json`: flat list of `{ cpu, event_name, code, description }`
  for cross-CPU event name search
- Updates `manifest.json` to include PMU source hashes

**P1-3 — `query_pmu.py`**
- `query_pmu.py cortex-a710` — list all events for this CPU with codes and truncated description
- `query_pmu.py cortex-a710 CPU_CYCLES` — full detail for a specific event
- `query_pmu.py --search L1D_CACHE` — find all CPUs that have events matching a pattern
- `query_pmu.py --list` — list all CPUs with event counts
- Standard staleness check and cache-not-found error handling

**P1-4 — `.claude/skills/arm-pmu.md`**
- Positive triggers: PMU event names, PMEVTYPER encoding for a named event, comparing event
  availability across CPUs
- Negative examples: instruction performance characteristics (not in spec data), PMCCNTR usage
  (→ `arm-reg PMCCNTR_EL0`)
- Note: descriptions ARE available for PMU events (unlike AARCHMRS BSD release)

**P1-5 — Eval tests**
- CPU existence: `cortex-a710` is present
- Event existence: `CPU_CYCLES` exists for Cortex-A710 with code `0x0011`
- Cross-CPU search: `L1D_CACHE_REFILL` found on multiple CPUs
- Hallucination guard: `FAKE_TURBO_COUNTER` returns non-zero exit

**Exit criteria:** `python3 tools/query_pmu.py cortex-a710 CPU_CYCLES` returns the event code
and description grounded in ARM-official data.

---

## Phase 2 — AARCHMRS XML / ASL Pseudocode Unlock

**Source:** ARM Architecture License (not publicly available)
**License:** Architecture license required — data NOT redistributable
**Effort:** Medium — data is structurally similar to current JSON but in XML

### What's available

The XML release of AARCHMRS (sometimes called the "full MRA") contains:
- **Full ASL pseudocode** for all instructions (currently `// Not specified` in BSD JSON)
- **Full prose descriptions** for registers and fields (currently `null` in BSD JSON)
- **Complete instruction semantics** — decode logic, execute blocks, exception flows

This is what tools like the Sail model and ARM's own formal verification tooling are built on.

### Applicability

This phase is only relevant if:
- You or your organization holds an ARM Architecture License (universities, chip companies, EDA vendors)
- You are working under ARM's community research program

If you do not hold a license, skip this phase. The current BSD JSON data is all that can be used.

### Implementation (if licensed)

**P2-1 — Download and probe the XML release**
- XML is distributed as per-register files and per-instruction-group files
- Probe for field names that correspond to the JSON fields currently null
- Map XML field paths → JSON cache schema extensions

**P2-2 — Extend `build_index.py`**
- Add an optional `--xml-dir` argument pointing to the XML release directory
- Merge ASL pseudocode and prose descriptions into existing cache files where available
- Preserve the JSON-only path for users without the XML release

**P2-3 — Update skill files**
- Remove "not available in BSD MRS release" disclaimers when data is present
- `arm-instr`: `--op` now returns real ASL instead of the stub message
- `arm-reg`: field descriptions now have content

**P2-4 — Conditional eval tests**
- Tests that check for real pseudocode content (skip if XML data not present)

**Note:** This phase does not add new skill types — it enriches the four existing skills.
Cache files remain in the same format; only previously-null fields get populated.

---

## Phase 3 — GIC Registers (`arm-gic` skill)

**Source:** https://developer.arm.com/documentation/ihi0069/latest/ (HTML)
**License:** Proprietary — data NOT redistributable; local cache only
**Effort:** High — requires a custom HTML extractor

### What's available

The GIC Architecture Specification (IHI0069, currently version F for GICv4.1) documents:
- ~200+ named GIC registers (GICD_*, GICC_*, GICR_*, GICH_*, GICV_*)
- Each register has: bit field layout, field names, reset values, R/W/RO attributes
- Register address offsets within GIC distributor, redistributor, CPU interface, etc.
- No machine-readable version — documentation is HTML only on developer.arm.com

**Unlike AARCHMRS, this data is proprietary.** A local cache built from it should NOT be
committed to a public repository or redistributed.

### Ingestion strategy

ARM's online documentation renders each register as a structured HTML table. The pattern is
consistent enough to parse programmatically, but requires reverse-engineering the HTML layout
and handling version differences.

**P3-1 — HTML structure probe**
- Fetch the GIC IHI0069 HTML documentation
- Identify register table patterns: field names, bit ranges, reset values, access types
- Assess consistency across all GICD_*, GICC_*, GICR_* sections
- Document any ambiguities or edge cases (e.g., implementation-defined fields)

**P3-2 — `fetch_gic.py` (one-time extractor)**
- Downloads the GIC spec HTML pages from developer.arm.com
- Parses register tables using `html.parser` (stdlib only)
- Writes `cache/gic/GICD_CTLR.json`, `cache/gic/GICR_WAKER.json`, etc.
- Writes `cache/gic_meta.json`: name → { interface, offset, description_available }
- Writes version metadata: which GIC version (v3/v4/v4.1) is captured

**P3-3 — `query_gic.py`**
- `query_gic.py GICD_CTLR` — field layout with bit ranges, access type, reset value
- `query_gic.py GICD_CTLR EnableGrp0` — single field detail
- `query_gic.py --list GICR` — list all redistributor registers
- `query_gic.py --list --interface dist` — filter by interface (dist/redist/cpu/hyp/virt)

**P3-4 — `.claude/skills/arm-gic.md`**
- Positive triggers: GIC register fields, interrupt configuration, GICv3 redistributor layout
- Negative examples: ARM system registers like ICC_SRE_EL1 → `arm-reg ICC_SRE_EL1`
  (those are in AARCHMRS already)

**Constraints:**
- The `.gitignore` must include `cache/gic/` (proprietary data, not redistributable)
- `CLAUDE.md` must document the one-time fetch step clearly
- Rate-limit the HTML fetcher to avoid hammering developer.arm.com

**Exit criteria:** `python3 tools/query_gic.py GICD_CTLR EnableGrp0` returns correct bit
position and access type from the GIC v3/v4 specification.

---

## Phase 4 — CoreSight Registers (`arm-cs` skill)

**Source:** https://developer.arm.com/documentation/ihi0029/latest/ (HTML)
**License:** Proprietary — NOT redistributable; local cache only
**Effort:** High — HTML extraction, complex component hierarchy

### What's available

The CoreSight Architecture Specification (IHI0029E, v3.0) documents:
- Component registers for ETM, CTI, ETF, TMC, STM, ROM Table, etc.
- Each component has a standard CoreSight register block at a known offset
- Component identification registers (DEVAFF, DEVID, CIDR, PIDR)
- Complex: the same register name may appear in multiple component types with different semantics

### Ingestion strategy

CoreSight is more complex than GIC because:
1. Registers are organized by **component type**, not a flat namespace
2. Some registers are defined once at the architecture level and appear in many components
3. The HTML structure may vary more across component sections

**P4-1 — HTML structure probe and complexity assessment**
- Fetch the CoreSight IHI0029 HTML
- Assess how many distinct components exist and how register tables are structured
- Determine whether component-scoped naming is needed (e.g., `ETM.TRCPRGCTLR` vs flat `TRCPRGCTLR`)
- Estimate the total number of distinct register × component combinations

**P4-2 — Scoped data model**
The cache should reflect the component hierarchy:
```
cache/coresight/
  etm/TRCPRGCTLR.json
  cti/CTICONTROL.json
  tmc/FFCR.json
  ...
cache/coresight_meta.json
```

**P4-3 — `fetch_coresight.py`** and **`query_coresight.py`**
- Similar structure to Phase 3 tools
- `query_coresight.py etm TRCPRGCTLR` — component-scoped lookup
- `query_coresight.py --list etm` — all ETM registers
- `query_coresight.py --list --component cti` — all CTI registers

**P4-4 — `.claude/skills/arm-cs.md`**

**Note:** Phase 4 should be preceded by Phase 3 to validate the HTML extraction approach.

---

## Implementation priority

| Phase | Skill | Value | Effort | Blocker |
|---|---|---|---|---|
| P1 | `arm-pmu` | High | Low | None — start immediately |
| P2 | ASL enrichment | Very high | Medium | Requires architecture license |
| P3 | `arm-gic` | High | High | HTML extraction; proprietary data |
| P4 | `arm-cs` | Medium | Very high | Depends on P3 validation |

**Recommended sequence:** P1 → P3 probe → P2 (if licensed) → P3 full → P4

---

## Shared infrastructure changes

All new phases should reuse the existing patterns:

1. **Cache manifest** — extend `manifest.json` to include new source hashes (PMU: git commit SHA;
   GIC/CoreSight: fetched URL + ETag or last-modified header; XML: file hash)

2. **Staleness detection** — all `query_*.py` scripts import the same `check_staleness()` helper;
   consider extracting to a shared `cache_utils.py` module when ≥3 scripts duplicate it

3. **`ARM_MRS_CACHE_DIR`** — already documented; all new tools should respect it

4. **Eval framework** — `eval_skill.py` `ALL_SKILLS` dict is already extensible; add a `pmu`
   key when P1 is done

5. **`.gitignore`** — add `cache/gic/` and `cache/coresight/` entries for Phase 3/4 (proprietary)

---

## What NOT to add

| Candidate | Reason to skip |
|---|---|
| CMSIS-SVD device files | Microcontroller peripherals, not ARM system architecture |
| Linux kernel bindings | These describe Linux device model, not the ARM spec |
| TrustZone / TF-A registers | Defined within AARCHMRS (already in Registers.json) |
| AMBA bus protocol (APB, AXI) | No register-level spec; signal-level only |
| ARM Compiler documentation | Tool documentation, not hardware spec |

---

## Open questions before starting

1. **Phase 1 (PMU):** Which CPUs in `ARM-software/data` are in scope? The repository includes
   ~40+ CPUs from Cortex-A53 to Neoverse V3. Should the cache include all, or a curated subset?

2. **Phase 3/4 (HTML):** ARM's documentation is hosted on a CDN with dynamic rendering. Confirm
   that the register tables are in static HTML (parseable without a headless browser) before
   committing to this approach.

3. **Phase 2 (XML):** Does an architecture license exist in this context? If yes, what format
   is the XML download and does it include the full `aarch64.xml` / `aarch32.xml` hierarchy?

4. **Cache storage:** PMU data adds ~50 JSON files (~5 MB). GIC/CoreSight would add ~300+ files.
   These are small enough to keep in the same `cache/` directory structure.
