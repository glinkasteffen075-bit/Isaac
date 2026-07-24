# Sentry Setup (Isaac)

Org: **evo20** (Evo2.0) · Region: **de.sentry.io**

## Projects

| Project | Platform | Use |
|---------|----------|-----|
| [isaac](https://evo20.sentry.io/projects/isaac/) | **Python** | Kernel (`isaac_core`, `relay`, Render free) |
| [isaac-web](https://evo20.sentry.io/projects/isaac-web/) | **Next.js** | `web/` monorepo (`@repo/observability`) |

## Environment

### Python kernel (`.env` / Render)

```bash
SENTRY_DSN=…                    # Project isaac DSN
SENTRY_ENVIRONMENT=development  # or production
SENTRY_TRACES_SAMPLE_RATE=…     # optional; default 1.0 dev / 0.1 production
SENTRY_INCLUDE_PROMPTS=1
SENTRY_RELEASE=isaac@5.3
```

Code entry: `isaac_sentry.init_sentry()` from `isaac_core.main`.

### Next.js (`web/apps/*/.env.local`)

```bash
NEXT_PUBLIC_SENTRY_DSN=…        # Project isaac-web DSN
SENTRY_ORG=evo20
SENTRY_PROJECT=isaac-web
SENTRY_TRACES_SAMPLE_RATE=0.1   # production default in code as well
```

## Sample rates

| Environment | Default traces rate |
|-------------|---------------------|
| development | **1.0** (full visibility) |
| production / free-cloud | **0.1** |

Override anytime with `SENTRY_TRACES_SAMPLE_RATE`.

## Alerts (configured)

**Issue alerts** (email to issue owners / active members):

- *Isaac: new errors or 10+ events/hour*
- *Isaac Web: new errors or 10+ events/hour*

**Metric alerts** (email team):

- *Isaac: error spike (>20 per hour)*
- *Isaac Web: error spike (>20 per hour)*

UI: https://evo20.sentry.io/alerts/rules/

## Verify

```bash
# Python smoke (needs SENTRY_DSN)
python3 scripts/verify_sentry_ai.py
# → Issues: "Isaac Sentry AI smoke" ; Traces: gen_ai.chat

# Render chat
python3 scripts/render_chat_smoke.py
```

## Security

- Never commit DSN or auth tokens.
- `.env` / `.env.local` are gitignored.
- Rotate tokens that were pasted into chat.
