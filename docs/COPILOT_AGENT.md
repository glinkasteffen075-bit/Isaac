# GitHub Copilot Companion (bounded)

GitHub Copilot in Isaac ist ein **opt-in Companion** — kein Kernel-Ersatz.

Pipeline bleibt: `classify → retrieve → strategy → task → execute`.

## Was angebunden ist

| Pfad | Wie | Voraussetzung |
|------|-----|----------------|
| **CLI** | `copilot -p "…" --output-format json` | `copilot` on PATH, Auth (nicht classic `ghp_`) |
| **SDK** | `github-copilot-sdk` (`CopilotClient`) | `ISAAC_COPILOT_AGENT_USE_SDK=1` + Runtime |
| **Cloud Agent Tasks** | `POST /agents/repos/{owner}/{repo}/tasks` | CCA im Repo/Plan aktiv |
| **Tool Bridge** | `bridge_copilot_agent` | Registry + Flag |
| **Auto-Select** | `agent_selection` → `copilot` | `ISAAC_AGENT_AUTO_SELECT=1` + Markers |

## Auth (wichtig)

Copilot CLI/SDK **lehnen Classic PATs ab** (`ghp_…`).

| Token | Prefix | CLI/SDK | REST (Issues/GitHub Bridge) |
|-------|--------|---------|-----------------------------|
| Classic PAT | `ghp_` | ❌ | ✅ |
| Fine-grained PAT (Copilot Requests) | `github_pat_` | ✅ | ✅ |
| OAuth (`gh auth login` / `copilot /login`) | `gho_` | ✅ | ✅ |
| GitHub App user token | `ghu_` | ✅ | ✅ |

Env-Priorität für Companion:

1. `COPILOT_GITHUB_TOKEN`
2. nicht-classic `GH_TOKEN` / `GITHUB_TOKEN`
3. `~/.copilot/config.json` → `copilotTokens`
4. `~/.config/gh/hosts.yml` → `oauth_token`

Beim CLI-Start werden **classic `ghp_` aus `GH_TOKEN`/`GITHUB_TOKEN` entfernt**, damit sie die Auth nicht vergiften.

```bash
# Empfohlen
export COPILOT_GITHUB_TOKEN='gho_…'   # oder github_pat_… mit Copilot Requests
# oder interaktiv:
copilot   # dann /login
# bzw.
unset GH_TOKEN GITHUB_TOKEN
gh auth login
```

## Isaac-Integration (default OFF)

| Env | Default | Bedeutung |
|-----|---------|-----------|
| `ISAAC_COPILOT_AGENT_ENABLED` | `0` | Companion freischalten |
| `COPILOT_BIN` / `ISAAC_COPILOT_AGENT_BIN` | `copilot` | Binary |
| `ISAAC_COPILOT_AGENT_MODEL` | *(CLI default)* | z. B. `gpt-5`, `auto` |
| `ISAAC_COPILOT_AGENT_CWD` | Isaac `BASE_DIR` | Arbeitsverzeichnis |
| `ISAAC_COPILOT_AGENT_TIMEOUT` | `300` | Sekunden |
| `ISAAC_COPILOT_AGENT_ALWAYS_APPROVE` | `0` | `--allow-all` / Yolo |
| `ISAAC_COPILOT_AGENT_AUTO_RESUME` | `1` | Nächster `copilot:` resumed Session |
| `ISAAC_COPILOT_AGENT_USE_SDK` | `0` | Python-SDK statt CLI |
| `ISAAC_COPILOT_AGENT_ENABLE_MEMORY` | `0` | `--enable-memory` |
| `ISAAC_COPILOT_AGENT_ALLOW_TOOLS` | | `--allow-tool=` (komma) |
| `ISAAC_COPILOT_AGENT_DENY_TOOLS` | | `--deny-tool=` (komma) |
| `ISAAC_COPILOT_CLOUD_REPO` | *(git origin)* | `owner/repo` für Cloud Tasks |
| `ISAAC_COPILOT_CLOUD_BASE_REF` | `main` | Base branch |
| `ISAAC_COPILOT_CLOUD_CREATE_PR` | `0` | PR bei Cloud Task |
| `COPILOT_GITHUB_TOKEN` | | Auth für CLI/SDK |

Auto-Select (gemeinsam mit Grok/OI/Letta):

| Env | Default |
|-----|---------|
| `ISAAC_AGENT_AUTO_SELECT` | `0` |
| `ISAAC_AGENT_TIMEOUT` | `180` |

## Explizite Prefixe

```text
copilot: AUFGABE
gh-copilot: AUFGABE
github-copilot: AUFGABE
copilot-agent: AUFGABE

copilot: cli: erkläre relay.py
copilot: sdk: was macht memory.py?
copilot: cloud: Fix the login button on the homepage
copilot: tasks
copilot: status
copilot: new: frische Session
copilot: resume <uuid>: weiter
copilot: clear session
```

## Architekturgrenze

- **Kein** Ersatz von Classification/Strategy/Executor
- **Kein** opportunistischer Start bei „Hallo“ / normalem Chat
- Constitution + Privilege-Gate wie bei `grok:` / `oi:`
- Default **ohne** `--allow-all` (Headless braucht trotzdem Tool-Policy → `--allow-all-tools` soft default)
- Cloud Agent (CCA) braucht aktivierten Plan/Repo — Free-Limited meldet oft `CCA not enabled`

## Install

```bash
# CLI
npm install -g @github/copilot
# oder via gh:
gh copilot -- --version

# Optional SDK
.venv/bin/pip install github-copilot-sdk
.venv/bin/python -m copilot download-runtime
```

## Mapping (Dateien)

| Datei | Rolle |
|-------|--------|
| `external_memory/copilot_agent_adapter.py` | CLI / SDK / Cloud Tasks |
| `external_memory/config.py` | Env-Flags |
| `external_memory/bridge.py` | Adapter am Bridge |
| `agent_selection.py` | Auto-Select `copilot` |
| `tool_bridge.py` | `bridge_copilot_agent` |
| `isaac_core.py` | Intent `COPILOT_AGENT` + Handler |
| `secrets_bootstrap.py` | `COPILOT_GITHUB_TOKEN` → SecretsStore |

## Sicherheit

- Opt-in + prefix-only (bzw. Auto-Select nur mit Master-Flag + Code-Markern)
- `--allow-all` nur in trusted local Env
- Keys nie committen (`data/cli_auth_backup/`, `.env` gitignored)
- Classic PAT darf GitHub REST (Issues/PRs) nutzen, **nicht** Copilot-Inference
