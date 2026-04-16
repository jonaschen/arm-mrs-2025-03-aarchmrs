# ARM FEAT_* Tracking Log

Ongoing log of ARM Armv9.6-A and Armv9.7-A `FEAT_*` identifiers, their
coverage in the current AARCHMRS data (v9Ap6-A Build 445, March 2025),
and gaps relative to public ARM announcements.

> This is a working document maintained by the `arm-mrs-steward` agent.
> When a newer MRS build is ingested (see ROADMAP EX-3a), update the
> presence/min-version columns against the new data.

---

## Build 445 Coverage Snapshot

- Source: `Features.json` (`_meta` → `schema_version: 2.5.5`, `build_number: 445`)
- Total `FEAT_*` parameters in cache: **361**
- Max `min_version` tag observed: **v9Ap5**
  (no feature in Build 445 is tagged with `min_version: v9Ap6`; feature adds
  appear staged across earlier point revisions even though the release is
  labelled v9Ap6-A)

---

## Armv9.6-A FEAT_* Identifiers

22 identifiers publicly associated with Armv9.6-A have been cross-checked
against Build 445. **18/22 are present** in the current data; **4 are
absent** (expected to arrive in a later MRS build).

### Present in Build 445 (18)

| Identifier          | `min_version` | Notes |
|---------------------|---------------|-------|
| FEAT_PCDPHINT       | v9Ap0         | Producer-consumer DP hint |
| FEAT_F8F16MM        | v9Ap2         | FP8-to-FP16 matrix multiply |
| FEAT_F8F32MM        | v9Ap2         | FP8-to-FP32 matrix multiply |
| FEAT_SVE_BFSCALE    | v9Ap2         | SVE BFloat16 scaling |
| FEAT_SVE_F16F32MM   | v9Ap2         | SVE FP16-to-FP32 matmul |
| FEAT_LSFE           | v9Ap3         | Large System Float Extensions |
| FEAT_SME_MOP4       | v9Ap4         | SME MOP4 outer product |
| FEAT_SSVE_BitPerm   | v9Ap4         | Streaming SVE bit permutation |
| FEAT_SSVE_FEXPA     | v9Ap4         | Streaming SVE FEXPA |
| FEAT_CMPBR          | v9Ap5         | Compare and Branch |
| FEAT_FPRCVT         | v9Ap5         | FP register convert |
| FEAT_LSUI           | v9Ap5         | Load/Store Unprivileged Improved |
| FEAT_OCCMO          | v9Ap5         | Outer cache clean for memory ops |
| FEAT_PoPS           | v9Ap5         | Point of Physical Storage |
| FEAT_SME2p2         | v9Ap5         | SME2.2 |
| FEAT_SSVE_AES       | v9Ap5         | Streaming SVE AES |
| FEAT_SVE2p2         | v9Ap5         | SVE2.2 |
| FEAT_SVE_AES2       | v9Ap5         | SVE AES variant 2 |

### Absent in Build 445 (4 — expected in newer MRS build)

| Identifier    | Expected role |
|---------------|---------------|
| FEAT_BTIE     | Enhanced Branch Target Identification |
| FEAT_F16MM    | Half-precision floating-point matrix multiply-accumulate (non-SVE) |
| FEAT_MTETC    | MTE tag cache store and zero instructions |
| FEAT_TMOP     | SME TMOP (outer-product) instructions |

**Impact**: Queries to `arm-feat FEAT_BTIE/F16MM/MTETC/TMOP` return
"feature not found" today. Skills correctly refuse to synthesise
descriptions; this is spec-grounded behaviour.

Cross-reference: `arm-cpusysregs/docs/features.md` (revision 2025-12, 412
features total in that catalogue) independently confirms all four as
Armv9.6-A additions.

---

## Armv9.7-A FEAT_* Identifiers

Per public ARM announcements, the following Armv9.7-A additions are known.
The "Optional in" column reflects when the feature first became available
optionally; Armv9.7-A makes each of these mandatory.

| Identifier        | Optional in | Description (per features.md rev 2025-12)                |
|-------------------|-------------|----------------------------------------------------------|
| FEAT_EAESR        | Armv9.0     | Enable Abort Exception System Registers                  |
| FEAT_FDIT         | Armv9.4     | Force Data Independent Timing                            |
| FEAT_PAuth_EnhCtl | Armv9.6     | Enhanced controls for pointer authentication             |

