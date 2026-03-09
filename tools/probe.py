#!/usr/bin/env python3
"""
probe.py — Data structure validation and proposed cache schema preview.

Run this before implementing build_index.py to verify data extraction
assumptions and review the proposed cache JSON format for each entity type.

Usage:
  python tools/probe.py                        # run all three probes
  python tools/probe.py --register SCTLR_EL1  # register probe only
  python tools/probe.py --operation ADC        # instruction probe only
  python tools/probe.py --feat-version v9Ap2  # feature version traversal only
  python tools/probe.py --feat FEAT_SVE        # single feature probe

Reads directly from the MRS source files (no cache required).
"""

import argparse
import json
import os
import sys
import time

# ---------------------------------------------------------------------------
# Repo root resolution
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)

FEATURES_PATH     = os.path.join(REPO_ROOT, "Features.json")
INSTRUCTIONS_PATH = os.path.join(REPO_ROOT, "Instructions.json")
REGISTERS_PATH    = os.path.join(REPO_ROOT, "Registers.json")

# Known architecture version ordering (oldest to newest)
VERSION_ORDER = [
    "v8Ap0", "v8Ap1", "v8Ap2", "v8Ap3", "v8Ap4", "v8Ap5",
    "v8Ap6", "v8Ap7", "v8Ap8", "v8Ap9",
    "v9Ap0", "v9Ap1", "v9Ap2", "v9Ap3", "v9Ap4", "v9Ap5", "v9Ap6",
]

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def load_json(path, label):
    t0 = time.time()
    print(f"  Loading {label}...", end=" ", flush=True)
    with open(path) as f:
        data = json.load(f)
    print(f"done ({time.time() - t0:.1f}s)")
    return data


def separator(title):
    width = 72
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def subsection(title):
    print(f"\n--- {title} ---")


# ---------------------------------------------------------------------------
# Probe 1: Register
# ---------------------------------------------------------------------------

def extract_field(raw_field):
    """
    Normalise a raw Fields.* object into the proposed cache field schema.
    Returns None for unnamed/reserved fields (they are skipped in the cache).
    """
    name = raw_field.get("name")
    ftype = raw_field.get("_type", "")
    rangeset = raw_field.get("rangeset", [])

    bits = [{"start": r["start"], "width": r["width"]} for r in rangeset]

    # Extract value enumeration if present
    values_raw = raw_field.get("values")
    values = []
    if isinstance(values_raw, dict):
        for v in values_raw.get("values", []):
            values.append({
                "value":   v.get("value"),
                "meaning": v.get("meaning"),
            })

    return {
        "name":   name,
        "type":   ftype,
        "bits":   bits,
        "values": values if values else None,
    }


def extract_accessor(raw_acc):
    """Normalise a raw Accessors.* object into the proposed cache accessor schema."""
    atype = raw_acc.get("_type", "")
    enc   = raw_acc.get("encoding")
    acc   = raw_acc.get("access")
    return {
        "type":     atype,
        "name":     raw_acc.get("name"),
        "encoding": enc,
        "access":   acc,
    }


def extract_register(raw_reg):
    """
    Produce the proposed cache schema for a single register entry.
    This is what cache/registers/NAME__STATE.json will contain.
    """
    fieldsets_out = []
    for fset in raw_reg.get("fieldsets", []):
        fields_out = []
        for raw_f in fset.get("values", []):
            f = extract_field(raw_f)
            if f["name"]:  # skip unnamed/reserved
                fields_out.append(f)
        fieldsets_out.append({
            "condition": fset.get("condition"),
            "width":     fset.get("width"),
            "fields":    fields_out,
        })

    accessors_out = [extract_accessor(a) for a in raw_reg.get("accessors", [])]

    return {
        "name":       raw_reg.get("name"),
        "state":      raw_reg.get("state"),
        "condition":  raw_reg.get("condition"),
        "index_variable": raw_reg.get("index_variable"),
        "indexes":    raw_reg.get("indexes"),
        "fieldsets":  fieldsets_out,
        "accessors":  accessors_out,
    }


