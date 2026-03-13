# arm-coresight — ARM CoreSight Component Register Queries

Use this skill when the user asks about **CoreSight** debug and trace component registers:
- "How do I enable ETM tracing?"
- "What is the TRCPRGCTLR register?"
- "How do I program the ETM to trace EL0 only?"
- "What does TRCSTATR.IDLE mean?"
- "How do I configure CTI cross-triggers?"
- "Which CTI register routes trigger inputs to channels?"
- "How does CTIINEN map trigger inputs to channels?"
- "How do I enable STM stimulus ports?"
- "What registers control ITM tracing?"
- "How do I read PIDR registers to identify a CoreSight component?"
- "What is the common CoreSight identification block?"

## Do NOT use this skill when the user asks about:
- `MDSCR_EL1`, `DBGBCR<n>_EL1`, `DBGWCR<n>_EL1`, or other AArch64 debug system registers → use `arm-reg`
- CPU halt via `EDECR` or software step via `MDSCR_EL1.SS` → use `arm-reg`
- JTAG, SWD, or DAP protocol details → out of scope (not in MRS or CoreSight static data)
- Performance monitors (PMU, PMCR_EL0) → use `arm-reg` for system register fields
- GIC interrupt controllers (GICD_*, GICR_*) → use `arm-gic`

### Component routing
| User query | Use |
|-----------|-----|
| "How do I enable ETM trace?" | `arm-coresight etm TRCPRGCTLR` |
| "What is TRCPRGCTLR.EN?" | `arm-coresight etm TRCPRGCTLR EN` |
| "Show me all CTI registers" | `arm-coresight --component cti` |
| "How do CTI channels work?" | `arm-coresight cti CTIINEN0` + `arm-coresight cti CTIOUTEN0` |
| "List all ETM registers" | `arm-coresight --component etm` |
| "What are CoreSight ID registers?" | `arm-coresight --id-block` |
| "Is trace enabled?" | `arm-coresight etm TRCSTATR` (check IDLE bit) |
| "CPU halt / MDSCR_EL1" | use `arm-reg MDSCR_EL1` |

---

## Prerequisites

Before any query, build the CoreSight cache:
```bash
python3 tools/build_coresight_index.py
```

---

## Path resolution

```bash
REPO=$(git rev-parse --show-toplevel)
SCRIPT="$REPO/tools/query_coresight.py"
```

---

## Commands

### All fields for a component register
```bash
python3 "$SCRIPT" etm TRCPRGCTLR
python3 "$SCRIPT" etm TRCCONFIGR
python3 "$SCRIPT" cti CTICONTROL
python3 "$SCRIPT" stm STMHEMCR
python3 "$SCRIPT" itm TCR
```
Returns: register name, component, offset, width, CoreSight Architecture version,
and a table of all fields with bit ranges, access types, and reset values.

### Single field detail
```bash
python3 "$SCRIPT" etm TRCPRGCTLR EN
python3 "$SCRIPT" etm TRCSTATR IDLE
python3 "$SCRIPT" etm TRCCONFIGR BB
python3 "$SCRIPT" cti CTICONTROL GLBEN
python3 "$SCRIPT" cti CTIINEN0 TRIGINEN
python3 "$SCRIPT" itm TCR ITMENA
```
Returns: the specific field's bit range, access type, reset value, and brief description.

### All registers in a component
```bash
python3 "$SCRIPT" --component etm
python3 "$SCRIPT" --component cti
python3 "$SCRIPT" --component stm
python3 "$SCRIPT" --component itm
python3 "$SCRIPT" --component id_block
```
Returns: a table of all registers in the component with offsets and titles.

### List all component types
```bash
python3 "$SCRIPT" --list-components
```
Returns: all known CoreSight component names with their full titles.

### Register name search
```bash
python3 "$SCRIPT" --list TRC
python3 "$SCRIPT" --list CTI
python3 "$SCRIPT" --list ENABL
python3 "$SCRIPT" --list STATUS
```
Returns: all CoreSight register names containing the pattern.

### Common identification block
```bash
python3 "$SCRIPT" --id-block
python3 "$SCRIPT" id_block DEVARCH
python3 "$SCRIPT" id_block DEVTYPE
python3 "$SCRIPT" id_block AUTHSTATUS
python3 "$SCRIPT" id_block CIDR0
```
Returns the 13 standard registers present in every CoreSight 4 KB frame (offsets 0xF00–0xFFC).
Use DEVARCH to identify the architecture implemented, DEVTYPE for major/sub classification.

---

## Key CoreSight concepts