All three are absent from Build 445, which is expected (v9Ap6-A does not
include v9.7 features). A v9Ap7 MRS build has not yet been published by
ARM as of this log entry. The September 2025 BSD build
(`AARCHMRS_OPENSOURCE_A_profile_FAT-2025-09_ASL0.tar.gz`) likely still
tops out at v9.6.

Source: `arm-cpusysregs/docs/features.md` (lelegard/arm-cpusysregs, rev
2025-12) enumerates exactly three Armv9.7-A mandatory features. No further
FEAT_* identifiers have been publicly disclosed for Armv9.7-A beyond these.

### Documented Armv9.7-A additions beyond FEAT_* parameters

- SVE/SME instructions for 6-bit data types (OCP MXFP6 format)
- Domain-based TLB invalidation for scalability
- MPAMv2 — Memory System Resource Partitioning and Monitoring v2
- Video codec instructions: SABAL, UABAL, SQRSHRN, UQRSHRN, ADDQP
- Limited Order Region support extended to Realms
- Separate kernel/user PAC controls (tracked by FEAT_PAuth_EnhCtl)
- Nested hypervisor optimisations

---

## Verification Commands

Confirm presence counts directly from the cache (requires built cache):

```
python3 -c "
import json
feats = json.load(open('cache/features.json'))
names = {f['name'] for f in feats}
print('present in cache:', sum(1 for n in [
  'FEAT_PCDPHINT','FEAT_F8F16MM','FEAT_F8F32MM','FEAT_SVE_BFSCALE',
  'FEAT_SVE_F16F32MM','FEAT_LSFE','FEAT_SME_MOP4','FEAT_SSVE_BitPerm',
  'FEAT_SSVE_FEXPA','FEAT_CMPBR','FEAT_FPRCVT','FEAT_LSUI','FEAT_OCCMO',
  'FEAT_PoPS','FEAT_SME2p2','FEAT_SSVE_AES','FEAT_SVE2p2','FEAT_SVE_AES2'
] if n in names))
"
```

Expected output: `present in cache: 18`

---

## Action Items

- **EX-3a (human-gated)**: When Jonas downloads a newer MRS build, re-run
  the comparison and move absent entries to the present table.
- **EX-3b (agent-ongoing)**: Watch ARM announcements and developer.arm.com
  for additional Armv9.7-A `FEAT_*` names; add to the "Armv9.7-A" table
  as they are disclosed.
- **Hallucination guard**: Eval suite should include tests that
  `FEAT_BTIE`, `FEAT_F16MM`, `FEAT_MTETC`, `FEAT_TMOP`, `FEAT_EAESR`,
  `FEAT_FDIT`, and `FEAT_PAuth_EnhCtl` are NOT present in the current
  cache — so a future regression that fabricates these would be caught.

---

## PMU Upstream Monitoring (2026-04-17)

Direct listing of `github.com/ARM-software/data/pmu/` confirms no new
A-profile or Neoverse CPU profiles have been added since our last sync.

- Our 38-entry AArch64 set is complete against upstream's A-profile AArch64
  subset.
- Upstream commit 2026-02-23 ("Add A725, X925, R52+") refreshed existing
  a725/x925 entries plus added cortex-r52+ (R-profile — out of scope).
  SHA-256 of `pmu/cortex-a725.json` and `pmu/cortex-x925.json` match
  upstream exactly; no refresh needed.
- Still absent upstream: Cortex-A730, Cortex-A530, Cortex-X5, and the
  automotive ...AE variants (A520AE, A720AE, X925AE). Silicon exists
  (Rockchip RK3668 uses A730/A530; Cortex-X5 codenamed Logan is in
  2026-generation SoCs), but ARM has not published PMU event lists yet.

## ARM C1 Family — PMU Data Not Yet Published (2026-04-17)

ARM announced the new **C1 CPU cluster** in September 2025 as part of the
Lumex Compute Subsystem (CSS) platform. Four variants are Armv9.3-A-based
with native SME2 hardware matrix acceleration:

| Variant      | Role                       | Prior-gen analogue |
|--------------|----------------------------|--------------------|
| C1-Ultra     | Flagship big core          | Cortex-X925        |
| C1-Premium   | Sub-flagship big core      | (new tier)         |
| C1-Pro       | Mid-tier big core          | Cortex-A725        |
| C1-Nano      | Efficiency / LITTLE core   | Cortex-A520        |

**Impact on project**: Consumer devices launched Q1–Q2 2026, but no PMU
event JSON for any C1 variant exists upstream yet. Add to EX-3d watch
list; if/when upstream publishes, integrate via `build_pmu_index.py`.

---

Last updated: 2026-04-17 (arm-mrs-steward session — research pass)