def probe_register(reg_name):
    separator(f"PROBE 1: Register — {reg_name}")
    print()
    data = load_json(REGISTERS_PATH, "Registers.json")

    matches = [r for r in data if r["name"] == reg_name]
    if not matches:
        # Try parameterised: normalise digits to <n>
        import re
        normalised = re.sub(r"\d+", "<n>", reg_name)
        matches = [r for r in data if r["name"] == normalised]
        if matches:
            print(f"  Exact name not found; resolved '{reg_name}' -> '{normalised}'")
        else:
            print(f"  ERROR: No register named '{reg_name}' found.", file=sys.stderr)
            return

    # Show state breakdown
    subsection("Matches found")
    for m in matches:
        print(f"  state={m['state']}  fieldsets={len(m.get('fieldsets', []))}  "
              f"accessors={len(m.get('accessors', []))}")

    # Default to AArch64; fall back to first match
    target = next((m for m in matches if m["state"] == "AArch64"), matches[0])
    if len(matches) > 1:
        print(f"\n  Defaulting to state=AArch64 (use --state to override)")

    subsection("Proposed cache schema (proposed cache/registers/*.json)")
    cached = extract_register(target)
    print(json.dumps(cached, indent=2))

    # Stats
    subsection("Statistics")
    all_fields = [f for fset in target.get("fieldsets", [])
                    for f in fset.get("values", [])]
    named = [f for f in all_fields if f.get("name")]
    unnamed = len(all_fields) - len(named)
    acc_types = {}
    for a in target.get("accessors", []):
        t = a.get("_type", "unknown")
        acc_types[t] = acc_types.get(t, 0) + 1

    print(f"  Total raw fields : {len(all_fields)}")
    print(f"  Named fields     : {len(named)}  (will be cached)")
    print(f"  Unnamed/reserved : {unnamed}  (will be skipped)")
    print(f"  Accessor types   : {acc_types}")


# ---------------------------------------------------------------------------
# Probe 2: Instruction / Operation
# ---------------------------------------------------------------------------

def extract_encoding(raw_enc):
    """Normalise a raw Instruction encoding node."""
    if not raw_enc:
        return None
    fields = []
    for f in raw_enc.get("values", []):
        fields.append({
            "name":  f.get("name"),
            "start": f.get("range", {}).get("start"),
            "width": f.get("range", {}).get("width"),
            "value": f.get("value"),
        })
    return {
        "width":  raw_enc.get("width"),
        "fields": fields,
    }


def collect_instruction_nodes(node, op_id, result):
    """Walk the instruction tree and collect leaf nodes matching op_id."""
    t = node.get("_type", "")
    node_op_id = node.get("operation_id")
    if node_op_id == op_id and "Set" not in t and "Group" not in t:
        result.append(node)
    for child in node.get("children", []):
        collect_instruction_nodes(child, op_id, result)


def extract_operation(op_id, operations, instruction_tree_root):
    """
    Produce the proposed cache schema for a single operation.
    This is what cache/operations/OPERATION_ID.json will contain.
    """
    op = operations.get(op_id)
    if not op:
        return None

    # Collect all instruction nodes that reference this operation_id
    instr_nodes = []
    collect_instruction_nodes(instruction_tree_root, op_id, instr_nodes)

    variants = []
    for node in instr_nodes:
        variants.append({
            "name":     node.get("name"),
            "encoding": extract_encoding(node.get("encoding")),
            "assembly": node.get("assembly"),
            "condition": node.get("condition"),
        })

    # Truncate long ASL operation text for the probe preview
    operation_text = op.get("operation")
    if operation_text and len(operation_text) > 500:
        operation_text = operation_text[:500] + "\n  ... [truncated — full text in cache]"

    return {
        "operation_id":        op_id,
        "title":               op.get("title"),
        "brief":               op.get("brief"),
        "description":         op.get("description"),
        "decode":              op.get("decode"),   # may be None
        "operation_truncated": operation_text,
        "instruction_variants": variants,
    }


