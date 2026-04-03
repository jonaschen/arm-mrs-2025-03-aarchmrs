#!/usr/bin/env python3
"""
multi_agent.py — Multi-Agent Orchestration for AArch64 (Milestone H8).

Coordinates four agent roles (Developer, Critic, Judge, Executor) working on
independent architectural subsystems.  Provides a task-lock protocol, Oracle
comparison testing framework, and RALPH (Repeating Amplified Prompting Loop)
continuous improvement orchestrator.

Design note: the original H8 plan called for Docker containers per agent.
This implementation uses an in-process Python orchestration model that can
drive actual Claude Code agent instances (via subprocess or MCP) while
remaining testable without any external runtime.

Usage:
    multi_agent.py --list-agents                            # list all agent roles
    multi_agent.py --agent developer --describe             # print agent profile
    multi_agent.py --lock TASK_ID --agent developer         # acquire task lock
    multi_agent.py --unlock TASK_ID --agent developer       # release task lock
    multi_agent.py --lock-status [TASK_ID]                  # show lock status
    multi_agent.py --oracle --reference REF --experimental EXP [--json]
    multi_agent.py --ralph --task TASK_FILE [--max-iters N] [--json]
    multi_agent.py --system-prompt developer                # print system prompt

Exit codes:
    0  success
    1  invalid arguments or operation failure
    2  lock conflict (another agent holds the lock)
"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import textwrap
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_TOOLS_DIR = Path(__file__).parent.resolve()
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

SCHEMA_VERSION = '1.0'

# Default lock directory — inside cache/ or a temp dir
_LOCK_DIR_ENV = os.environ.get('ARM_AGENT_LOCK_DIR')
_LOCK_DIR = Path(_LOCK_DIR_ENV) if _LOCK_DIR_ENV else (_TOOLS_DIR.parent / 'cache' / 'agent_locks')

# ---------------------------------------------------------------------------
# Agent Role Definitions
# ---------------------------------------------------------------------------

AGENT_ROLES = {
    'developer': {
        'name': 'Developer Agent',
        'role': 'developer',
        'primary_responsibility': 'Generate A64 code, pass unit tests',
        'domain_focus': 'Instruction selection, algorithm design',
        'tools_allowed': [
            'query_instruction.py', 'query_feature.py', 'query_register.py',
            'query_allowlist.py', 'isa_optimize.py', 'setup_cross_compile.py',
        ],
        'tools_denied': ['query_gdb.py'],  # Executor-only
        'constraints': [
            'All memory accesses must be 16-byte aligned for LDP/STP instructions.',
            'Never use XZR as the base register in load/store with writeback.',
            'Always verify feature availability via arm-feat before using any ISA extension.',
            'Insert PAC/AUT instructions in all function prologues and epilogues for Armv9 targets.',
            'BTI landing pads are mandatory for all indirect branch targets.',
        ],
        'reasoning_protocol': [
            'Query arm-feat to confirm the instruction/extension exists for the target architecture version.',
            'Analyse register dependencies and potential pipeline stalls.',
            'Generate assembly code with proper alignment and security annotations.',
            'Propose a GDB verification plan (H3) before finalizing.',
        ],
    },
    'critic': {
        'name': 'Critic Agent',
        'role': 'critic',
        'primary_responsibility': 'Catch syntax errors and logical flaws',
        'domain_focus': 'Architectural compliance, best practices',
        'tools_allowed': [
            'isa_linter.py', 'query_allowlist.py', 'query_feature.py',
            'query_register.py', 'query_instruction.py',
        ],
        'tools_denied': ['setup_cross_compile.py', 'gen_qemu_launch.py'],
        'constraints': [
            'Review every instruction against the allowlist for the target arch version.',
            'Flag any use of ISA extensions not confirmed by arm-feat.',
            'Verify all branch targets have correct BTI landing pads.',
            'Check SP alignment at every function boundary.',
            'Verify PAC signing/authentication pairing in every function.',
        ],
        'reasoning_protocol': [
            'Run the full 50-rule linter (H7) on the submitted assembly.',
            'Cross-check each instruction against the allowlist (H1).',
            'Verify register constraints (XZR writeback, STXR overlap, etc.).',
            'Report all violations with severity and auto-repair suggestions.',
        ],
    },
    'judge': {
        'name': 'Judge Agent',
        'role': 'judge',
        'primary_responsibility': 'Independent spec-based verification',
        'domain_focus': 'Zero-hallucination gatekeeper',
        'tools_allowed': [
            'query_feature.py', 'query_register.py', 'query_instruction.py',
            'query_allowlist.py', 'query_search.py',
        ],
        'tools_denied': ['isa_optimize.py', 'setup_cross_compile.py'],
        'constraints': [
            'Every fact must be verified against the MRS data — never assume.',
            'If a feature or instruction cannot be confirmed, reject the code.',
            'Cross-reference all register accesses with accessor encoding data.',
            'Reject any code that uses instructions outside the allowlist.',
            'All verdicts must cite the specific MRS data source.',
        ],
        'reasoning_protocol': [
            'For each instruction used, query arm-instr to verify existence and encoding.',
            'For each register accessed, query arm-reg to verify field layout and access mode.',
            'For each feature assumed, query arm-feat to verify availability at target version.',
            'Produce a verdict: PASS (spec-confirmed) or FAIL (violation found) with evidence.',
        ],
    },
    'executor': {
        'name': 'Executor Agent',
        'role': 'executor',
        'primary_responsibility': 'Operate QEMU, GDB, compiler',
        'domain_focus': 'Runtime verification, performance analysis',
        'tools_allowed': [
            'query_gdb.py', 'gen_qemu_launch.py', 'setup_cross_compile.py',
            'query_allowlist.py',
        ],
        'tools_denied': ['isa_optimize.py'],
        'constraints': [
            'Always cross-compile with the correct -march flag for the target arch.',
            'Use QEMU user-mode for functional tests, system-mode for full-system.',
            'On SIGILL, immediately invoke the H1 allowlist for repair guidance.',
            'On SIGSEGV, check SP alignment and memory access patterns.',
            'All GDB assertions must use the register-state comparison framework.',
        ],
        'reasoning_protocol': [
            'Cross-compile the generated code using setup_cross_compile.py.',
            'Run the binary in QEMU and classify the exit condition.',
            'On failure, invoke GDB to isolate the failing instruction.',
            'Report runtime results: pass/fail/sigill/sigsegv/timeout with details.',
        ],
    },
}

AGENT_NAMES = sorted(AGENT_ROLES.keys())

# ---------------------------------------------------------------------------
# System Prompt Generation
# ---------------------------------------------------------------------------

def generate_system_prompt(agent_role: str, arch: str = 'v9Ap4') -> str:
    """Generate the full system prompt for an agent role.

    Returns the XML-structured system prompt as defined in the H8 design.
    """
    if agent_role not in AGENT_ROLES:
        raise ValueError(f'Unknown agent role: {agent_role}. '
                         f'Available: {", ".join(AGENT_NAMES)}')

    agent = AGENT_ROLES[agent_role]

    constraints_text = '\n'.join(f'- {c}' for c in agent['constraints'])
    reasoning_text = '\n'.join(f'{i+1}. {s}'
                               for i, s in enumerate(agent['reasoning_protocol']))
    tools_text = ', '.join(agent['tools_allowed'])

    prompt = textwrap.dedent(f"""\
    <identity>
    You are the {agent['name']}, an expert AArch64 Systems Architect operating in
    a Linux environment. You have direct access to AARCHMRS machine-readable
    specifications via the arm-feat, arm-reg, arm-instr, arm-gic, arm-coresight,
    and arm-pmu skills.

    Primary responsibility: {agent['primary_responsibility']}
    Domain focus: {agent['domain_focus']}
    Target architecture: {arch}
    Allowed tools: {tools_text}
    </identity>

    <constraints>
    {constraints_text}
    </constraints>

    <reasoning_protocol>
    Think step-by-step:
    {reasoning_text}
    </reasoning_protocol>

    <graceful_exit>
    If the requested feature is absent from arm-feat for the target version,
    state this clearly and offer an alternative implementation.
    </graceful_exit>
    """)
    return prompt


def get_agent_profile(agent_role: str) -> dict:
    """Return the full profile dict for an agent role."""
    if agent_role not in AGENT_ROLES:
        raise ValueError(f'Unknown agent role: {agent_role}. '
                         f'Available: {", ".join(AGENT_NAMES)}')
    return dict(AGENT_ROLES[agent_role])


def list_agents() -> list:
    """Return a list of (role, name, responsibility) tuples."""
    return [(role, info['name'], info['primary_responsibility'])
            for role, info in sorted(AGENT_ROLES.items())]


# ---------------------------------------------------------------------------
# Task Lock Protocol (H8-2)
# ---------------------------------------------------------------------------

class LockConflictError(Exception):
    """Raised when a task lock is held by another agent."""
    pass


class TaskLock:
    """File-based task lock for multi-agent coordination.

    Each task is identified by a task_id string.  A lock file is created
    at ``<lock_dir>/<task_id>.lock`` containing the agent role and timestamp.
    Locks are advisory and idempotent — acquiring a lock you already hold
    is a no-op.
    """

    def __init__(self, lock_dir: str = None):
        self.lock_dir = Path(lock_dir) if lock_dir else _LOCK_DIR

    def _lock_path(self, task_id: str) -> Path:
        """Sanitise task_id and return the lock file path."""
        safe = re.sub(r'[^a-zA-Z0-9_\-.]', '_', task_id)
        return self.lock_dir / f'{safe}.lock'

    def acquire(self, task_id: str, agent_role: str) -> dict:
        """Acquire a lock for task_id on behalf of agent_role.

        Returns the lock info dict on success.
        Raises LockConflictError if another agent holds the lock.
        """
        if agent_role not in AGENT_ROLES:
            raise ValueError(f'Unknown agent role: {agent_role}')

        self.lock_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self._lock_path(task_id)

        # Check for existing lock
        if lock_path.exists():
            existing = json.loads(lock_path.read_text())
            if existing.get('agent') == agent_role:
                return existing  # idempotent re-acquire
            raise LockConflictError(
                f'Task "{task_id}" is locked by {existing.get("agent")} '
                f'(since {existing.get("timestamp", "unknown")})')

        lock_info = {
            'task_id': task_id,
            'agent': agent_role,
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'pid': os.getpid(),
        }
        lock_path.write_text(json.dumps(lock_info, indent=2) + '\n')
        return lock_info

    def release(self, task_id: str, agent_role: str) -> bool:
        """Release a lock.  Returns True if released, False if not held."""
        lock_path = self._lock_path(task_id)
        if not lock_path.exists():
            return False
        existing = json.loads(lock_path.read_text())
        if existing.get('agent') != agent_role:
            raise LockConflictError(
                f'Task "{task_id}" is locked by {existing.get("agent")}, '
                f'not {agent_role}')
        lock_path.unlink()
        return True

    def status(self, task_id: str = None) -> list:
        """Return lock status.  If task_id given, return just that lock.
        Otherwise return all active locks."""
        if not self.lock_dir.exists():
            return []

        if task_id:
            lock_path = self._lock_path(task_id)
            if not lock_path.exists():
                return []
            return [json.loads(lock_path.read_text())]

        locks = []
        for f in sorted(self.lock_dir.glob('*.lock')):
            try:
                locks.append(json.loads(f.read_text()))
            except (json.JSONDecodeError, OSError):
                pass
        return locks

    def clear_all(self) -> int:
        """Remove all locks.  Returns count of locks removed."""
        if not self.lock_dir.exists():
            return 0
        count = 0
        for f in self.lock_dir.glob('*.lock'):
            f.unlink()
            count += 1
        return count


# ---------------------------------------------------------------------------
# Oracle Comparison Testing Framework (H8-3)
# ---------------------------------------------------------------------------

class OracleResult:
    """Result of comparing a reference (GCC) output against experimental output."""

    def __init__(self, match: bool, reference_hash: str, experimental_hash: str,
                 delta: list = None, reference_path: str = None,
                 experimental_path: str = None):
        self.match = match
        self.reference_hash = reference_hash
        self.experimental_hash = experimental_hash
        self.delta = delta or []
        self.reference_path = reference_path
        self.experimental_path = experimental_path

    def to_dict(self) -> dict:
        return {
            'schema_version': SCHEMA_VERSION,
            'match': self.match,
            'reference_hash': self.reference_hash,
            'experimental_hash': self.experimental_hash,
            'reference_path': self.reference_path,
            'experimental_path': self.experimental_path,
            'delta_count': len(self.delta),
            'delta': self.delta[:50],  # cap for readability
        }


def _file_hash(path: str) -> str:
    """Return SHA-256 hex digest of file contents."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def _diff_lines(ref_lines: list, exp_lines: list) -> list:
    """Simple line-by-line diff returning list of delta dicts."""
    deltas = []
    max_len = max(len(ref_lines), len(exp_lines))
    for i in range(max_len):
        ref_line = ref_lines[i] if i < len(ref_lines) else None
        exp_line = exp_lines[i] if i < len(exp_lines) else None
        if ref_line != exp_line:
            deltas.append({
                'line': i + 1,
                'reference': ref_line,
                'experimental': exp_line,
            })
    return deltas


