# arm-gic — ARM GIC Register Queries

Use this skill when the user asks about **GIC (Generic Interrupt Controller)**
memory-mapped registers:
- "What are the fields of GICD_CTLR?"
- "How do I enable Group 0 interrupts in GICv3?"
- "What does EnableGrp1S control?"
- "Show me all GICR registers"
- "How does the ITS command queue work? (GITS_CBASER)"
- "What is the GICR_WAKER register?"
- "How do I configure LPI support in the Redistributor?"
- "How does vGIC direct injection work?"

## Do NOT use this skill when the user asks about:
- `ICC_*` system registers → use `arm-reg` (these are AArch64 system registers accessed via MRS/MSR)
- CPU interrupt pending state (e.g. `ICC_IAR1_EL1`) → use `arm-reg`
- Interrupt enable at the CPU interface level → use `arm-reg ICC_IGRPEN1_EL1`
- Interrupt priority masking at CPU level → use `arm-reg ICC_PMR_EL1`

### Component routing
| User query | Use |
|-----------|-----|
| "How do I enable all GIC interrupts?" | `arm-gic GICD_CTLR` + `arm-reg ICC_IGRPEN1_EL1` |
| "What is GICD_CTLR.EnableGrp0?" | `arm-gic GICD_CTLR EnableGrp0` |
| "Show me Redistributor registers" | `arm-gic --block GICR` |
| "How do LPIs work?" | `arm-gic --block GITS` + `arm-gic GICR_PROPBASER` |
| "ICC_IAR1_EL1 fields" | use `arm-reg ICC_IAR1_EL1` (system register, not GIC memory-mapped) |

---

## Prerequisites

Before any query, build the GIC cache:
```bash
python3 tools/build_gic_index.py
```

---

## Path resolution

```bash
REPO=$(git rev-parse --show-toplevel)
SCRIPT="$REPO/tools/query_gic.py"
```

---

## Commands

### All fields for a register
```bash
python3 "$SCRIPT" GICD_CTLR
python3 "$SCRIPT" GICR_WAKER
python3 "$SCRIPT" GITS_CTLR
```
Returns: register name, block, offset, width, GIC version applicability, and a table of all
fields with bit ranges, access types, and reset values.

### Single field detail
```bash
python3 "$SCRIPT" GICD_CTLR EnableGrp0
python3 "$SCRIPT" GICD_CTLR EnableGrp1S
python3 "$SCRIPT" GICD_CTLR DS
python3 "$SCRIPT" GICR_WAKER ProcessorSleep
```
Returns: the specific field's bit range, access type, reset value, and brief description.

### GIC version filtering
```bash
python3 "$SCRIPT" GICD_CTLR --version v3
python3 "$SCRIPT" GICD_CTLR EnableGrp1NS --version v3
python3 "$SCRIPT" GITS_TYPER --version v4
```
Filters the displayed fieldsets to those applicable to the requested GIC version.
GICv4 is a superset of GICv3; all GICv3 registers and fields are present in GICv4.

### All registers in a block
```bash
python3 "$SCRIPT" --block GICD
python3 "$SCRIPT" --block GICR
python3 "$SCRIPT" --block GITS
python3 "$SCRIPT" --block GICD --version v4
```
Returns: a table of all registers in the specified component, with offsets and titles.

### Register name search
```bash
python3 "$SCRIPT" --list CTLR
python3 "$SCRIPT" --list ENABL
python3 "$SCRIPT" --list GR
```
Returns: all GIC register names containing the pattern.

### ICC_* system register cross-reference
```bash
python3 "$SCRIPT" --icc-xref ICC_IAR1_EL1
python3 "$SCRIPT" --icc-xref ICC_PMR_EL1
python3 "$SCRIPT" --icc-xref ICC_IGRPEN1_EL1
```
Returns: the ICC register's brief description and a redirect to `arm-reg` for field details.
Use this to help users who ask about the CPU interface side of GICv3.

---

## Key GIC concepts

**Three address regions:**
- **GICD** (Distributor) — one per GIC; controls SPI routing and distribution
- **GICR** (Redistributor) — one per PE; controls per-PE SGIs/PPIs and LPIs
- **GITS** (ITS) — optional; translates MSI writes to LPI interrupts

