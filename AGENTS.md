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