def oracle_compare(reference_path: str, experimental_path: str) -> OracleResult:
    """Compare reference (GCC-compiled) output against experimental output.

    Both paths should point to text files containing program output (stdout
    captured from running the binary).  The comparison is:
    1. SHA-256 hash match (fast path)
    2. Line-by-line diff (detailed delta on mismatch)
    """
    ref_hash = _file_hash(reference_path)
    exp_hash = _file_hash(experimental_path)

    if ref_hash == exp_hash:
        return OracleResult(
            match=True,
            reference_hash=ref_hash,
            experimental_hash=exp_hash,
            reference_path=reference_path,
            experimental_path=experimental_path,
        )

    # Detailed diff
    with open(reference_path, 'r', errors='replace') as f:
        ref_lines = f.read().splitlines()
    with open(experimental_path, 'r', errors='replace') as f:
        exp_lines = f.read().splitlines()

    delta = _diff_lines(ref_lines, exp_lines)

    return OracleResult(
        match=False,
        reference_hash=ref_hash,
        experimental_hash=exp_hash,
        delta=delta,
        reference_path=reference_path,
        experimental_path=experimental_path,
    )


def delta_debug(reference_lines: list, experimental_lines: list,
                max_depth: int = 10) -> list:
    """Narrow failures to the minimal differing region using delta debugging.

    Returns a list of (start_line, end_line) tuples identifying the minimal
    failure-inducing regions.  Uses a simplified Zeller-style binary
    partitioning: split the experimental output in halves, check which half
    causes the mismatch, recurse.
    """
    full_delta = _diff_lines(reference_lines, experimental_lines)
    if not full_delta:
        return []

    # Group contiguous delta lines into regions
    regions = []
    current_start = None
    current_end = None
    for d in full_delta:
        line = d['line']
        if current_start is None:
            current_start = line
            current_end = line
        elif line == current_end + 1:
            current_end = line
        else:
            regions.append((current_start, current_end))
            current_start = line
            current_end = line
    if current_start is not None:
        regions.append((current_start, current_end))

    return regions


