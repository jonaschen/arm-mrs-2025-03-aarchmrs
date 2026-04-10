# Steering Notes — ARM MRS Project

Last updated: 2026-04-11 by arm-mrs-steward

---

## BLOCKING — Must Address Before New Work

### P0: Update `.claude/skills/arm-pmu.md` (Day 6 — Permission Blocked)

**Issue**: `.claude/skills/arm-pmu.md` still references ~8 CPUs while actual PMU data covers 36 CPUs with 5,014+ events.

**Status (2026-04-11)**: Attempted again — same permission error. Edit tool returns `Claude requested permissions to write to .claude/skills/arm-pmu.md, but you haven't granted it yet.`

**Required human action**: Either (a) grant the agent write permission to `.claude/skills/arm-pmu.md` during the next session, or (b) manually apply the update. The prepared content includes all 36 CPUs grouped by family (Cortex-A, Cortex-X, Neoverse, Other) with architecture versions and event counts.

---

## Completed This Session (2026-04-11)

### EX-2a Complete: CoreSight 69→71 registers ✅

Added 2 new ETM sequencer registers:
- **TRCSEQEVR0** — Sequencer State Transition Event Register 0 (forward/back event selectors)
- **TRCSEQRSTEVR** — Sequencer Reset Event Register (reset event selector)

ETM now has 16 registers. EX-2a target (70+ registers, 8+ components) is met with 71 registers.

### EX-2d Complete: Eval suite 441→453 tests ✅

- 6 new CoreSight tests for ETM sequencer registers (TRCSEQEVR0, TRCSEQRSTEVR fields)
- 3 new GIC search tests (SYNCR, VPROPBASER, PIDR2 cross-spec search)
- 3 new PMU search tests (BR_MIS, STALL, INST_RETIRED cross-CPU search)
- All 453 tests pass (100%)

### EX-2 Milestone: 3/4 sub-milestones complete ✅

| Sub-milestone | Target | Current | Status |
|---------------|--------|---------|--------|
| EX-2a CoreSight | 70+ regs, 8+ components | 71 regs, 8 components | ✅ Complete |
| EX-2b PMU | 40+ CPUs | 36 CPUs | Externally blocked (no upstream data) |
| EX-2c GIC | 50+ registers | 52 registers | ✅ Complete |
| EX-2d Eval | 450+ tests | 453 tests | ✅ Complete |

---

## Informational

- ARM MRS steward eval suite growth: 352 → 387 → 406 → 423 → 441 → 453 over 6 days
- EX-2 milestone is effectively complete — only EX-2b remains, blocked on ARM-software/data upstream
- P0 arm-pmu.md is day 6 of permission blocking — human intervention still needed

## 2026-04-11 — Session Notes for Reviewer

**Actions taken:**
1. Attempted P0 (arm-pmu.md) — still blocked by permissions (day 6)
2. Expanded CoreSight from 69 to 71 registers — EX-2a target met
3. Added 12 new eval tests — EX-2d target met (453/450)
4. All 453 eval tests pass (100%)
5. Updated ROADMAP.md: EX-2 milestone marked complete (3/4 + 1 externally blocked)

**Next session recommendations:**
- EX-2 is effectively done. Consider defining new milestones (SMMU, CI/CD, MRS refresh tracking)
- Continue attempting P0 arm-pmu.md or escalate for manual intervention
- Could continue ETM/CTI register expansion beyond minimum targets