def probe_operation(op_id):
    separator(f"PROBE 2: Instruction / Operation — {op_id}")
    print()
    data = load_json(INSTRUCTIONS_PATH, "Instructions.json")

    operations = data.get("operations", {})
    if op_id not in operations:
        # Try case-insensitive match
        matches = [k for k in operations if k.lower() == op_id.lower()]
        if matches:
            op_id = matches[0]
            print(f"  Case-corrected to: {op_id}")
        else:
            print(f"  ERROR: operation_id '{op_id}' not found.", file=sys.stderr)
            print(f"  Tip: use --list to search for matching operation_ids.")
            return

    subsection("Proposed cache schema (cache/operations/*.json)")
    cached = extract_operation(op_id, operations, data["instructions"][0])
    print(json.dumps(cached, indent=2))

    subsection("Statistics")
    variants = cached.get("instruction_variants", [])
    print(f"  Instruction variants : {len(variants)}")
    for v in variants:
        enc = v.get("encoding")
        nfields = len(enc["fields"]) if enc else 0
        print(f"    {v['name']}  ({nfields} encoding fields)")
    print(f"  decode field present : {cached.get('decode') is not None}")
    print(f"  operation text length: "
          f"{len(operations[op_id].get('operation') or '')} chars")


def probe_operation_list(pattern):
    separator(f"PROBE 2b: Operation list — pattern '{pattern}'")
    print()
    data = load_json(INSTRUCTIONS_PATH, "Instructions.json")
    matches = sorted(k for k in data["operations"] if pattern.lower() in k.lower())
    print(f"  Found {len(matches)} matching operation_ids:\n")
    for m in matches:
        print(f"    {m}")


# ---------------------------------------------------------------------------
# Probe 3: Feature version AST traversal
# ---------------------------------------------------------------------------

def collect_version_implications(node, versions_set, found):
    """
    Recursively walk an AST node looking for BinaryOp nodes of the form:
      FEAT_X --> vNApM   (or vNApM --> FEAT_X, though unusual)
    Populate `found` with {feature: version} pairs.
    """
    if not isinstance(node, dict):
        return

    if node.get("_type") == "AST.BinaryOp" and node.get("op") == "-->":
        left  = node.get("left",  {})
        right = node.get("right", {})

        left_val  = left.get("value")  if left.get("_type")  == "AST.Identifier" else None
        right_val = right.get("value") if right.get("_type") == "AST.Identifier" else None

        # Pattern: FEAT_X --> vNApM
        if (left_val and left_val.startswith("FEAT_")
                and right_val and right_val in versions_set):
            feat, ver = left_val, right_val
            # Keep only the earliest (minimum) version seen for this feature
            if feat not in found or VERSION_ORDER.index(ver) < VERSION_ORDER.index(found[feat]):
                found[feat] = ver

        # Pattern: vNApM --> FEAT_X (unusual but handle it)
        if (right_val and right_val.startswith("FEAT_")
                and left_val and left_val in versions_set):
            feat, ver = right_val, left_val
            if feat not in found or VERSION_ORDER.index(ver) < VERSION_ORDER.index(found[feat]):
                found[feat] = ver

    # Recurse into all child values
    for v in node.values():
        if isinstance(v, dict):
            collect_version_implications(v, versions_set, found)
        elif isinstance(v, list):
            for item in v:
                collect_version_implications(item, versions_set, found)


