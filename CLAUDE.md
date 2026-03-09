# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

This is the **Arm A-profile Architecture Machine Readable Specification (AARCHMRS)**, a data distribution repository containing the ARM architecture (v9Ap6-A, Build 445, March 2025) in machine-readable JSON format. It is not a software project — there is no build system, test suite, or executable code.

## Core Data Files

| File | Size | Content |
|------|------|---------|
| `Features.json` | ~1 MB | Architecture features, versions, and constraint expressions |
| `Instructions.json` | ~38 MB | Complete A64 ISA (encodings, assembly syntax, operations) |
| `Registers.json` | ~75 MB | AArch32/AArch64/Memory-mapped system registers and fields |

All JSON files include a `_meta` property with version/build/timestamp metadata and conform to JSON Schema draft-04.

## Schema Organization (`schema/`)

138 JSON Schema files define the data model:

- **Core:** `Meta.json`, `Description.json`, `Encoding.json`, `Fieldset.json`, `Register.json`
- **Instructions** (`schema/Instruction/`): `Instruction.json`, `Assembly.json`, `Operation.json`, `Encodeset/`, `Rules/`
- **Registers** (`schema/Accessors/`): `SystemAccessor.json`, `MemoryMapped.json`, `ExternalDebug.json`, `Permission/`
- **AST** (`schema/AST/`): Constraint expression nodes — `BinaryOp`, `UnaryOp`, `If`, `ForLoop`, `Function`, `Identifier`, `Slice`, etc.
- **Supporting:** `Parameters/`, `Values/`, `Types/`, `Traits/`, `Enums/`, `References/`

## Key Architectural Concepts

**Features model:** Defines architecture feature constraints using AST expressions. Parameters represent `FEAT_*` identifiers and version strings (e.g., `v9Ap6`). Constraints use implication (`-->`), equivalence (`<->`), and logical/comparison operators.

**Registers model:** Each register has a state (`AArch64`, `AArch32`, `ext`), conditional fieldsets (bit field layouts), typed fields, accessors (how to read/write), and optional existence conditions.

**Instructions model:** The top-level `Instructions` wrapper contains `assembly_rules` (token patterns for assembly text), `operations` (semantic behavior in ASL), and `instructions` (encoding groups). Each instruction links to an operation and has assemble/disassemble blocks with ASL pseudocode.

**AST nodes:** Constraint and operation expressions are stored as `{"_type": "AST.*", ...}` objects throughout the data. See `schema/AST/` for node types.

## Documentation

- `docs/index.html` — Main documentation index
- `docs/userguide/` — Practical guides for features, registers, and ISA data models
- `docs/schema_specification.html` — Schema overview
- Individual `*_schema.html` files in `docs/` — Rendered per-type documentation
- `schema/Instruction/index.md`, `schema/AST/index.md` — Markdown guides per subsystem

## Versioning

- Architecture: v9Ap6-A
- Schema: 2.5.5
- Build: 445 (Fri Mar 21 17:42:54 2025)
- License: BSD 3-clause (see `docs/notice.html`)
