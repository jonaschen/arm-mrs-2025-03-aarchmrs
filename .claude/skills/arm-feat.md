# arm-feat — ARM Architecture Feature / Extension Queries

Use this skill when the user asks about ARM architecture features or extensions:
- Whether a feature exists (`FEAT_SVE`, `FEAT_BTI`, `FEAT_MTE`, …)
- What an architecture version introduces (`v9Ap2`, `v8Ap7`, …)
- Whether one feature depends on or requires another
- Listing all features matching a name pattern

## Do NOT use this skill when the user asks about:
- Register field layout or bit positions → use `arm-reg`
- Instruction encoding, mnemonics, or assembly syntax → use `arm-instr`
- "How do I read/write a register?" → use `arm-reg`

---

## Path resolution

Resolve the query script path before running any command:

```bash
REPO=$(git rev-parse --show-toplevel)
# Or use ARM_MRS_CACHE_DIR if set
SCRIPT="$REPO/tools/query_feature.py"
```

If `ARM_MRS_CACHE_DIR` is set, it points to a shared cache; `REPO` still resolves correctly for the script location.

---

## Commands

### Look up a single feature
```bash
python "$SCRIPT" FEAT_SVE
```
Returns: type, min_version, rendered constraint expressions.

### Check a dependency between two features
```bash
python "$SCRIPT" FEAT_SVE --deps FEAT_FP16
```
Returns: yes / conditional / no answer **first**, then the full constraint tree.
- **yes** — `FEAT_X --> RHS` where `RHS` contains the target (sole LHS)
- **conditional** — target appears in a compound constraint (e.g., `(FEAT_X && OTHER) --> TARGET`)
- **no** — no relationship found in the spec data

### List features introduced at or before a version
```bash
python "$SCRIPT" --version v9Ap2
```
Returns: features grouped by the version they were introduced in, up to and including the requested version.

Known version ordering (oldest → newest):
`v8Ap0 v8Ap1 v8Ap2 v8Ap3 v8Ap4 v8Ap5 v8Ap6 v8Ap7 v8Ap8 v8Ap9 v9Ap0 v9Ap1 v9Ap2 v9Ap3 v9Ap4 v9Ap5 v9Ap6`

### List features matching a name pattern
```bash
python "$SCRIPT" --list SVE
```
Returns: all `FEAT_*` names containing the pattern (case-insensitive).

---

## Important constraints

- **No prose descriptions.** The BSD MRS release omits all descriptive text. `description` is `null` for every feature. Do not synthesize a description — tell the user it is not available in this release.
- **Constraints are structural.** The constraint expressions (`-->`, `<->`, `&&`, `||`) describe formal implications between features, not human-readable explanations of what a feature does.
- **41 features have no version constraint.** If `min_version` is `null`, the feature exists in the spec but was not introduced at a specific tracked version.
- **Version params are also in the data.** `v8Ap0`…`v9Ap6` appear as `Parameters.Boolean` entries alongside `FEAT_*` names. Filter to `FEAT_*` when listing features; include versions only when relevant.

---

## Example interactions

**User:** "Does FEAT_SVE require FEAT_FP16?"
```bash
python "$SCRIPT" FEAT_SVE --deps FEAT_FP16
```
Read the first line (yes/no/conditional) and report it directly. Show the relevant constraint expression. Do not show the full tree unless the user asks.

**User:** "What features were added in ARMv9.2?"
```bash
python "$SCRIPT" --version v9Ap2
```
Report only the `v9Ap2` group from the output, not the full cumulative list (which goes back to v8Ap0).

**User:** "What is FEAT_BTI?"
```bash
python "$SCRIPT" FEAT_BTI
```
Report type, min_version, and constraints. Note that prose description is unavailable. You may state the common meaning of Branch Target Identification **only if you are certain** — otherwise instruct the user to consult the ARM Architecture Reference Manual.

**User:** "List all SVE-related features"
```bash
python "$SCRIPT" --list SVE
```
Present the list. Optionally note which ones are sub-features (e.g., `FEAT_SVE_AES`, `FEAT_SVE2`) vs. the base feature.