# ---------------------------------------------------------------------------
# RALPH — Repeating Amplified Prompting Loop (H8-4)
# ---------------------------------------------------------------------------

# RALPH step types
RALPH_STEPS = ('generate', 'lint', 'compile', 'execute', 'verify', 'repair')

class RALPHState:
    """State of a single RALPH iteration."""

    def __init__(self, iteration: int, step: str, status: str,
                 agent: str = None, detail: str = None):
        self.iteration = iteration
        self.step = step
        self.status = status  # 'pass', 'fail', 'skip'
        self.agent = agent
        self.detail = detail

    def to_dict(self) -> dict:
        return {
            'iteration': self.iteration,
            'step': self.step,
            'status': self.status,
            'agent': self.agent,
            'detail': self.detail,
        }


class RALPHResult:
    """Final result of a RALPH loop execution."""

    def __init__(self, converged: bool, iterations: int, max_iterations: int,
                 final_status: str, history: list = None, task_id: str = None):
        self.converged = converged
        self.iterations = iterations
        self.max_iterations = max_iterations
        self.final_status = final_status
        self.history = history or []
        self.task_id = task_id

    def to_dict(self) -> dict:
        return {
            'schema_version': SCHEMA_VERSION,
            'converged': self.converged,
            'iterations': self.iterations,
            'max_iterations': self.max_iterations,
            'final_status': self.final_status,
            'task_id': self.task_id,
            'step_count': len(self.history),
            'history': [s.to_dict() for s in self.history],
        }