def probe_feat_version(requested_version):
    separator(f"PROBE 3: Feature version traversal — {requested_version}")
    print()

    if requested_version not in VERSION_ORDER:
        print(f"  ERROR: Unknown version '{requested_version}'.", file=sys.stderr)
        print(f"  Known versions: {VERSION_ORDER}")
        return

    data = load_json(FEATURES_PATH, "Features.json")

    versions_set = set(VERSION_ORDER)
    found = {}  # feat -> minimum version string

    # Walk per-parameter constraints
    for param in data.get("parameters", []):
        for constraint in param.get("constraints") or []:
            collect_version_implications(constraint, versions_set, found)

    # Walk top-level constraints
    for constraint in data.get("constraints") or []:
        collect_version_implications(constraint, versions_set, found)

    subsection("Statistics")
    print(f"  Total parameters            : {len(data['parameters'])}")
    print(f"  Features with version bound : {len(found)}")
    print(f"  Features without version    : {len(data['parameters']) - len(found)}")

    # Filter to requested version ceiling
    req_idx = VERSION_ORDER.index(requested_version)
    in_version = {f: v for f, v in found.items()
                  if VERSION_ORDER.index(v) <= req_idx}

    subsection(f"Features introduced at or before {requested_version} ({len(in_version)} total)")
    # Group by version
    by_version = {}
    for feat, ver in in_version.items():
        by_version.setdefault(ver, []).append(feat)

    for ver in VERSION_ORDER:
        if ver not in by_version:
            continue
        feats = sorted(by_version[ver])
        print(f"\n  {ver} ({len(feats)} features):")
        for f in feats:
            print(f"    {f}")

    subsection("Proposed cache contribution (part of cache/features.json)")
    sample = {feat: ver for feat, ver in list(in_version.items())[:5]}
    print("  Each feature entry will include a 'min_version' field, e.g.:")
    print(json.dumps({"name": "FEAT_SVE",
                      "min_version": found.get("FEAT_SVE", None),
                      "constraints": "... (raw AST) ..."}, indent=2))


# ---------------------------------------------------------------------------
# Probe 4: Single feature
# ---------------------------------------------------------------------------

def probe_feature(feat_name):
    separator(f"PROBE 4: Feature — {feat_name}")
    print()
    data = load_json(FEATURES_PATH, "Features.json")

    match = next((p for p in data["parameters"] if p["name"] == feat_name), None)
    if not match:
        close = [p["name"] for p in data["parameters"]
                 if feat_name.lower() in p["name"].lower()]
        print(f"  ERROR: Feature '{feat_name}' not found.", file=sys.stderr)
        if close:
            print(f"  Similar names: {close[:10]}")
        return

    subsection("Raw MRS entry")
    print(json.dumps(match, indent=2))

    subsection("Proposed cache schema (part of cache/features.json)")
    # Run version traversal to find min_version for this feature
    versions_set = set(VERSION_ORDER)
    found = {}
    for constraint in match.get("constraints") or []:
        collect_version_implications(constraint, versions_set, found)
    for constraint in data.get("constraints") or []:
        collect_version_implications(constraint, versions_set, found)

    cached = {
        "name":        match["name"],
        "type":        match["_type"],
        "min_version": found.get(feat_name),
        "constraints": match.get("constraints"),
    }
    print(json.dumps(cached, indent=2))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Probe MRS data structure and preview proposed cache schemas."
    )
    parser.add_argument("--register",     metavar="NAME",    help="Probe a register (e.g. SCTLR_EL1)")
    parser.add_argument("--operation",    metavar="OP_ID",   help="Probe an operation (e.g. ADC)")
    parser.add_argument("--list",         metavar="PATTERN", help="List operation_ids matching pattern")
    parser.add_argument("--feat-version", metavar="VERSION", help="Run feature version traversal (e.g. v9Ap2)")
    parser.add_argument("--feat",         metavar="NAME",    help="Probe a single feature (e.g. FEAT_SVE)")
    args = parser.parse_args()

    ran_any = False

    if args.register:
        probe_register(args.register)
        ran_any = True

    if args.operation:
        probe_operation(args.operation)
        ran_any = True

    if args.list:
        probe_operation_list(args.list)
        ran_any = True

    if args.feat_version:
        probe_feat_version(args.feat_version)
        ran_any = True

    if args.feat:
        probe_feature(args.feat)
        ran_any = True

    if not ran_any:
        # Default: run all three primary probes
        print("Running all probes. Use --help to run individual probes.\n")
        probe_register("SCTLR_EL1")
        probe_operation("ADC")
        probe_feat_version("v9Ap2")
        probe_feature("FEAT_SVE")

    print()


if __name__ == "__main__":
    main()
