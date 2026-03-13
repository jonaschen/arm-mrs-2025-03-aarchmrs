# arm-pmu — ARM PMU Event Queries

Use this skill when the user asks about **ARM PMU (Performance Monitoring Unit)**
events, event codes, or PMEVTYPER programming:
- "What is the event code for CPU_CYCLES on Cortex-A710?"
- "What PMU events does the Cortex-A55 have?"
- "How do I count L1D cache refills in the PMU?"
- "Which CPUs support L1D_CACHE_REFILL?"
- "What is event code 0x003 on Neoverse N1?"
- "What PMU events are available for Neoverse N2?"
- "How do I configure PMEVTYPER to count branch mispredictions?"
- "Compare L1I_CACHE_REFILL across Cortex-A710 and Neoverse N2"

## Do NOT use this skill when the user asks about:
- PMU system registers (PMCCNTR_EL0, PMEVTYPER<n>_EL0, PMEVCNTR<n>_EL0, etc.) → use `arm-reg`
- PMU enable/disable registers (PMCR_EL0, PMCNTENSET_EL0, PMINTENSET_EL1) → use `arm-reg`
- Instruction throughput or latency → out of scope
- Cache behaviour analysis (structural) → out of scope

### Routing summary
| User query | Use |
|-----------|-----|
| "What PMU event counts L1 cache misses?" | `arm-pmu --search L1D_CACHE_REFILL` |
| "What code do I write to PMEVTYPER?" | `arm-pmu cortex-a710 L1D_CACHE_REFILL` (for code) + `arm-reg PMEVTYPER0_EL0` (for register) |
| "PMCCNTR_EL0 fields" | use `arm-reg PMCCNTR_EL0` (PMU counter system register) |
| "Cortex-A710 CPU_CYCLES event code" | `arm-pmu cortex-a710 CPU_CYCLES` |

---

## Prerequisites

Before any query, build the PMU cache:
```bash
python3 tools/build_pmu_index.py
```

---

## Path resolution

```bash
REPO=$(git rev-parse --show-toplevel)
SCRIPT="$REPO/tools/query_pmu.py"
```

---

## Commands

### All events for a CPU
```bash
python3 "$SCRIPT" cortex-a710
python3 "$SCRIPT" neoverse-n1
python3 "$SCRIPT" cortex-a55
```
Returns: CPU metadata (architecture, PMU arch, hardware counter count) and a table
of all events with codes (decimal and hex), type classification, architectural flag,
and truncated description.

### Single event full detail
```bash
python3 "$SCRIPT" cortex-a710 CPU_CYCLES
python3 "$SCRIPT" cortex-a710 L1D_CACHE_REFILL
python3 "$SCRIPT" neoverse-n1 BR_MIS_PRED
```
Returns: event code (decimal + hex), type, component, architectural flag,
and the full description text from ARM-official data.

### Cross-CPU event name search
```bash
python3 "$SCRIPT" --search L1D_CACHE
python3 "$SCRIPT" --search STALL
python3 "$SCRIPT" --search CYCLE
python3 "$SCRIPT" --search BR_MIS
```
Returns: all event names matching the pattern, with per-CPU event codes and
a description. Useful for comparing event availability and codes across CPUs.

### List all available CPUs
```bash
python3 "$SCRIPT" --list
python3 "$SCRIPT" --list cortex
python3 "$SCRIPT" --list neoverse
python3 "$SCRIPT" --list a7
```
Returns: all CPUs in the cache with architecture version, PMU architecture, and
event count. Optionally filtered by a pattern matched against the CPU slug.

---

## Data source and coverage

**Source:** ARM-software/data (https://github.com/ARM-software/data), Apache 2.0 license  
**Coverage:** Representative set of ARM Cortex-A and Neoverse CPUs (armv8-a through armv9-a)

Available CPUs in the starter dataset:
- **Cortex-A53** — armv8-a, 59 events
- **Cortex-A55** — armv8.2-a, 111 events
- **Cortex-A76** — armv8-a, 107 events (big core)
- **Cortex-A510** — armv9-a, 144 events (efficiency core)
- **Cortex-A710** — armv9-a, 151 events (performance core)
- **Cortex-X2** — armv9-a, 151 events (premium core)
- **Neoverse N1** — armv8.2-a, 110 events (server/cloud)
- **Neoverse N2** — armv9-a, 155 events (server/cloud, Armv9)

Unlike the BSD AARCHMRS release, **PMU event descriptions ARE available** in this dataset.

---

## Key PMU event types

| Type | Description |
|------|-------------|
| `INS` | Instruction execution events |
| `CYCLE` | CPU cycle events |
| `EXC` | Exception events |
| `UEVT` | Microarchitecture-specific events |
| `ETM` | Trace-related events |

**Architectural events** (marked `Arch=Y`) have the same code across all ARMv8/v9
compliant implementations. Non-architectural events may use different codes on
different CPUs. Always verify the code against the specific CPU.

---

## Programming guide: PMEVTYPER workflow

To count a PMU event using the Arm PMU:

1. Find the event code:
   ```bash
   python3 "$SCRIPT" cortex-a710 L1D_CACHE_REFILL
   # → Code: 3 (0x003)
   ```

2. Programme `PMEVTYPER<n>_EL0` with the event code (arm-reg skill):
   ```
   MSR PMEVTYPER0_EL0, Xt   ; bits [15:0] = event code
   ```

3. Enable the counter: `PMCNTENSET_EL0.P0 = 1`

4. Enable the PMU: `PMCR_EL0.E = 1`

5. Read count: `MRS Xt, PMEVCNTR0_EL0`

---

## Example interactions

**User:** "What is the CPU_CYCLES event code for Cortex-A710?"
```bash
python3 "$SCRIPT" cortex-a710 CPU_CYCLES
```
Report: code 17 (0x011), type CYCLE. Write 0x011 to PMEVTYPER<n>_EL0[15:0].

**User:** "Which ARM CPUs support L1D_CACHE_REFILL and what is the code?"
```bash
python3 "$SCRIPT" --search L1D_CACHE_REFILL
```
Report: event found in all 8 CPUs, consistently code 3 (0x003). This is an
architectural event code (0x03 is defined in the ARM PMUv3 architecture).

**User:** "What PMU events are available on Neoverse N2?"
```bash
python3 "$SCRIPT" neoverse-n2
```
Report: 155 events, armv9-a, pmuv3. List the full table.

**User:** "I want to count branch mispredictions — what event do I use?"
```bash
python3 "$SCRIPT" --search BR_MIS
python3 "$SCRIPT" cortex-a710 BR_MIS_PRED
```
Report: BR_MIS_PRED is the architectural branch misprediction event. Show the code
and description for the specific CPU.

**User:** "What is PMCR_EL0?"
```
→ Not a PMU event query. Use arm-reg PMCR_EL0 instead.
```
