# Steering Notes — ARM MRS Project

Last updated: 2026-04-12 by arm-mrs-steward (session 8)

---

## BLOCKING — Must Address Before New Work

### P0: Update `.claude/skills/arm-pmu.md` (Day 7 — Permission Blocked)

**Issue**: `.claude/skills/arm-pmu.md` still references ~8 CPUs while actual PMU data covers 38 entries (36 CPUs + 2 architectural baselines) with 5,953 events.

**Status (2026-04-12)**: Attempted again — same permission error. Edit tool returns: `Claude requested permissions to write to .claude/skills/arm-pmu.md, but you haven't granted it yet.`

**Root cause**: This is a Claude Code **tool permission** restriction, NOT a filesystem permission issue. The file has normal permissions (rw-rw-r--, owned by jonas). The Claude Code session does not have write authorization for the `.claude/skills/` directory.

**Exact error path**: Edit tool → `.claude/skills/arm-pmu.md` → "Claude requested permissions to write to .claude/skills/arm-pmu.md, but you haven't granted it yet."

**Required human action**: Grant Claude Code write permission to `.claude/skills/` during a session (approve the permission prompt when it appears), OR manually apply the update from `/tmp/arm-pmu-md-patch.txt`.

---

## Completed This Session (2026-04-12, Session 8)

### CoreSight: ETM expanded from 16 to 29 registers (stretch target 20+ met)

Added 13 ETM registers:
- **Stall/flow control**: TRCSTALLCTLR (FIFO overflow stall), TRCBBCTLR (branch broadcast)
- **Trace identification**: TRCTRACEIDR (ATB trace source ID)
- **Sequencer**: TRCSEQSTR (current sequencer state)
- **Counters**: TRCCNTRLDVR\<n\> (reload value), TRCCNTCTLR\<n\> (control), TRCCNTVR\<n\> (current value)
- **Resource selectors**: TRCRSCTLR\<n\> (hardware resource selection for event generation)
- **Address comparators**: TRCACVR\<n\> (64-bit address value), TRCACATR\<n\> (access type/EL matching)
- **Identification/control**: TRCIDR1 (arch revision), TRCOSLAR (OS lock), TRCPDCR (power down control)

### CoreSight: CTI expanded from 12 to 17 registers (stretch target 15+ met)

Added 5 CTI registers:
- **Device control**: CTIDEVCTL (power-on request for Debug over Power Down)
- **Affinity**: CTIDEVAFF0/CTIDEVAFF1 (MPIDR_EL1 of connected PE)
- **Software lock**: CTILAR (lock access, write-only), CTILSR (lock status, read-only)

### Eval suite: 461 → 488 tests (100% pass)

Added 27 new CoreSight tests: 20 ETM register/field tests + 7 CTI register/field tests.

### Total CoreSight coverage: 89 registers across 8 components

| Component | Registers |
|-----------|-----------|
| ETM | 29 |
| CTI | 17 |
| STM | 5 |
| ITM | 4 |
| TPIU | 6 |
| CSTF | 8 |
| CSRT | 7 |
| ID_BLOCK | 13 |

---

## EX-3 Milestone Proposal (per reviewer request)

The reviewer requested a proposal for the next milestone covering architecture tracking and data preparation for upcoming ARM specs.

### Proposed: EX-3 — Architecture Evolution Tracking

**Goal:** Prepare the project for Armv9.7-A features, GICv5, and newer MRS builds.

#### EX-3a — Newer MRS Build Integration
- **Task**: Download and evaluate the September 2025 or later AARCHMRS build (if available)
- **Impact**: Features.json, Instructions.json, Registers.json would be updated to include Armv9.6-A features (18 new FEAT_* extensions: FEAT_FPRCVT, FEAT_LSFE, FEAT_F8F32MM, etc.)
- **Action**: Human must check https://developer.arm.com/architectures/cpu-architecture/a-profile/exploration-tools
- **Dependencies**: Rebuild all caches after source file update
- **Status**: Blocked — human action required to download newer MRS build

