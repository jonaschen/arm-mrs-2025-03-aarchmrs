# Android Software Owner — ARM Agent Skills Development Plan

This document is the development plan for extending the ARM agent skills project to cover the
software components that Android device owners maintain: the **little-kernel (LK) bootloader**
and **ARM Trusted Firmware (ATF / TF-A)**. Both components run on ARM AArch64 silicon at
privilege levels that require direct interaction with the same system registers and instruction
encodings already modelled in the AARCHMRS foundation skills (Parts I–III).

> **Prerequisite:** All AARCHMRS foundation skills (M0–H6) must be complete before adding
> the Android-specific layers defined here. See `AARCH64_AGENT_SKILL_DEV_PLAN.md`.

---

## Background — Android Firmware Stack

A typical Android device boots through several firmware stages, each running at a specific
ARM exception level:

```
┌─────────────────────────────────────────────────────────────┐
│  EL3  │  ARM Trusted Firmware BL1 / BL2 / BL31              │
│       │  (Secure Monitor, PSCI, SMC dispatch)                │
├───────┼─────────────────────────────────────────────────────┤
│  S-EL1│  BL32: OP-TEE / Trusted OS / Secure Partition       │
│       │  (TrustZone secure world OS)                         │
├───────┼─────────────────────────────────────────────────────┤
│  EL2  │  Hypervisor (optional; pKVM on Android 12+)          │
├───────┼─────────────────────────────────────────────────────┤
│  EL1  │  BL33: little-kernel / ABL / UEFI bootloader         │
│       │  (fastboot, AVB, kernel hand-off)                    │
├───────┼─────────────────────────────────────────────────────┤
│  EL1  │  Linux kernel (loaded by bootloader)                 │
│  EL0  │  Android userspace                                   │
└───────┴─────────────────────────────────────────────────────┘
```