**Four address regions (component types):**
- **ETM** (Embedded Trace Macrocell) — one per PE; generates instruction/data trace
- **CTI** (Cross-Trigger Interface) — one per CTM connection point; routes triggers to channels
- **STM** (System Trace Macrocell) — system-level software stimulus trace
- **ITM** (Instrumentation Trace Macrocell) — Cortex-M profile software stimulus trace

**ETM trace enable sequence:**
1. Poll `TRCSTATR.IDLE` = 1 before programming
2. Program `TRCCONFIGR` for trace features (BB, CCI, CID, VMID, TS)
3. Program `TRCVICTLR` to select exception levels to trace
4. Set `TRCPRGCTLR.EN` = 1 to start trace

**CTI cross-trigger model:**
- 8 trigger inputs (hardware events e.g. halt, breakpoint) → channels via `CTIINEN<n>`
- 4 channels → 8 trigger outputs (e.g. halt PE, restart) via `CTIOUTEN<n>`
- Enable CTI with `CTICONTROL.GLBEN` = 1
- Monitor channel state via `CTICHINSTATUS` / `CTICHOUTSTATUS`

**STM stimulus port usage:**
1. Enable STM: `STMHEMCR.EN` = 1
2. Enable ports: `STMSPER` bit mask
3. Write to stimulus port MMIO address to generate trace packets

**ITM usage:**
1. Enable ITM: `TCR.ITMENA` = 1
2. Enable stimulus ports: `TER` bit mask
3. Write to `STIM<n>` (read first to check ready: returns 1)
4. Set `TCR.TraceBusID` to a unique 7-bit ATB ID

**Common identification block (every 4 KB frame):**
| Register | Offset | Purpose |
|----------|--------|---------|
| DEVARCH   | 0xFBC  | Architecture ID (v3+) — identify ETM, CTI, STM, etc. |
| DEVID     | 0xFC8  | Implementation-defined device info |
| DEVTYPE   | 0xFCC  | Major type + sub-type classification |
| AUTHSTATUS | 0xFB8 | Debug authentication status |
| PIDR0–4   | 0xFE0–0xFD0 | Peripheral ID — part number, JEP106 code |
| CIDR0–3   | 0xFF0–0xFFC | Component ID preamble and class |

**DEVTYPE major values:**
- 0x1 = Trace sink (e.g. ETB, TMC)
- 0x2 = Trace link (e.g. funnel, replicator)
- 0x3 = Trace source (e.g. ETM, STM, ITM, PTM)
- 0x4 = Debug control (e.g. CTI, CTM)
- 0x5 = Debug logic (e.g. CPU debug block)

---

## ETM programming reference

**Minimal trace enable (instruction trace, all exception levels):**
```
TRCSTATR.IDLE == 1       # wait before programming
TRCCONFIGR = 0x00000000  # no optional features
TRCVICTLR  = 0x00FF0000  # trace all ELs (EXLEVEL_NS=0xF, EXLEVEL_S=0xF)
TRCPRGCTLR = 0x00000001  # EN=1, start trace
```

**Enable branch broadcast:**
```
TRCCONFIGR.BB = 1   # all taken branches traced (no inference needed)
```

**Enable timestamps:**
```
TRCCONFIGR.TS = non-zero  # enable timestamp insertion
```

---

## Example interactions

**User:** "How do I enable ETM tracing?"
```bash
python3 "$SCRIPT" etm TRCPRGCTLR
python3 "$SCRIPT" etm TRCSTATR IDLE
```
Report: EN at bit [0], must wait for IDLE=1 first. Suggest also programming TRCCONFIGR and TRCVICTLR.

**User:** "What are the ETM trace configuration options?"
```bash
python3 "$SCRIPT" etm TRCCONFIGR
```
List all fields (BB, CCI, CID, VMID, TS, RS, DA, DV) with bit positions and brief descriptions.

**User:** "How do I configure CTI to halt all CPUs on a breakpoint trigger?"
```bash
python3 "$SCRIPT" cti CTICONTROL GLBEN
python3 "$SCRIPT" cti CTIINEN0
python3 "$SCRIPT" cti CTIOUTEN0
```
Explain: enable CTI (GLBEN=1), map breakpoint trigger input via CTIINEN<n>, map halt via CTIOUTEN<m>.

**User:** "How do I identify a CoreSight component from its registers?"
```bash
python3 "$SCRIPT" --id-block
python3 "$SCRIPT" id_block DEVARCH
python3 "$SCRIPT" id_block DEVTYPE
python3 "$SCRIPT" id_block CIDR1
```
Read DEVARCH for architecture ID, DEVTYPE for major/sub classification, CIDR1.CLASS for component class.

**User:** "What is TRCSTATR?"
```bash
python3 "$SCRIPT" etm TRCSTATR
```
Report IDLE [0] and PMSTABLE [1] fields. Emphasize polling IDLE=1 before any programming.
