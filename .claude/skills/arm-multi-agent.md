---
description: Multi-agent orchestration for AArch64 code generation and verification
globs:
alwaysApply: false
---

# arm-multi-agent -- Multi-Agent Orchestration (H8)

Coordinates four specialised agent roles for AArch64 code generation and verification.
Each agent has constrained tool access and a defined responsibility.

## When to use this skill

Positive triggers:
- Multi-agent AArch64 code generation workflow
- Developer/Critic/Judge/Executor agent coordination
- Task locking for parallel agent work
- Oracle comparison testing (reference vs experimental output)
- RALPH continuous improvement loop

Negative triggers:
- Single-agent queries (use arm-feat, arm-reg, arm-instr, etc.)
- Just running the linter (use arm-linter)
- Just cross-compiling (use arm-cross)

## Agent Roles

developer: Generate A64 code, pass unit tests
critic: Catch syntax errors and logical flaws
judge: Independent spec-based verification
executor: Operate QEMU, GDB, compiler

## RALPH Loop: Developer->Critic->Executor->Judge->Developer(repair)

## CLI: python3 tools/multi_agent.py --list-agents
## CLI: python3 tools/multi_agent.py --agent developer --describe
## CLI: python3 tools/multi_agent.py --system-prompt developer --arch v9Ap4
## CLI: python3 tools/multi_agent.py --lock TASK --agent ROLE
## CLI: python3 tools/multi_agent.py --oracle --reference REF --experimental EXP
## CLI: python3 tools/multi_agent.py --ralph --task TASK --max-iters N
## CLI: python3 tools/multi_agent.py --ralph-simulate --json
