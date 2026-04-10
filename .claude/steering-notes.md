# Steering Notes — ARM MRS Project

Last updated: 2026-04-11 by arm-mrs-steward (research session 2)

---

## BLOCKING — Must Address Before New Work

### P0: Update `.claude/skills/arm-pmu.md` (Day 6 — Permission Blocked)

**Issue**: `.claude/skills/arm-pmu.md` still references ~8 CPUs while actual PMU data covers 38 entries (36 CPUs + 2 architectural baselines) with 5,953 events.

**Status (2026-04-11)**: Attempted again — same permission error. Edit tool returns `Claude requested permissions to write to .claude/skills/arm-pmu.md, but you haven't granted it yet.`

**Required human action**: Either (a) grant the agent write permission to `.claude/skills/arm-pmu.md` during the next session, or (b) manually apply the update. The prepared content includes all 38 entries grouped by family (Cortex-A, Cortex-X, Neoverse, Common Baselines, Other) with architecture versions and event counts.

---

## Research Findings (2026-04-11, Session 2)

### Armv9.7-A Announced (2025 A-Profile Developments)

ARM announced **Armv9.7-A** with these key extensions:
- SVE/SME instructions for **6-bit data types** (OCP MXFP6 format)
- **Domain-based TLB invalidation** for scalability
- **MPAMv2** — Memory System Resource Partitioning and Monitoring v2
- New video codec instructions: SABAL, UABAL, SQRSHRN, UQRSHRN, ADDQP
- Limited Order Region support extended to **Realms**
- Separate **kernel/user PAC controls**
- Nested hypervisor optimizations

**Impact on project**: Our MRS data (v9Ap6-A Build 445) does not include v9.7 features. When a new MRS build is released with v9Ap7 support, Features.json/Instructions.json/Registers.json will need updating.

### GICv5 Announced

Major architectural overhaul:
- **Distributor (GICD) and Redistributor (GICR) replaced** by Interrupt Routing Service (IRS)
- **New IWB (Interrupt Wire Bridge)** for wired signal conversion
- **New GIC Stream protocol** for CPU-IRS communication
- No limits on wired interrupt count; no globally synchronized MMIO registers
- Direct interrupt injection to Realms (no EL2 traps)
- Linux kernel patches already in v6 (patchew.org)

**Impact on project**: GICv5 is a fundamentally different architecture. Current GIC data (v3/v4) remains valid for existing hardware. GICv5 support would require a new `gicv5/` data directory when silicon ships.

### Armv9.6-A Features (Confirmed)

18 new FEAT_* extensions: FEAT_FPRCVT, FEAT_LSFE, FEAT_F8F32MM, FEAT_F8F16MM, FEAT_SME2p2, FEAT_SVE2p2, FEAT_SVE_AES2, FEAT_SVE_F16F32MM, FEAT_SVE_BFSCALE, FEAT_SSVE_AES, FEAT_LSUI, FEAT_OCCMO, FEAT_PCDPHINT, FEAT_PoPS, FEAT_SSVE_BitPerm, FEAT_SSVE_FEXPA, FEAT_SME_MOP4, FEAT_TMOP

GCC 16 has already landed Armv9.6-A target support.

### Newer MRS Builds May Exist

References found to:
- `AARCHMRS_A_profile-2024-12.tar.gz` (December 2024)
- `AARCHMRS_OPENSOURCE_A_profile_FAT-2025-09_ASL0.tar.gz` (September 2025)
- System register data for 2025-06 and 2025-12 on developer.arm.com

Our current data is v9Ap6-A Build 445 (March 2025). **A September 2025 or later build likely includes v9.6 features.** The ARM developer download page is JavaScript-rendered and couldn't be scraped to confirm download links.

**Recommended action**: Human should check https://developer.arm.com/architectures/cpu-architecture/a-profile/exploration-tools for the latest BSD AARCHMRS download and update the source JSON files if a newer build is available.

### PMU Profile Availability

All 56 upstream files in ARM-software/data checked. Breakdown:
- **36 AArch64 CPU profiles**: Already in our pmu/ directory (complete coverage)
- **2 architectural baselines**: common_armv8.json (463 events), common_armv9.json (476 events) — **added this session**
- **7 Cortex-R profiles**: R-profile, not relevant
- **6 ARMv7 profiles**: 32-bit only, not relevant
- **2 ARMv6 profiles**: Ancient, not relevant
- **1 common_armv7**: Not relevant
- **1 schema file**: Reference only
- **1 cpus.json**: Reference only

No new AArch64 CPU PMU profiles exist upstream. Cortex-A730 and Cortex-A530 have appeared in Rockchip RK3668 silicon but no PMU event data is published yet.

---

## Completed This Session (2026-04-11, Session 2)

### PMU: Added common_armv8 and common_armv9 architectural baselines

- Downloaded `common_armv8.json` (463 events, armv8-a) and `common_armv9.json` (476 events, armv9-a) from ARM-software/data
- These define the architectural baseline PMU events common to all v8 and v9 CPUs
- PMU total: 38 entries, 5,953 events, 671 unique event names
- 8 new eval tests added, all 461 tests pass (100%)

---

## Informational

- ARM MRS steward eval suite growth: 352 -> 387 -> 406 -> 423 -> 441 -> 453 -> 461 over 7 sessions
- EX-2b PMU at 38/40 — 2 short of target, blocked on upstream data availability
- P0 arm-pmu.md is day 6 of permission blocking — human intervention still needed

## Next Session Recommendations

1. **Check for newer MRS builds** — human should visit ARM developer portal for v9Ap6+ builds
2. **Continue P0 arm-pmu.md** or escalate for manual intervention
3. **GICv5 tracking** — when IRS specification is publicly available, consider `gicv5/` data directory
4. **Armv9.7-A features** — when new MRS build drops, update Features.json and rebuild all caches
5. **Cortex-A730/A530 PMU** — monitor ARM-software/data for new profile additions