class RALPHOrchestrator:
    """RALPH continuous improvement loop orchestrator.

    The loop follows this sequence per iteration:
        Developer → generate code
        Critic → lint and review
        Executor → compile and run
        Judge → verify against spec
        Developer → repair (if any step failed)

    The loop terminates when:
        - All steps pass (converged = True)
        - max_iterations is reached (converged = False)
    """

    def __init__(self, task_id: str = None, max_iterations: int = 10,
                 lock_dir: str = None):
        self.task_id = task_id or 'ralph_default'
        self.max_iterations = max_iterations
        self.lock = TaskLock(lock_dir)
        self.history: list = []

    def _record(self, iteration: int, step: str, status: str,
                agent: str = None, detail: str = None) -> RALPHState:
        state = RALPHState(iteration, step, status, agent, detail)
        self.history.append(state)
        return state

    def plan_iteration(self, iteration: int) -> list:
        """Return the planned steps for a single RALPH iteration.

        Each step is a dict with keys: step, agent, action.
        """
        return [
            {'step': 'generate',  'agent': 'developer', 'action': 'Generate AArch64 code for the task'},
            {'step': 'lint',      'agent': 'critic',    'action': 'Run 50-rule linter (H7) on generated code'},
            {'step': 'compile',   'agent': 'executor',  'action': 'Cross-compile for target architecture (H5)'},
            {'step': 'execute',   'agent': 'executor',  'action': 'Run in QEMU and classify exit condition (H4)'},
            {'step': 'verify',    'agent': 'judge',     'action': 'Verify spec compliance of all instructions used'},
            {'step': 'repair',    'agent': 'developer', 'action': 'Fix violations found by critic/judge/executor'},
        ]

    def run_dry(self, task_description: str = None) -> RALPHResult:
        """Execute a dry-run of the RALPH loop (no actual agent invocation).

        Useful for testing the orchestration logic.  Returns a RALPHResult
        showing the planned execution without side effects.
        """
        self.history = []

        for iteration in range(1, self.max_iterations + 1):
            steps = self.plan_iteration(iteration)
            for step_info in steps:
                self._record(
                    iteration=iteration,
                    step=step_info['step'],
                    status='planned',
                    agent=step_info['agent'],
                    detail=step_info['action'],
                )

        return RALPHResult(
            converged=False,
            iterations=self.max_iterations,
            max_iterations=self.max_iterations,
            final_status='dry_run',
            history=self.history,
            task_id=self.task_id,
        )

    def simulate(self, pass_at_iteration: int = 3) -> RALPHResult:
        """Simulate a RALPH loop where convergence occurs at a given iteration.

        For testing: iterations before pass_at_iteration have a 'fail' at the
        lint or verify step, causing a repair step.  At pass_at_iteration, all
        steps pass and the loop terminates.
        """
        self.history = []

        for iteration in range(1, self.max_iterations + 1):
            # Generate
            self._record(iteration, 'generate', 'pass', 'developer',
                         'Generated AArch64 code')

            # Lint
            if iteration < pass_at_iteration:
                self._record(iteration, 'lint', 'fail', 'critic',
                             'L01: Missing PACIASP in function prologue')
                self._record(iteration, 'repair', 'pass', 'developer',
                             'Inserted PACIASP/AUTIASP pair')
                continue  # restart iteration

            self._record(iteration, 'lint', 'pass', 'critic',
                         'All 50 lint rules passed')

            # Compile
            self._record(iteration, 'compile', 'pass', 'executor',
                         'Cross-compiled with -march=armv9-a')

            # Execute
            self._record(iteration, 'execute', 'pass', 'executor',
                         'QEMU exit code 0 (pass)')

            # Verify
            self._record(iteration, 'verify', 'pass', 'judge',
                         'All instructions confirmed in MRS allowlist')

            # Converged!
            return RALPHResult(
                converged=True,
                iterations=iteration,
                max_iterations=self.max_iterations,
                final_status='converged',
                history=self.history,
                task_id=self.task_id,
            )

        return RALPHResult(
            converged=False,
            iterations=self.max_iterations,
            max_iterations=self.max_iterations,
            final_status='max_iterations_reached',
            history=self.history,
            task_id=self.task_id,
        )


