# Steering Notes — ARM MRS Project

Last updated: 2026-04-10 by arm-mrs-steward

---

## BLOCKING — Must Address Before New Work

### P0: Update `.claude/skills/arm-pmu.md` (Day 5 — Permission Blocked)

**Issue**: `.claude/skills/arm-pmu.md` still references ~8 CPUs while actual PMU data covers 36 CPUs with 5,014+ events.

**Status (2026-04-10)**: Attempted again — same permission error. Edit tool returns `Claude requested permissions to write to .claude/skills/arm-pmu.md, but you haven't granted it yet.`

**Required human action**: Either (a) grant the agent write permission to `.claude/skills/arm-pmu.md` during the next session, or (b) manually apply the update. The prepared content includes all 36 CPUs grouped by family (Cortex-A, Cortex-X, Neoverse, Other) with architecture versions and event counts.

---

## Completed This Session (2026-04-10)

### GIC Expansion: 41→52 registers (EX-2c target met) ✅

Added 11 new GIC registers across GICD and GICR blocks:
- **GICD** (5 new): GICD_ISPENDR\<n\>, GICD_ICPENDR\<n\>, GICD_ISACTIVER\<n\>, GICD_ICACTIVER\<n\>, GICD_NSACR\<n\>
- **GICR** (4 new): GICR_INVLPIR, GICR_INVALLR, GICR_SYNCR, GICR_PIDR2
- **GICv4** (2 new): GICR_VPROPBASER, GICR_VPENDBASER

EX-2c target (50+ registers) is now met with 52 registers.

### Eval suite: 423→441 tests ✅

- 18 new GIC eval tests covering pending/active state management, LPI invalidation, synchronization, peripheral ID, and GICv4 virtual LPI registers
- All 441 tests pass (100%)

---

## EX-2 Milestone Status

| Sub-milestone | Target | Current | Status |
|---------------|--------|---------|--------|
| EX-2a CoreSight | 70+ regs, 8+ components | 69 regs, 8 components | Nearly complete (1 register short) |
| EX-2b PMU | 40+ CPUs | 36 CPUs | In progress |
| EX-2c GIC | 50+ registers | 52 registers | ✅ Complete |
| EX-2d Eval | 450+ tests | 441 tests | Nearly complete (9 tests short) |

---

## Informational

- ARM MRS steward eval suite growth: 352 → 387 → 406 → 423 → 441 over 5 days
- GIC now has the strongest coverage of any extension (52 registers with GICv4 support)
- P0 arm-pmu.md is day 5 of permission blocking — human intervention still needed

## 2026-04-10 — Session Notes for Reviewer

**Actions taken:**
1. Attempted P0 (arm-pmu.md) — still blocked by permissions (day 5)
2. Expanded GIC from 41 to 52 registers — EX-2c target met
3. Added 18 new eval tests for GIC expansion
4. All 441 eval tests pass (100%)

**Remaining EX-2 work:**
- EX-2a: Add 1+ more CoreSight register (ETM or CTI expansion)
- EX-2b: Add 4+ more PMU CPU profiles
- EX-2d: Add 9+ more eval tests to reach 450 target
