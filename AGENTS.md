# Repository Guidelines

## Project Structure & Module Organization
Core runtime lives in the repository root. The main entrypoint is `isaac_core.py`; orchestration and execution are split across `executor.py`, `relay.py`, `memory.py`, `logic.py`, `browser.py`, and `monitor_server.py`. Dashboard assets are flat files such as `dashboard.html` and related monitor APIs. Persistent runtime data is stored under `data/`, logs under `logs/`, and generated workspace artifacts under `workspace/`. Regression coverage is currently concentrated in `tests_phase_a_stabilization.py`.

## Build, Test, and Development Commands
- `python3 -m py_compile *.py` checks syntax for the main runtime modules.
- `cd /root/Isaac && /root/Isaac/.venv/bin/python sanity_check.py` validates imports and environment wiring.
- `cd /root/Isaac && /root/Isaac/.venv/bin/python tests_phase_a_stabilization.py` runs the current regression suite.
- `cd /root/Isaac && /root/Isaac/.venv/bin/python isaac_core.py` starts the kernel directly.
- `cd /root/Isaac && bash run_isaac.sh` starts the repository’s standard runtime path.

## Coding Style & Naming Conventions
Use Python 3 with 4-space indentation and standard library-first implementations when practical. Keep module names snake_case and classes PascalCase. Preserve the repository’s German-facing user messages and comments unless a file already uses English for a specific API surface. Prefer small, local patches over broad rewrites; Isaac’s architecture is phase-driven and sensitive to scope drift.

## Testing Guidelines
Use `unittest`-style tests in repository-root test files. Add focused regression tests for every routing, privilege, browser, or provider policy change. Name tests after the bug or guarantee they protect, for example `test_bug_10_kernel_parses_structured_browser_flow`. Before publishing, run both `sanity_check.py` and `tests_phase_a_stabilization.py`.

## Commit & Pull Request Guidelines
Follow the existing commit style: short imperative subjects tied to a concrete Isaac phase or capability, for example `Complete Isaac phase-1 tool policy cleanup`. Keep PRs narrowly scoped, describe the architectural intent, list exact validation commands, and call out any runtime or environment prerequisites such as Playwright or provider keys.

## Security & Configuration Tips
Runtime behavior is controlled through `config.py`, `.env`, and persisted runtime settings in `data/runtime_settings.json`. Do not silently widen privileges or provider access. If you add browser automation, external tools, or filesystem reach, surface the toggle in the dashboard and keep owner-controlled gates intact.

# Isaac System Rules (OpenCode)

Isaac is a controlled cognitive-kernel project under active architectural consolidation.

## Primary Priorities

1. Functional correctness
2. Runtime stability
3. Clear architectural boundaries
4. Minimal safe changes
5. Regression prevention

## Current Phase Discipline

The current priority is core function and stability.

Do NOT start or expand:
- Human Layer
- instincts
- relationship systems
- curiosity
- autonomy
- personality features
- dashboard/UI work
- cloud/deployment work
- MCP/subagent architecture
- broad speculative redesign

If these files exist, leave them alone unless they directly block runtime stability.

## Architectural Intent

Isaac should remain structured around:
- classification
- retrieval
- strategy
- task creation
- execution
- evaluation
- memory update

The executor must execute, not reinterpret.

## Hard Rules

- Do not introduce large refactors unless explicitly requested.
- Do not invent new architecture layers.
- Do not replace existing systems wholesale.
- Do not broaden scope from one subsystem into many.
- Do not silently “improve” unrelated files.
- Always prefer the smallest safe change.
- Preserve currently working behavior unless a change is necessary to fix a real defect.

## Routing Rules

Routing authority must become clearer and less ambiguous.

Be aware that the repo may still contain:
- low_complexity classification
- detect_intent / PATTERNS / regex intent logic

When working on routing:
- classification should be treated as the stronger authority where safe
- explicit command-style patterns may still remain if clearly necessary
- remove ambiguity, not functionality

## Retrieval Rules

Avoid duplicate context construction.

Be aware that the repo may contain:
- structured retrieval paths
- legacy memory.build_context(...) paths

Do not broadly redesign memory unless explicitly requested.
Prefer consolidation over reinvention.

## Strategy Rules

Executor-side behavior should respect explicit strategy/task contract.

If strategy and legacy flags coexist:
- explicit strategy should be treated as authoritative
- reduce ambiguity
- do not silently create conflicting permission behavior

## Executor Rules

Executor must NOT:
- classify user intent
- act as a second router
- infer tool usage from vague context
- become a planner

Executor MAY:
- execute already allowed tasks/tools
- enforce safety boundaries
- remain conservative when uncertain

## Tooling Rules

Registry = structure
Strategy = permission
Executor = execution

Do not confuse these roles.

Do not introduce hidden tool autonomy.

## Testing Rules

For any non-trivial change:
- update or add stabilization tests
- verify lightweight greeting behavior
- verify acknowledgment short-circuit
- verify normal chat path
- verify tool boundary behavior
- verify no accidental tool overreach
- verify compile/import sanity

## Output Discipline

When making changes:
1. identify exact files/functions
2. explain exact defect
3. make minimal safe change
4. validate
5. check regressions

## Repo-Specific Guidance

Focus first on files like:
- isaac_core.py
- executor.py
- low_complexity.py
- memory.py
- tests_phase_a_stabilization.py
- tool_registry.py
- tool_runtime.py

Avoid drifting into unrelated modules unless required for a blocking fix.

## Final Rule

Isaac is not in a “feature expansion” phase.
It is in a “consolidate core behavior” phase.

Favor stability, clarity, and maintainability over novelty.