# ---------------------------------------------------------------------------
# CLI — Text/JSON formatting
# ---------------------------------------------------------------------------

def _fmt_agents_text() -> str:
    """Format agent listing as text table."""
    lines = ['Agent Roles:', '']
    lines.append(f'  {"Role":<12} {"Name":<20} {"Responsibility"}')
    lines.append(f'  {"-"*12} {"-"*20} {"-"*40}')
    for role, name, resp in list_agents():
        lines.append(f'  {role:<12} {name:<20} {resp}')
    lines.append(f'\n  ({len(AGENT_ROLES)} agent roles defined)')
    return '\n'.join(lines)


def _fmt_agent_describe(role: str) -> str:
    """Format a single agent profile as text."""
    profile = get_agent_profile(role)
    lines = [f'Agent Profile: {profile["name"]}', '']
    lines.append(f'  Role:           {profile["role"]}')
    lines.append(f'  Responsibility: {profile["primary_responsibility"]}')
    lines.append(f'  Domain Focus:   {profile["domain_focus"]}')
    lines.append('')
    lines.append('  Allowed Tools:')
    for t in profile['tools_allowed']:
        lines.append(f'    - {t}')
    lines.append('')
    lines.append('  Denied Tools:')
    for t in profile['tools_denied']:
        lines.append(f'    - {t}')
    lines.append('')
    lines.append('  Constraints:')
    for c in profile['constraints']:
        lines.append(f'    - {c}')
    lines.append('')
    lines.append('  Reasoning Protocol:')
    for i, s in enumerate(profile['reasoning_protocol'], 1):
        lines.append(f'    {i}. {s}')
    return '\n'.join(lines)