#### EX-3b — Armv9.7-A Feature Tracking
- **Task**: Create a tracking document for Armv9.7-A extensions when they appear in MRS data
- **Key features**: SVE/SME 6-bit data types, domain-based TLB invalidation, MPAMv2, new video codec instructions, separate kernel/user PAC controls
- **Action**: Monitor ARM announcements and MRS builds for v9Ap7 features
- **Status**: Planned — waiting for spec availability

#### EX-3c — GICv5 Data Preparation
- **Task**: When the GICv5 specification (IRS/IWB architecture) becomes stable, create `gicv5/` data directory
- **Key changes from GICv3/v4**: GICD/GICR replaced by Interrupt Routing Service (IRS), new IWB for wired signals, GIC Stream protocol, no limit on wired interrupt count
- **Action**: Monitor ARM specification releases for stable GICv5 spec
- **Status**: Blocked — GICv5 spec in beta, not yet stable

#### EX-3d — PMU Profile Monitoring
- **Task**: Monitor ARM-software/data for new CPU PMU profiles (Cortex-A730, A530, X925AE, A720AE, A520AE)
- **Status**: Ongoing — check periodically

**Note:** This proposal is written in the session log per reviewer instructions, not as a ROADMAP edit. The reviewer should decide whether to formalize EX-3 in the ROADMAP.

---

## Research Findings (2026-04-11, Session 7)

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

Our current data is v9Ap6-A Build 445 (March 2025). **A September 2025 or later build likely includes v9.6 features.**

**Recommended action**: Human should check https://developer.arm.com/architectures/cpu-architecture/a-profile/exploration-tools for the latest BSD AARCHMRS download and update the source JSON files if a newer build is available.

---

## Informational

- ARM MRS steward eval suite growth: 352 -> 387 -> 406 -> 423 -> 441 -> 453 -> 461 -> 488 over 8 sessions
- EX-2a CoreSight stretch targets now met: ETM 29/20+, CTI 17/15+
- EX-2b PMU at 38/40 — 2 short of target, blocked on upstream data availability
- P0 arm-pmu.md is day 7 of Claude Code permission blocking — human intervention still needed
- Total CoreSight registers: 89 across 8 components

## Next Session Recommendations

1. **Check for newer MRS builds** — human should visit ARM developer portal for v9Ap6+ builds
2. **Resolve P0 arm-pmu.md** — grant Claude Code write permission to `.claude/skills/` or manually apply patch
3. **GICv5 tracking** — when IRS specification is publicly available, consider `gicv5/` data directory
4. **Consider formalizing EX-3** — see proposal above for architecture evolution tracking milestone
5. **Cortex-A730/A530 PMU** — monitor ARM-software/data for new profile additions

## 2026-04-12 — Project Reviewer Feedback

**Verdict**: needs-correction

**Required Actions (next session):**
1. Continue CoreSight data quality improvements if any gaps remain.
2. Begin documenting the EX-3 milestone formally in ROADMAP.md (which IS writable, unlike `.claude/`).
3. If arm-pmu.md is still blocked, create the skill content in an alternative location (e.g., `docs/arm-pmu-draft.md`) so the content is ready when permissions are fixed.


## 2026-04-13 — Project Reviewer Feedback

**Verdict**: needs-correction

**Required Actions (next session):**
1. Do not retry arm-pmu.md creation — wait for human intervention.
2. Focus on eval test expansion (target 500+) and research tracking.
3. If human has approved EX-3 scope, begin implementation.


## 2026-04-16 — Project Reviewer Feedback

**Verdict**: needs-correction

**Required Actions (next session):**
1. Do not retry arm-pmu.md — document in session summary that human action is required.
2. Delete `note.txt`; add it to `.gitignore`.
3. Proceed with EX-3b (Armv9.7-A) and additional FEAT_* documentation.

