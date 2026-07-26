# Automation Pipeline (Isaac ↔ Render ↔ Cognee ↔ Letta ↔ GitHub)

Bounded multi-system automation. Isaac remains the kernel orchestrator;
companions stay opt-in tools.

## Status command

```text
status:pipeline
status:pipeline sync
pipeline status
automation status
```

`sync` writes an ops snapshot into **Cognee** (requires write enabled).

## Env flags

| Flag | Default | Meaning |
|------|---------|---------|
| `ISAAC_AUTO_PIPELINE` | `0` | Background ops→Cognee automation |
| `ISAAC_AUTO_REDEPLOY` | `0` | Optional auto-redeploy on drift (Stage 2) |
| `ISAAC_GH_AUTO_PR` | `0` | Aggressive auto-PR (Stage 3) |
| `ISAAC_GH_AUTO_MERGE` | `0` | Never merge main by default |
| `ISAAC_GH_REPO_ALLOWLIST` | `sco0rp/IsaacNew` | Comma-separated repos |
| `ISAAC_GH_MAX_PR_PER_DAY` | `3` | Rate limit (Stage 3) |
| `ISAAC_COGNEE_ENABLED` | `0` | Cognee adapter |
| `ISAAC_COGNEE_ALLOW_CLOUD` | `0` | Cloud REST |
| `COGNEE_BASE_URL` / `COGNEE_API_KEY` | | Tenant |
| `ISAAC_EXTERNAL_MEMORY_WRITE` | `0` | Allow remember |
| `ISAAC_LETTA_ENABLED` | `0` | Letta CLI companion |
| `ISAAC_COPILOT_AGENT_ENABLED` | `0` | Copilot / CCA |
| `ISAAC_COPILOT_CLOUD_REPO` | | `owner/repo` for cloud tasks |
| `ISAAC_AGENT_AUTO_SELECT` | `0` | Marker-based companion pick |
| `SENTRY_DSN` / `SENTRY_AUTH_TOKEN` | | Errors + triage API |

## Owner autonomy task

`daily_stack_health` (action `automation_ops`):

- Window ~07–22h, every 12h
- Runs `run_stack_health_cycle(force_write=True)` → status + Cognee snapshot
- Needs admin/owner mode like other autonomy tasks

Enable pipeline write for background:

```bash
export ISAAC_AUTO_PIPELINE=1
```

## Stages

0. Status wiring — **done in code** (`automation_pipeline.py`)
1. Memory/ops sync — Cognee snapshot + autonomy task
2. Sentry/deploy actions (redeploy flag)
3. GitHub auto-PR (policy + CCA)
4. Letta local parity

## Policy (aggressive GH later)

- Owner-equivalent only
- goal_id recommended / required for auto PR
- Branch `auto/…` only, never direct main
- No force-push, no auto-merge unless explicit flag
- Kill-switches above

## Code

| File | Role |
|------|------|
| `automation_pipeline.py` | Status probes + ops→Cognee |
| `owner_autonomy.py` | `daily_stack_health` task |
| `isaac_core.py` | `status:pipeline` intent |
| `docs/AUTOMATION_PIPELINE.md` | This doc |
