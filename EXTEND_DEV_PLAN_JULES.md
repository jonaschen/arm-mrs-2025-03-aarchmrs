# EXTEND_DEV_PLAN_JULES.md - Integration of Additional ARM Specifications

This development plan outlines the process for extending the Arm Architecture Machine Readable Specification (AARCHMRS) project to include additional specifications, such as the Generic Interrupt Controller (GIC), CoreSight, and the Architecture Reference Manual.

## Background

The current AARCHMRS project handles the A-profile Architecture, primarily parsing `Features.json`, `Instructions.json`, and `Registers.json`. The goal is to incorporate other essential hardware specifications to provide a more comprehensive, ground-truth data source for agent skills.

## Phase 1: Data Acquisition and Standardization

**Goal:** Obtain machine-readable formats for the new specifications and align them with the existing data structures.

1. **Source Identification:**
   - **GIC:** Locate the XML or JSON releases corresponding to the GIC specification (e.g., IHI0069).
   - **CoreSight:** Locate the XML or JSON releases corresponding to the CoreSight architecture (e.g., IHI0029).
   - **Architecture Reference Manual (ARM):** Determine the scope of data to extract from the ARM (e.g., DDI0487), such as system register definitions not currently covered or exception models.

2. **Format Conversion (If Necessary):**
   - If the new specifications are provided in XML (which is common for ARM releases prior to AARCHMRS), develop a robust XML-to-JSON converter.
   - The resulting JSON schema should closely resemble or gracefully extend the existing AST/Fields schema used in `Registers.json` and `Features.json`.

3. **Data Organization:**
   - Store the new source data files in the repository root or a designated `data/` directory (e.g., `GIC_Registers.json`, `CoreSight_Features.json`).

## Phase 2: Indexing and Caching Expansion

**Goal:** Extend the `tools/build_index.py` script to parse and cache the new specifications.

1. **Modify `tools/build_index.py`:**
   - Add parsing logic for the new JSON files.
   - Create new cache directories: `cache/gic/` and `cache/coresight/`.
   - Ensure the parser handles domain-specific entities (e.g., interrupt IDs for GIC, debug components for CoreSight).

2. **Update Metadata Indices:**
   - Extend `cache/manifest.json` to include hashes for the new source files.
   - Update `cache/registers_meta.json` (or create a new `cache/meta.json` for global search) to index entities from GIC and CoreSight, tagging them with their respective domains.

## Phase 3: Query Tools and Agent Skills

**Goal:** Provide command-line interfaces and agent skills to interact with the new data.

1. **Develop Query Scripts:**
   - Create `tools/query_gic.py` to handle GIC-specific queries (e.g., interrupt routing, distributor register layouts).
   - Create `tools/query_coresight.py` to handle CoreSight queries (e.g., trace macrocell configurations).
   - Update `tools/query_search.py` to search across all domains (A-profile, GIC, CoreSight).

2. **Create Agent Skills:**
   - Add `.claude/skills/arm-gic.md` to guide the agent in answering GIC-related questions.
   - Add `.claude/skills/arm-coresight.md` for debug and trace queries.
   - Ensure each skill defines clear positive and negative triggers to route user queries correctly (e.g., "How do I configure a SPI?" -> `arm-gic`).

## Phase 4: Evaluation and Integration

**Goal:** Ensure correctness and prevent regressions.

1. **Update `tools/eval_skill.py`:**
   - Add test batteries for `arm-gic` and `arm-coresight`.
   - Verify that the skills return accurate, spec-grounded information without hallucination.

2. **Documentation Updates:**
   - Update `README.md` to list the newly supported specifications.
   - Revise `CLAUDE.md` to include instructions for querying the new domains.
   - Update `ROADMAP.md` to reflect completed milestones.

## Timeline and Dependencies

- **Phase 1** must be completed first, as it provides the raw data.
- **Phase 2** depends on the standardized JSON schema from Phase 1.
- **Phase 3** can begin once the cache structure is finalized in Phase 2.
- **Phase 4** should be ongoing throughout Phase 3 to ensure quality.