| Component | GitHub | Exception Level | Role |
|-----------|--------|----------------|------|
| **little-kernel (LK)** | [littlekernel/lk](https://github.com/littlekernel/lk) | EL1 (non-secure) | Second-stage bootloader: hardware init, fastboot, AVB, kernel load |
| **ARM Trusted Firmware (ATF/TF-A)** | [ARM-software/arm-trusted-firmware](https://github.com/ARM-software/arm-trusted-firmware) | EL3 / S-EL1 | Secure monitor: PSCI, SMC dispatch, TrustZone partition, boot chain |

Both components interact extensively with AArch64 system registers, exception-level-specific
instructions, and architectural security features (TrustZone, PAC, BTI, MTE). The AARCHMRS
foundation skills are directly applicable; this plan adds an Android-software-owner skill layer
on top.

---

## Part A — little-kernel (LK) Skill Set

### Overview

little-kernel is a minimal embedded OS / bootloader used as the Android Boot Loader (ABL) on
many Qualcomm and other ARM-based Android devices. Key areas where AARCHMRS skills apply:

| LK Function | Relevant ARM Skill |
|-------------|-------------------|
| UART / GPIO initialization | `arm-reg` (system register layout, MMIO) |
| CPU feature detection at boot | `arm-feat` (FEAT_* availability for current core) |
| Exception handler setup (VBAR_EL1) | `arm-reg` (VBAR_EL1 field layout) |
| Cache/MMU enable (SCTLR_EL1) | `arm-reg` (SCTLR_EL1 field layout and bits) |
| Fastboot USB descriptor assembly | `arm-instr` (instruction encoding for tight loops) |
| AVB signature verification | `arm-instr` / `arm-feat` (FEAT_SHA2, FEAT_SHA3 availability) |
| PMU profiling of boot time | `arm-pmu` (performance counter event codes) |
| GDB/JTAG debugging of LK | `arm-gdb` (GDB-MCP step/inspect/assert) |
| Cross-compiling LK for target | `arm-cross` (toolchain flags, -march, static link) |

### Skill Set Design

#### Skill A1 — `arm-lk-reg` — LK Boot Register Queries

**Purpose:** Ground little-kernel register initialization sequences in the AARCHMRS spec,
preventing incorrect bit patterns when configuring EL1 system registers during boot.

**Trigger:** User is writing or reviewing LK hardware initialization code and needs:
- The correct bit fields for `SCTLR_EL1`, `TCR_EL1`, `MAIR_EL1`, `VBAR_EL1`, etc.
- Safe reset values and writable field ranges
- Cache/MMU enable sequences

**Key registers for LK:**

| Register | Purpose in LK |
|----------|--------------|
| `SCTLR_EL1` | Enable MMU (`M`), I-cache (`I`), D-cache (`C`), alignment check (`A`) |
| `TCR_EL1` | Translation table configuration (IPS, TG0, SH0, ORGN0, IRGN0, T0SZ) |
| `MAIR_EL1` | Memory attribute index register (cache attributes for page table entries) |
| `VBAR_EL1` | Vector base address (exception table pointer) |
| `TTBR0_EL1` | Translation table base register (page table root) |
| `CPACR_EL1` | FP/SIMD access control (required before using NEON in LK) |
| `CurrentEL` | Query current exception level at runtime |
| `MIDR_EL1` | CPU identification (implementer, variant, architecture, part number) |
| `MPIDR_EL1` | Multiprocessor affinity register (core/cluster numbering) |
| `ID_AA64PFR0_EL1` | Feature availability bitmap (SVE, GIC, Advanced SIMD presence) |
| `ID_AA64MMFR0_EL1` | Memory model features (PA range, ASID size, big-endian support) |

**Skill interface:**

```bash
# Query EL1 register layout for MMU setup
python3 tools/query_register.py SCTLR_EL1

# Query specific field (e.g., MMU enable bit)
python3 tools/query_register.py SCTLR_EL1 M

# Query CPU identification fields
python3 tools/query_register.py MIDR_EL1 --access

# List all identification registers
python3 tools/query_register.py --list ID_AA64 --state AArch64
```

**Skill file:** `.claude/skills/arm-lk-reg.md`
- Positive triggers: LK register init, ABL hardware setup, SCTLR bits, MMU enable
- Negative triggers: EL3 registers (→ `arm-atf-reg`), peripheral MMIO (use `arm-reg` directly)
- Routes to existing `arm-reg` backend; no new tooling required

---

#### Skill A2 — `arm-lk-feat` — LK Feature Detection

**Purpose:** Ground little-kernel CPU feature detection sequences. LK must test for optional
features (SVE, crypto, PMU) before using them or before handing off to the kernel.

**Trigger:** User is writing LK startup code that reads `ID_AA64PFR0_EL1`,
`ID_AA64ISAR0_EL1`, `ID_AA64ISAR1_EL1`, or any other `ID_*` register to determine
supported features, and needs to cross-reference with the canonical `FEAT_*` identifiers.

**Key feature → ID register mappings for LK:**

| Feature | ID register | Field | LK usage |
|---------|-------------|-------|----------|
| `FEAT_SVE` | `ID_AA64PFR0_EL1` | `SVE` | Enable before passing SVE cap to kernel |
| `FEAT_SHA2` | `ID_AA64ISAR0_EL1` | `SHA2` | Hardware-accelerated AVB signature verify |
| `FEAT_SHA3` | `ID_AA64ISAR0_EL1` | `SHA3` | SHA3-256 in verified boot |
| `FEAT_AES` | `ID_AA64ISAR0_EL1` | `AES` | Hardware AES for disk encryption key unwrap |
| `FEAT_PMUv3` | `ID_AA64DFR0_EL1` | `PMUVer` | Performance counter availability |
| `FEAT_BTI` | `ID_AA64PFR1_EL1` | `BT` | Branch Target Identification for hardened images |
| `FEAT_MTE` | `ID_AA64PFR1_EL1` | `MTE` | Memory Tagging Extension availability |

**Skill interface:**

```bash
# Check feature availability for target architecture version
python3 tools/query_feature.py FEAT_SVE
python3 tools/query_feature.py FEAT_SHA2 --deps FEAT_AES

# Check what features are available at a specific version
python3 tools/query_feature.py --version v9Ap0

# Check feature availability for allowlist generation
python3 tools/query_allowlist.py --arch v9Ap0 --feat FEAT_SVE --summary
```

**Skill file:** `.claude/skills/arm-lk-feat.md`
- Positive triggers: LK feature detection, ID_AA64* register decode, AVB crypto selection
- Negative triggers: EL3 feature checks (→ `arm-atf-feat`), PSCI availability (→ `arm-atf-psci`)
- Routes to existing `arm-feat` and `arm-allowlist` backends; no new tooling required

---

#### Skill A3 — `arm-lk-boot` — LK Boot Sequence and Fastboot

**Purpose:** Ground LK boot sequence implementation in ARM architecture constraints. Covers
the EL1 initialization sequence, exception vector setup, and fastboot USB protocol assembly.

**Trigger:** User is implementing or debugging LK boot flow, including:
- EL1 entry sequence after BL31 → BL33 hand-off
- Exception vector table layout (`VBAR_EL1`)
- CPU initialization order (cache invalidate → MMU configure → enable)
- Fastboot USB bulk-transfer loop (tight assembly, cache coherency)
- Kernel image loading and hand-off (`br x0` to kernel entry)

**LK EL1 entry sequence (ARM-spec-grounded):**

```
1. Invalidate TLBs:   TLBI VMALLE1IS   (arm-instr: TLBI)
2. Invalidate I$:     IC IALLU         (arm-instr: IC)
3. Set MAIR_EL1:      MSR MAIR_EL1, x0 (arm-reg: MAIR_EL1)
4. Set TCR_EL1:       MSR TCR_EL1, x1  (arm-reg: TCR_EL1)
5. Set TTBR0_EL1:     MSR TTBR0_EL1, x2(arm-reg: TTBR0_EL1)
6. ISB
7. Enable MMU:        MSR SCTLR_EL1, x3 (SCTLR_EL1.M=1, .C=1, .I=1)
8. ISB
9. Set VBAR_EL1:      MSR VBAR_EL1, x4  (arm-reg: VBAR_EL1)
```

**Skill interface:**

```bash
# Verify TLBI instruction encoding
python3 tools/query_instruction.py TLBI

# Verify IC instruction encoding
python3 tools/query_instruction.py IC

# Check ISB and DSB encodings
python3 tools/query_instruction.py ISB
python3 tools/query_instruction.py DSB

# Query VBAR_EL1 layout
python3 tools/query_register.py VBAR_EL1
```

**Skill file:** `.claude/skills/arm-lk-boot.md`
- Positive triggers: LK EL1 boot sequence, cache invalidation, MMU enable, fastboot
- Negative triggers: TF-A BL31 setup (→ `arm-atf-boot`), kernel device tree (out of scope)

---

#### Skill A4 — `arm-lk-debug` — LK GDB / JTAG Debugging

**Purpose:** Ground little-kernel debugging sessions in ARM architecture knowledge.
Covers EL1 debug register setup, hardware breakpoints, and GDB-MCP integration for
AArch64 bootloader debugging.

**Key debug registers for LK:**

| Register | Purpose |
|----------|---------|
| `DBGBCR<n>_EL1` | Hardware breakpoint control |
| `DBGBVR<n>_EL1` | Hardware breakpoint value (address) |
| `DBGWCR<n>_EL1` | Hardware watchpoint control |
| `DBGWVR<n>_EL1` | Hardware watchpoint value (address) |
| `MDSCR_EL1` | Monitor debug system control (enable debug) |
| `OSLAR_EL1` | OS lock register (must unlock before setting breakpoints) |
| `EDSCR` | External debug status and control |

**Skill interface:**

```bash
# Query debug register layout
python3 tools/query_register.py DBGBCR2_EL1
python3 tools/query_register.py MDSCR_EL1

# GDB-MCP session for LK binary debugging
python3 tools/query_gdb.py ./lk.elf --break lk_main --registers

# Step through LK initialization and assert register state
python3 tools/query_gdb.py ./lk.elf --step 10 --assert "x0=0"

# SIGILL repair hint when LK uses unavailable instructions
python3 tools/query_gdb.py --sigill-hint v9Ap0 --pc 0x40001000
```

**Skill file:** `.claude/skills/arm-lk-debug.md`
- Positive triggers: LK breakpoints, fastboot hang debugging, AArch64 EL1 watchpoints
- Negative triggers: EL3 debug (→ `arm-atf-debug`), Linux kernel KGDB (out of scope)
- Routes to existing `arm-reg` and `arm-gdb` backends

---

### LK Milestone Plan

| Milestone | Description | Status |
|-----------|-------------|--------|
| A1 | `arm-lk-reg` — EL1 boot register skill | 🔲 Pending |
| A2 | `arm-lk-feat` — LK CPU feature detection skill | 🔲 Pending |
| A3 | `arm-lk-boot` — LK boot sequence and fastboot skill | 🔲 Pending |
| A4 | `arm-lk-debug` — LK GDB/JTAG debugging skill | 🔲 Pending |
| AE | LK skill correctness evaluation | 🔲 Pending |

**Milestone A1 detail:**
- [ ] **A1-1** Write `.claude/skills/arm-lk-reg.md` — positive/negative triggers, routing to `arm-reg`
- [ ] **A1-2** Verify `arm-reg` covers all key LK EL1 registers listed in §A1 above
- [ ] **A1-3** Add 8 LK register eval tests to `tools/eval_skill.py` (`--skill lk_reg`)
- [ ] **A1-4** Manual test: `SCTLR_EL1 M` returns bit 0, `MAIR_EL1` returns 8-byte ATTR fields, `MIDR_EL1` returns implementer/part/variant fields

**Milestone A2 detail:**
- [ ] **A2-1** Write `.claude/skills/arm-lk-feat.md` — feature → ID register cross-reference table
- [ ] **A2-2** Add 6 LK feature eval tests to `tools/eval_skill.py` (`--skill lk_feat`)
- [ ] **A2-3** Manual test: FEAT_SHA2 → ID_AA64ISAR0_EL1.SHA2, FEAT_BTI → ID_AA64PFR1_EL1.BT

**Milestone A3 detail:**
- [ ] **A3-1** Write `.claude/skills/arm-lk-boot.md` — EL1 entry sequence, cache operations, fastboot
- [ ] **A3-2** Add 6 LK boot eval tests to `tools/eval_skill.py` (`--skill lk_boot`)
- [ ] **A3-3** Manual test: TLBI VMALLE1IS encoding, ISB encoding, VBAR_EL1 layout

**Milestone A4 detail:**
- [ ] **A4-1** Write `.claude/skills/arm-lk-debug.md` — debug register setup, GDB session workflow
- [ ] **A4-2** Add 6 LK debug eval tests to `tools/eval_skill.py` (`--skill lk_debug`)
- [ ] **A4-3** Manual test: DBGBCR2_EL1 fields, MDSCR_EL1 KDE bit, `arm-gdb` session against LK

**Milestone AE detail:**
- [ ] **AE-1** Consolidate all LK tests under `--skill lk` in `eval_skill.py`
- [ ] **AE-2** Target: 26 LK eval tests, 100% pass rate

---

## Part B — ARM Trusted Firmware (ATF / TF-A) Skill Set

### Overview

ARM Trusted Firmware (TF-A) is the reference implementation of Secure Monitor firmware for
ARM TrustZone. It implements:

| Boot stage | Runs at | Role |
|------------|---------|------|
| BL1 | EL3 (secure) | ROM-based trusted boot: authenticates BL2 |
| BL2 | S-EL1 | Trusted Boot Firmware: loads and authenticates BL31, BL32, BL33 |
| BL31 | EL3 (runtime) | EL3 Runtime Firmware: SMC dispatch, PSCI, SPMD, RAS |
| BL32 | S-EL1 | Secure Partition: OP-TEE, TrustZone OS, or SPM-MM |
| BL33 | EL1 (non-secure) | Non-Trusted Firmware: little-kernel, UEFI, U-Boot |

TF-A is the layer between the hardware and all software stacks in an Android device. Correctness
of EL3 register programming is safety-critical: errors in SCR_EL3, HCR_EL2, or SPSR_EL3 produce
unrecoverable faults (hang, reset, or security boundary violation).

### Skill Set Design

#### Skill B1 — `arm-atf-reg` — ATF EL3 Register Queries

**Purpose:** Ground TF-A EL3 register initialization in the AARCHMRS spec. The EL3 register
set controls security boundaries, exception routing, and secure/non-secure world partition.
Errors here can silently break TrustZone isolation.

**Key EL3 registers for TF-A:**

| Register | Purpose in TF-A |
|----------|----------------|
| `SCR_EL3` | Secure Configuration Register: NS bit (world select), RW bit (EL2/EL1 AArch64 vs AArch32), IRQ/FIQ/SError routing to EL3, SMC enablement |
| `SPSR_EL3` | Saved Program Status Register EL3: exception level to return to, DAIF mask, stack pointer select |
| `ELR_EL3` | Exception Link Register EL3: return address after `ERET` (points to BL33/BL32 entry) |
| `SCTLR_EL3` | System Control Register EL3: EL3 MMU enable, cache enable |
| `TCR_EL3` | Translation Control Register EL3: EL3 page table config |
| `TTBR0_EL3` | Translation Table Base Register EL3 |
| `VBAR_EL3` | Vector Base Address Register EL3 (EL3 exception vectors) |
| `CPTR_EL3` | Architectural Feature Trap Register EL3 (FP/SVE trap control) |
| `MDCR_EL3` | Monitor Debug Configuration EL3 (debug routing between worlds) |
| `MPIDR_EL1` | Read in EL3 to determine boot CPU affinity for PSCI topology |
| `RMR_EL3` | Reset Management Register EL3 (warm reset, AA64 mode select) |
| `RVBAR_EL3` | Reset Vector Base Address (ROM entry point for BL1) |

**Critical SCR_EL3 fields for TF-A BL31:**

| Field | Bit | Meaning for TF-A |
|-------|-----|-----------------|
| `NS` | 0 | 0=secure world, 1=non-secure. BL31 sets to 0 for BL32, 1 for BL33 `ERET` |
| `IRQ` | 1 | Route IRQ to EL3 when 1 (TF-A SPD takes IRQs) |
| `FIQ` | 2 | Route FIQ to EL3 when 1 (GIC FIQ delivery to EL3) |
| `EA` | 3 | Route SError to EL3 when 1 (RAS firmware-first handling) |
| `SMD` | 7 | SMC Disable — must be 0 for SMC dispatch in BL31 |
| `HCE` | 8 | HVC Enable — must be 1 if EL2 is present |
| `RW` | 10 | 1=EL2/EL1 is AArch64, 0=AArch32 — Android always 1 |
| `ST` | 11 | Secure EL1 access to Physical Counter/Timer |
| `TWI` | 12 | Trap WFI to EL3 — usually 0 for TF-A |
| `TWE` | 13 | Trap WFE to EL3 — usually 0 for TF-A |
| `APK` | 16 | Pointer Auth key access to EL3 — enable to prevent key leakage between worlds |
| `API` | 17 | Pointer Auth instr. access to EL3 — must enable for PAC in secure world |
| `TLOR` | 29 | Trap LOR instructions to EL3 |

**Skill interface:**

```bash
# Full SCR_EL3 field layout
python3 tools/query_register.py SCR_EL3

# Specific field: NS bit
python3 tools/query_register.py SCR_EL3 NS

# SPSR_EL3 layout for building ERET target state
python3 tools/query_register.py SPSR_EL3

# CPTR_EL3 trap control
python3 tools/query_register.py CPTR_EL3

# MDCR_EL3 debug routing
python3 tools/query_register.py MDCR_EL3

# List all EL3 registers
python3 tools/query_register.py --list EL3 --state AArch64
```

**Skill file:** `.claude/skills/arm-atf-reg.md`
- Positive triggers: TF-A BL31 init, SCR_EL3 bit setup, SPSR_EL3 ERET target, EL3 page tables
- Negative triggers: EL1 registers (→ `arm-lk-reg` or `arm-reg`), GIC secure config (→ `arm-gic`)

---

#### Skill B2 — `arm-atf-psci` — PSCI SMC Calling Convention

**Purpose:** Ground TF-A PSCI (Power State Coordination Interface) implementation in the ARM
architecture SMC calling convention. PSCI is the standard interface for CPU power management
in Linux on ARM — errors cause permanent CPU or cluster power failures.

**PSCI SMC function identifiers (SMCCC §5):**

| PSCI Function | SMC ID (SMC32) | SMC ID (SMC64) | Description |
|--------------|---------------|---------------|-------------|
| `PSCI_VERSION` | `0x84000000` | — | Returns PSCI version |
| `CPU_SUSPEND` | `0x84000001` | `0xC4000001` | Suspend current CPU |
| `CPU_OFF` | `0x84000002` | — | Power off current CPU |
| `CPU_ON` | `0x84000003` | `0xC4000003` | Power on a secondary CPU |
| `AFFINITY_INFO` | `0x84000004` | `0xC4000004` | Query CPU affinity state |
| `MIGRATE` | `0x84000005` | `0xC4000005` | Migrate trusted OS to another CPU |
| `SYSTEM_OFF` | `0x84000008` | — | System shutdown |
| `SYSTEM_RESET` | `0x84000009` | — | System warm reset |
| `SYSTEM_RESET2` | `0x84000012` | `0xC4000012` | System reset with reason |
| `MEM_PROTECT` | `0x84000013` | — | Enable/disable memory protection |
| `CPU_FREEZE` | `0x8400000B` | — | Freeze a CPU (EL3 extension) |
| `NODE_HW_STATE` | `0x8400000D` | `0xC400000D` | Query physical power domain state |

**SMC calling convention for PSCI (ARM DEN0028):**

- `x0` (or `w0` for SMC32): Function identifier
- `x1`–`x3` (or `w1`–`w3`): Input arguments
- `x0` on return: Return code (`0`=SUCCESS, negative values are error codes)
- `x1`–`x3` on return: Output values (function-dependent)
- Registers `x4`–`x17` are not preserved across an SMC call

**Key instruction encodings for TF-A:**

| Instruction | Encoding | TF-A usage |
|-------------|---------|-----------|
| `SMC #0` | `0xD4000003` | Invoke Secure Monitor from EL1/EL2 |
| `ERET` | `0xD69F03E0` | Return from EL3 to lower EL |
| `MSR VBAR_EL3, Xn` | System register write | Set EL3 exception vectors |
| `MRS Xn, MPIDR_EL1` | System register read | Read CPU affinity for PSCI topology |

**Skill interface:**

```bash
# SMC instruction encoding
python3 tools/query_instruction.py SMC

# ERET instruction encoding
python3 tools/query_instruction.py ERET

# MPIDR_EL1 affinity fields (for CPU_ON target_cpu parameter)
python3 tools/query_register.py MPIDR_EL1

# SCR_EL3 SMD bit (must be 0 for SMC to reach BL31)
python3 tools/query_register.py SCR_EL3 SMD
```

**Skill file:** `.claude/skills/arm-atf-psci.md`
- Positive triggers: PSCI implementation, CPU_ON secondary boot, system shutdown, warm reset
- Negative triggers: Linux PSCI driver (not firmware-side), HVC calls to EL2 hypervisor (→ KVM)

---

#### Skill B3 — `arm-atf-trustzone` — TrustZone Configuration

**Purpose:** Ground TF-A TrustZone memory and interrupt partitioning in the ARM architecture
spec. Misconfiguration allows non-secure software to read secure memory or intercept secure
interrupts, which is a critical security vulnerability.

**TrustZone configuration registers in TF-A:**

| Register | Purpose |
|----------|---------|
| `SCR_EL3` | Master world-select and exception routing (see §B1) |
| `TTBR0_EL3` | Secure world EL3 page tables |
| `HCR_EL2` | Hypervisor control (NS EL2 config; TGE, VM enable, tweak bits) |
| `VMPIDR_EL2` | Virtualized MPIDR for guest VMs |
| `VTTBR_EL2` | Stage 2 translation table base |
| `VTCR_EL2` | Stage 2 translation control |
| `ICC_SRE_EL3` | GIC CPU interface System Register Enable at EL3 |
| `ICC_SRE_EL2` | GIC CPU interface SRE routing to EL2/EL1 |
| `MDCR_EL3` | Debug/PMU world routing (SPME, TDOSA, TDA, TPM fields) |
| `CPTR_EL3` | FP/SVE trap routing between worlds |
| `ACTLR_EL3` | Auxiliary control (implementation-defined; MPAM routing in v8.4) |

**Skill interface:**

```bash
# HCR_EL2 field layout for TrustZone NS EL2 configuration
python3 tools/query_register.py HCR_EL2

# GIC System Register Interface enable registers
python3 tools/query_register.py ICC_SRE_EL3
python3 tools/query_register.py ICC_SRE_EL2

# MDCR_EL3 debug routing fields
python3 tools/query_register.py MDCR_EL3

# VTCR_EL2 stage-2 translation config
python3 tools/query_register.py VTCR_EL2

# Feature check: FEAT_TrustZone availability
python3 tools/query_feature.py FEAT_EL3

# Feature check: FEAT_SEL2 (Secure EL2 for S-EL2 SPM)
python3 tools/query_feature.py FEAT_SEL2
```

**Skill file:** `.claude/skills/arm-atf-trustzone.md`
- Positive triggers: TF-A TrustZone setup, secure/non-secure world isolation, SPMD, SPM
- Negative triggers: Linux KVM hypervisor config (→ separate plan), OP-TEE internals (out of scope)

---

#### Skill B4 — `arm-atf-boot` — ATF Boot Sequence and Chain of Trust

**Purpose:** Ground TF-A boot chain implementation in ARM architecture constraints. The TF-A
boot sequence involves multiple exception level transitions, authenticated image loading, and
memory layout decisions that must comply with the ARM security model.

**TF-A boot stages and EL transitions:**

```
Power-on
  │
  ▼ EL3
BL1 (ROM) — initializes EL3 registers, authenticates BL2 image
  │         MSR SCR_EL3: NS=0, RW=1, EA=1, FIQ=1, IRQ=0
  │         MSR SPSR_EL3: M=0b00101 (S-EL1), DAIF=0xF
  │         MSR ELR_EL3: &bl2_entrypoint
  │         ERET  ──────────────────────────────────────────► S-EL1
  │
  ▼ S-EL1
BL2 (Trusted Boot) — loads and authenticates BL31, BL32, BL33
  │  Issues SMC to BL1 for EL3 services (COT, image load)
  │  Returns to EL3 via SMC  ◄─────────────────────────────── EL3
  │
  ▼ EL3
BL31 (Runtime) — sets up PSCI/SMC dispatch, then hands off
  │  MSR SCR_EL3: NS=0, configure for BL32
  │  MSR SPSR_EL3: M=0b00101 (S-EL1)
  │  MSR ELR_EL3: &bl32_entrypoint
  │  ERET  ──────────────────────────────────────────────────► S-EL1
  │  (BL32 issues SMC back to BL31 when done)
  │  MSR SCR_EL3: NS=1, configure for BL33
  │  MSR SPSR_EL3: M=0b00101 (EL2) or 0b00100 (EL1t)
  │  MSR ELR_EL3: &bl33_entrypoint
  │  ERET  ──────────────────────────────────────────────────► EL2/EL1 (LK/UEFI)
```

**Skill interface:**

```bash
# SPSR_EL3 mode encoding (M field values for EL transition targets)
python3 tools/query_register.py SPSR_EL3 M

# ELR_EL3 (return address register)
python3 tools/query_register.py ELR_EL3

# ERET instruction encoding
python3 tools/query_instruction.py ERET

# ISB required after ERET preparation (MSR to ELR_EL3/SPSR_EL3)
python3 tools/query_instruction.py ISB

# FEAT_SEL2 for Secure EL2 SPM-MM support
python3 tools/query_feature.py FEAT_SEL2

# Check PAC features for TF-A pointer authentication in BL31
python3 tools/query_feature.py FEAT_PAuth
python3 tools/query_feature.py FEAT_PAuth2
```

**Skill file:** `.claude/skills/arm-atf-boot.md`
- Positive triggers: TF-A BL1/BL2/BL31/BL32/BL33 sequence, ERET target state, CoT, image auth
- Negative triggers: LK boot at EL1 (→ `arm-lk-boot`), Linux kernel boot (out of scope)

---

#### Skill B5 — `arm-atf-security` — ATF Security Hardening

**Purpose:** Ground TF-A security hardening in ARM architecture security features.
TF-A BL31 runs at the highest privilege level and must enable available hardware security
features to protect the secure monitor from non-secure world attacks.

**Security features relevant to TF-A:**

| Feature | Description | TF-A application |
|---------|-------------|-----------------|
| `FEAT_PAuth` | Pointer Authentication | Sign BL31 return addresses, link registers |
| `FEAT_PAuth2` | Enhanced Pointer Authentication | Stronger PAC codes |
| `FEAT_BTI` | Branch Target Identification | All indirect branches need BTI landing pads |
| `FEAT_MTE` | Memory Tagging Extension | Tag sensitive BL31 data structures |
| `FEAT_RNG` | Random Number Generator (`RNDR`/`RNDRRS` regs) | Entropy for key generation |
| `FEAT_CSV2` | Cache Speculation Vulnerability mitigations | Branch predictor isolation between worlds |
| `FEAT_CSV3` | Memory side-channel mitigation | Cache flush on world switch |
| `FEAT_SSBS` | Speculative Store Bypass Safe | SSBS bit in PSTATE to disable speculative stores |
| `FEAT_SB` | Speculation Barrier (`SB` instruction) | Harden BL31 SMC dispatch paths |
| `FEAT_SPECRES` | Speculation Restriction instructions | `PSBCSYNC`, `RSBCSYNC` for EL3 return paths |
| `FEAT_RAS` | Reliability, Availability, Serviceability | EL3 error record handling (ERXCTLR, ERXADDR) |

**Skill interface:**

```bash
# Check PAC availability and dependency chain
python3 tools/query_feature.py FEAT_PAuth --deps FEAT_PAuth2

# Check BTI availability
python3 tools/query_feature.py FEAT_BTI

# Check speculation mitigation features
python3 tools/query_feature.py FEAT_SSBS
python3 tools/query_feature.py FEAT_SB
python3 tools/query_feature.py FEAT_SPECRES

# RNG register access
python3 tools/query_register.py RNDR_EL0
python3 tools/query_register.py RNDRRS_EL0

# SSBS system register (in PSTATE)
python3 tools/query_register.py SCTLR_EL3 DSSBS

# Apply ISA security rules for hardened BL31 assembly
python3 tools/isa_optimize.py --list-rules --category pac
python3 tools/isa_optimize.py --list-rules --category bti
python3 tools/isa_optimize.py --auto-pac-bti --arch v9Ap0 --input bl31_entry.s
```

**Skill file:** `.claude/skills/arm-atf-security.md`
- Positive triggers: TF-A security hardening, BL31 PAC/BTI, speculation mitigation, RAS handling
- Negative triggers: Linux kernel security (SELinux, seccomp — out of scope), OP-TEE crypto

---

### ATF Milestone Plan

| Milestone | Description | Status |
|-----------|-------------|--------|
| B1 | `arm-atf-reg` — EL3 register skill | 🔲 Pending |
| B2 | `arm-atf-psci` — PSCI SMC calling convention skill | 🔲 Pending |
| B3 | `arm-atf-trustzone` — TrustZone configuration skill | 🔲 Pending |
| B4 | `arm-atf-boot` — TF-A boot sequence skill | 🔲 Pending |
| B5 | `arm-atf-security` — ATF security hardening skill | 🔲 Pending |
| BE | ATF skill correctness evaluation | 🔲 Pending |

**Milestone B1 detail:**
- [ ] **B1-1** Write `.claude/skills/arm-atf-reg.md` — EL3 register routing, SCR_EL3 field table
- [ ] **B1-2** Verify `arm-reg` backend covers all key ATF EL3 registers listed in §B1 above
- [ ] **B1-3** Add 10 ATF register eval tests to `tools/eval_skill.py` (`--skill atf_reg`)
- [ ] **B1-4** Manual test: `SCR_EL3 NS`, `SCR_EL3 RW`, `SPSR_EL3 M`, `CPTR_EL3`, `MDCR_EL3`

**Milestone B2 detail:**
- [ ] **B2-1** Write `.claude/skills/arm-atf-psci.md` — PSCI function table, SMC encoding, x0–x3 ABI
- [ ] **B2-2** Verify `arm-instr` covers SMC and ERET instruction encodings
- [ ] **B2-3** Add 8 PSCI eval tests to `tools/eval_skill.py` (`--skill atf_psci`)
- [ ] **B2-4** Manual test: SMC#0 encoding, ERET encoding, CPU_ON function ID, MPIDR_EL1 Aff0/1/2

**Milestone B3 detail:**
- [ ] **B3-1** Write `.claude/skills/arm-atf-trustzone.md` — HCR_EL2, GIC SRE, MDCR_EL3 world routing
- [ ] **B3-2** Verify `arm-reg` covers HCR_EL2, ICC_SRE_EL3, VTCR_EL2 fields
- [ ] **B3-3** Add 8 TrustZone eval tests to `tools/eval_skill.py` (`--skill atf_tz`)
- [ ] **B3-4** Manual test: HCR_EL2 VM, TGE, IMO, FMO fields; ICC_SRE_EL3.Enable; MDCR_EL3.SPME

**Milestone B4 detail:**
- [ ] **B4-1** Write `.claude/skills/arm-atf-boot.md` — EL transition diagram, SPSR_EL3 mode values
- [ ] **B4-2** Add 6 boot sequence eval tests to `tools/eval_skill.py` (`--skill atf_boot`)
- [ ] **B4-3** Manual test: SPSR_EL3.M encoding for S-EL1 (0b00101), EL2 (0b01001), EL1t (0b00100)

**Milestone B5 detail:**
- [ ] **B5-1** Write `.claude/skills/arm-atf-security.md` — security feature table, PAC/BTI for EL3
- [ ] **B5-2** Add 8 ATF security eval tests to `tools/eval_skill.py` (`--skill atf_security`)
- [ ] **B5-3** Manual test: FEAT_PAuth → SCR_EL3.API/APK, FEAT_BTI availability, speculation mitigations

**Milestone BE detail:**
- [ ] **BE-1** Consolidate all ATF tests under `--skill atf` in `eval_skill.py`
- [ ] **BE-2** Target: 40 ATF eval tests, 100% pass rate

---

## Part C — Integration and Cross-Skill Routing

### Skill C1 — `arm-android-search` — Cross-Component Discovery

**Purpose:** Route Android firmware developer queries to the correct skill when the developer
does not know which component (LK vs TF-A) handles a given register or feature.

**Routing table:**

| Query keyword | Route to |
|---------------|---------|
| `SCTLR_EL1`, `TCR_EL1`, `MAIR_EL1`, `VBAR_EL1` | `arm-lk-reg` (EL1 config) |
| `SCR_EL3`, `SPSR_EL3`, `ELR_EL3`, `CPTR_EL3` | `arm-atf-reg` (EL3 config) |
| `HCR_EL2`, `VTTBR_EL2`, `VTCR_EL2` | `arm-atf-trustzone` (stage-2 config) |
| `PSCI`, `CPU_ON`, `CPU_OFF`, `SYSTEM_RESET` | `arm-atf-psci` |
| `SMC`, `ERET`, `HVC` | `arm-atf-psci` or `arm-atf-boot` |
| `fastboot`, `AVB`, `TLBI`, `IC IALLU` | `arm-lk-boot` |
| `BL1`, `BL2`, `BL31`, `BL32`, `BL33`, `COT` | `arm-atf-boot` |
| `FEAT_PAuth`, `FEAT_BTI`, `FEAT_MTE` (in TF-A context) | `arm-atf-security` |
| `FEAT_SHA2`, `FEAT_AES` (in LK/AVB context) | `arm-lk-feat` |
| `DBGBCR`, `MDSCR_EL1` | `arm-lk-debug` |
| `PMU`, `performance counters` | `arm-pmu` |
| `GIC`, `GICD`, `GICR`, `ICC_` | `arm-gic` |

**Skill file:** `.claude/skills/arm-android-search.md`
- Positive triggers: Android firmware, ABL, ATF, TF-A, bootloader, TrustZone, PSCI

### Milestone C Plan

| Milestone | Description | Status |
|-----------|-------------|--------|
| C1 | `arm-android-search` — cross-component search and routing | 🔲 Pending |
| CE | Cross-component integration eval (routing correctness) | 🔲 Pending |

**Milestone C1 detail:**
- [ ] **C1-1** Write `.claude/skills/arm-android-search.md` with the routing table above
- [ ] **C1-2** Add 10 routing eval tests to `tools/eval_skill.py` (`--skill android_search`)
- [ ] **C1-3** Manual test: PSCI → atf_psci, SCTLR_EL1 in LK context → arm-lk-reg, SCR_EL3 → arm-atf-reg

---

## Development Timeline

```
Phase Android-1 (Month 1–2): little-kernel Skills
  ├── A1: arm-lk-reg — EL1 boot register skill          [Month 1]
  ├── A2: arm-lk-feat — CPU feature detection            [Month 1]
  ├── A3: arm-lk-boot — Boot sequence and fastboot       [Month 2]
  ├── A4: arm-lk-debug — GDB/JTAG debugging              [Month 2]
  └── AE: LK skill evaluation (26 tests)                 [Month 2]

Phase Android-2 (Month 3–4): ARM Trusted Firmware Skills
  ├── B1: arm-atf-reg — EL3 register skill               [Month 3]
  ├── B2: arm-atf-psci — PSCI SMC calling convention     [Month 3]
  ├── B3: arm-atf-trustzone — TrustZone configuration    [Month 4]
  ├── B4: arm-atf-boot — Boot sequence and CoT           [Month 4]
  ├── B5: arm-atf-security — Security hardening          [Month 4]
  └── BE: ATF skill evaluation (40 tests)                [Month 4]

Phase Android-3 (Month 5): Integration
  ├── C1: arm-android-search — cross-component routing   [Month 5]
  └── CE: Integration evaluation (10 routing tests)      [Month 5]
```

**Total new eval tests:** 76 (26 LK + 40 ATF + 10 integration)

**Prerequisite dependency:**

```
AARCHMRS Foundation (Parts I/II/III — Complete)
    │
    ├── A1–A4 (LK skills — independent, use existing arm-reg/feat/instr/gdb backends)
    ├── B1–B5 (ATF skills — independent, use existing arm-reg/feat/instr/isa-opt backends)
    └── C1   (Integration search — depends on A1–A4 + B1–B5)
```

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| EL3 register set varies between SoC implementations | Medium | Skill clearly distinguishes architected fields from IMPLEMENTATION DEFINED; warns user |
| PSCI function IDs differ between SMCCC revisions | Low | Skill documents PSCI 1.0/1.1/1.2 differences; defaults to PSCI 1.1 (most common in Android) |
| TF-A platform ports override EL3 register defaults | Medium | Skill provides spec-baseline values; notes platform code may override |
| LK is not the bootloader on all Android devices | Low | Skill focuses on ARM architecture (EL1 init) applicable to all ABL variants |
| Secure world register access denied from non-secure tools | High | arm-atf-debug explicitly requires EL3-capable debugger (Arm DS-5/DSTREAM, OpenOCD with EL3 support) |
| BSD MRS omits EL3 register prose descriptions | Low | Already handled by existing `arm-reg` skill — returns "Description not available in BSD MRS release" |

---

## References

| Resource | URL | Purpose |
|----------|-----|---------|
| **little-kernel** | https://github.com/littlekernel/lk | LK bootloader source |
| **ARM Trusted Firmware** | https://github.com/ARM-software/arm-trusted-firmware | TF-A source and documentation |
| **TF-A documentation** | https://trustedfirmware-a.readthedocs.io/ | Design and porting guides |
| **PSCI specification** | ARM DEN0022D (PSCI) | PSCI function IDs and calling convention |
| **SMCCC specification** | ARM DEN0028C (SMC Calling Convention) | SMC/HVC register usage |
| **ARM Security Model** | ARM GIC Architecture Specification IHI0069 | GIC secure world integration |
| **AARCHMRS** | Parts I–III (`AARCH64_AGENT_SKILL_DEV_PLAN.md`) | Foundation skills (prerequisite) |
| **ARM DDI 0487** | ARM Architecture Reference Manual | Authoritative EL3 register definitions |
| **FEAT_PAuth spec** | ARM DDI 0487, section D5 | Pointer authentication for EL3 hardening |
| **RAS Extension** | ARM ARM D18 | Error record registers used by TF-A RAS handlers |

---

*Plan version 1.0 — 2026-03-15. Covers Android device firmware skills: little-kernel (LK)
skills A1–A4, ARM Trusted Firmware skills B1–B5, and cross-component integration skill C1.*