def _fmt_locks_text(locks: list) -> str:
    """Format lock status as text."""
    if not locks:
        return 'No active locks.'
    lines = ['Active Locks:', '']
    lines.append(f'  {"Task ID":<30} {"Agent":<12} {"Timestamp":<24} {"PID"}')
    lines.append(f'  {"-"*30} {"-"*12} {"-"*24} {"-"*8}')
    for lock in locks:
        lines.append(
            f'  {lock.get("task_id","?"):<30} '
            f'{lock.get("agent","?"):<12} '
            f'{lock.get("timestamp","?"):<24} '
            f'{lock.get("pid","?")}'
        )
    lines.append(f'\n  ({len(locks)} active lock(s))')
    return '\n'.join(lines)


def _fmt_oracle_text(result: OracleResult) -> str:
    """Format oracle comparison result as text."""
    lines = ['Oracle Comparison Result:', '']
    lines.append(f'  Match:            {"YES" if result.match else "NO"}')
    lines.append(f'  Reference hash:   {result.reference_hash[:16]}...')
    lines.append(f'  Experimental hash:{result.experimental_hash[:16]}...')
    if not result.match:
        lines.append(f'  Delta lines:      {len(result.delta)}')
        for d in result.delta[:10]:
            lines.append(f'    Line {d["line"]}:')
            if d['reference'] is not None:
                lines.append(f'      ref: {d["reference"][:80]}')
            if d['experimental'] is not None:
                lines.append(f'      exp: {d["experimental"][:80]}')
        if len(result.delta) > 10:
            lines.append(f'    ... and {len(result.delta) - 10} more')
    return '\n'.join(lines)