**Interrupt groups (GICv3 security model):**
- Group 0: Secure FIQs → GICD_CTLR.EnableGrp0, ICC_IGRPEN0_EL1
- Secure Group 1: Secure IRQs → GICD_CTLR.EnableGrp1S, ICC_IGRPEN1_EL1 (Secure)
- Non-secure Group 1: NS IRQs → GICD_CTLR.EnableGrp1NS, ICC_IGRPEN1_EL1 (NS)
- Assignment: GICD_IGROUPR<n> (group bit) + GICD_IGRPMODR<n> (modifier)

**Affinity routing (GICv3 feature):**
- Enable with GICD_CTLR.ARE_S / ARE_NS = 1
- Route SPIs with GICD_IROUTER<n> using Aff3.Aff2.Aff1.Aff0 or IRM=1 (any PE)

**LPI / MSI flow (GITS + GICR):**
1. Configure LPI table: GICR_PROPBASER (priority/enable table), GICR_PENDBASER (pending table)
2. Enable LPIs: GICR_CTLR.EnableLPIs = 1
3. Configure ITS: GITS_CBASER (command queue), GITS_CTLR.Enabled = 1
4. Use ITS commands (MAPD, MAPC, MAPTI, INT) to configure device→interrupt→PE mapping

**vGIC (GICv4):**
- GICR_TYPER.VLPIS = 1 if virtual LPI injection is supported
- GITS_TYPER.VMOVP indicates VMOVP command support

---

## GIC initialisation sequence (typical)

1. Check GICD_TYPER for number of SPIs, security support, LPI support
2. Enable affinity routing: GICD_CTLR.ARE_S/ARE_NS = 1
3. Configure interrupt groups: GICD_IGROUPR<n> + GICD_IGRPMODR<n>
4. Set interrupt priorities: GICD_IPRIORITYR<n>
5. Enable interrupts: GICD_ISENABLER<n>
6. Enable distribution: GICD_CTLR.EnableGrp0/EnableGrp1NS/EnableGrp1S = 1
7. Per-PE: Check GICR_TYPER.Last; wake up with GICR_WAKER.ProcessorSleep = 0
8. Wait for GICR_WAKER.ChildrenAsleep = 0
9. Configure CPU priority: ICC_PMR_EL1 (arm-reg)
10. Enable Group 1: ICC_IGRPEN1_EL1 = 1 (arm-reg)

---

## ICC_* cross-reference summary

The following system registers complement the GIC memory-mapped interface.
Use `arm-reg <NAME>` to query their fields:

| Register | Purpose |
|----------|---------|
| ICC_IAR0/1_EL1 | Acknowledge interrupt (get INTID) |
| ICC_EOIR0/1_EL1 | End of interrupt |
| ICC_PMR_EL1 | Priority mask |
| ICC_BPR0/1_EL1 | Binary point (preemption) |
| ICC_CTLR_EL1/EL3 | CPU interface control |
| ICC_SRE_EL1/EL2/EL3 | System register enable |
| ICC_IGRPEN0_EL1 | Group 0 enable |
| ICC_IGRPEN1_EL1/EL3 | Group 1 enable |

---

## Example interactions

**User:** "How do I enable Group 0 interrupts in the GIC?"
```bash
python3 "$SCRIPT" GICD_CTLR EnableGrp0
```
Report: bit [0], access RW, reset 0. Then explain that ICC_IGRPEN0_EL1 also needs to be set.

**User:** "What are all the GICR registers?"
```bash
python3 "$SCRIPT" --block GICR
```
List all Redistributor registers with offsets and titles.

**User:** "What is EnableGrp1 in GICD_CTLR?"
```bash
python3 "$SCRIPT" GICD_CTLR --version v3
```
Show all fieldsets and point out that EnableGrp1S/EnableGrp1NS are the secure-state fields,
while EnableGrp1 appears in the single-security-state fieldset.

**User:** "How does the ITS work?"
```bash
python3 "$SCRIPT" --block GITS
python3 "$SCRIPT" GITS_CBASER
python3 "$SCRIPT" GITS_CTLR
```
Explain the ITS command queue mechanism and LPI translation flow.

**User:** "What does ICC_IAR1_EL1 do?"
```bash
python3 "$SCRIPT" --icc-xref ICC_IAR1_EL1
```
Report the brief and redirect to `arm-reg ICC_IAR1_EL1` for field details.