def _fmt_ralph_text(result: RALPHResult) -> str:
    """Format RALPH result as text."""
    lines = ['RALPH Result:', '']
    lines.append(f'  Task ID:        {result.task_id}')
    lines.append(f'  Converged:      {result.converged}')
    lines.append(f'  Iterations:     {result.iterations}/{result.max_iterations}')
    lines.append(f'  Final status:   {result.final_status}')
    lines.append(f'  Steps recorded: {len(result.history)}')
    lines.append('')
    lines.append('  History:')
    for s in result.history:
        flag = '✓' if s.status == 'pass' else ('✗' if s.status == 'fail' else '○')
        lines.append(f'    [{flag}] iter={s.iteration} {s.step:<10} '
                     f'agent={s.agent:<12} {s.detail or ""}')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Multi-Agent Orchestration for AArch64 (Milestone H8).',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Agent commands
    parser.add_argument('--list-agents', action='store_true',
                        help='List all agent roles')
    parser.add_argument('--agent', metavar='ROLE',
                        help='Agent role (developer, critic, judge, executor)')
    parser.add_argument('--describe', action='store_true',
                        help='Print agent profile (requires --agent)')
    parser.add_argument('--system-prompt', metavar='ROLE',
                        help='Print system prompt for agent role')
    parser.add_argument('--arch', default='v9Ap4',
                        help='Target architecture version (default: v9Ap4)')

    # Lock commands
    parser.add_argument('--lock', metavar='TASK_ID',
                        help='Acquire task lock (requires --agent)')
    parser.add_argument('--unlock', metavar='TASK_ID',
                        help='Release task lock (requires --agent)')
    parser.add_argument('--lock-status', nargs='?', const='__ALL__',
                        metavar='TASK_ID',
                        help='Show lock status (optional TASK_ID filter)')
    parser.add_argument('--clear-locks', action='store_true',
                        help='Clear all locks (emergency reset)')

    # Oracle commands
    parser.add_argument('--oracle', action='store_true',
                        help='Run oracle comparison')
    parser.add_argument('--reference', metavar='FILE',
                        help='Reference output file (for --oracle)')
    parser.add_argument('--experimental', metavar='FILE',
                        help='Experimental output file (for --oracle)')

    # RALPH commands
    parser.add_argument('--ralph', action='store_true',
                        help='Run RALPH loop (dry-run or simulate)')
    parser.add_argument('--ralph-simulate', action='store_true',
                        help='Simulate RALPH with convergence at iteration 3')
    parser.add_argument('--task', metavar='TASK_ID',
                        help='Task ID for RALPH')
    parser.add_argument('--max-iters', type=int, default=10,
                        help='Max RALPH iterations (default: 10)')

    # Output format
    parser.add_argument('--json', action='store_true',
                        help='Output as JSON')
    parser.add_argument('--output', choices=['text', 'json'], default='text',
                        help='Output format (default: text)')

    args = parser.parse_args()
    use_json = args.json or args.output == 'json'

    # --list-agents
    if args.list_agents:
        if use_json:
            data = [{'role': r, 'name': n, 'responsibility': resp}
                    for r, n, resp in list_agents()]
            print(json.dumps(data, indent=2))
        else:
            print(_fmt_agents_text())
        return 0

    # --describe (requires --agent)
    if args.describe:
        if not args.agent:
            print('Error: --describe requires --agent ROLE', file=sys.stderr)
            return 1
        if args.agent not in AGENT_ROLES:
            print(f'Error: unknown agent "{args.agent}". '
                  f'Available: {", ".join(AGENT_NAMES)}', file=sys.stderr)
            return 1
        if use_json:
            print(json.dumps(get_agent_profile(args.agent), indent=2))
        else:
            print(_fmt_agent_describe(args.agent))
        return 0

    # --system-prompt ROLE
    if args.system_prompt:
        if args.system_prompt not in AGENT_ROLES:
            print(f'Error: unknown agent "{args.system_prompt}". '
                  f'Available: {", ".join(AGENT_NAMES)}', file=sys.stderr)
            return 1
        print(generate_system_prompt(args.system_prompt, args.arch))
        return 0

    # --lock TASK_ID (requires --agent)
    if args.lock:
        if not args.agent:
            print('Error: --lock requires --agent ROLE', file=sys.stderr)
            return 1
        if args.agent not in AGENT_ROLES:
            print(f'Error: unknown agent "{args.agent}"', file=sys.stderr)
            return 1
        tl = TaskLock()
        try:
            info = tl.acquire(args.lock, args.agent)
            if use_json:
                print(json.dumps(info, indent=2))
            else:
                print(f'Lock acquired: task="{args.lock}" agent={args.agent}')
            return 0
        except LockConflictError as e:
            print(f'Lock conflict: {e}', file=sys.stderr)
            return 2

    # --unlock TASK_ID (requires --agent)
    if args.unlock:
        if not args.agent:
            print('Error: --unlock requires --agent ROLE', file=sys.stderr)
            return 1
        tl = TaskLock()
        try:
            released = tl.release(args.unlock, args.agent)
            if released:
                print(f'Lock released: task="{args.unlock}"')
            else:
                print(f'No lock found for task="{args.unlock}"')
            return 0
        except LockConflictError as e:
            print(f'Lock conflict: {e}', file=sys.stderr)
            return 2

    # --lock-status [TASK_ID]
    if args.lock_status is not None:
        tl = TaskLock()
        task_id = None if args.lock_status == '__ALL__' else args.lock_status
        locks = tl.status(task_id)
        if use_json:
            print(json.dumps(locks, indent=2))
        else:
            print(_fmt_locks_text(locks))
        return 0

    # --clear-locks
    if args.clear_locks:
        tl = TaskLock()
        count = tl.clear_all()
        print(f'Cleared {count} lock(s).')
        return 0

    # --oracle
    if args.oracle:
        if not args.reference or not args.experimental:
            print('Error: --oracle requires --reference and --experimental',
                  file=sys.stderr)
            return 1
        if not os.path.isfile(args.reference):
            print(f'Error: reference file not found: {args.reference}',
                  file=sys.stderr)
            return 1
        if not os.path.isfile(args.experimental):
            print(f'Error: experimental file not found: {args.experimental}',
                  file=sys.stderr)
            return 1
        result = oracle_compare(args.reference, args.experimental)
        if use_json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(_fmt_oracle_text(result))
        return 0 if result.match else 1

    # --ralph (dry run)
    if args.ralph:
        task_id = args.task or 'ralph_default'
        orch = RALPHOrchestrator(task_id, args.max_iters)
        result = orch.run_dry()
        if use_json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(_fmt_ralph_text(result))
        return 0

    # --ralph-simulate
    if args.ralph_simulate:
        task_id = args.task or 'ralph_sim'
        orch = RALPHOrchestrator(task_id, args.max_iters)
        result = orch.simulate(pass_at_iteration=3)
        if use_json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(_fmt_ralph_text(result))
        return 0 if result.converged else 1

    parser.print_help()
    return 1


if __name__ == '__main__':
    sys.exit(main())
