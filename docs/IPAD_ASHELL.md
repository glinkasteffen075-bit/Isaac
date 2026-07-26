# Isaac auf iPad (a-Shell) + S8 Termux/NetHunter

Zielbild: **iPad Air M3 = Konsole / Rechen-Workflow**, **S8 = Gerätekörper**, **Render = immer erreichbarer Chat**, **Cognee = gemeinsames Memory**.

## Was realistisch ist

| Auf dem iPad (a-Shell / Safari) | Besser auf S8 | Besser Render / Cloud |
|--------------------------------|---------------|------------------------|
| Safari → Isaac Free Chat | Termux-API (Akku, GPS, …) | 24/7 erreichbarer Endpoint |
| Optional: Kernel **im Vordergrund** | NetHunter / Netzwerk-Tools | LLM-APIs (Groq, OpenRouter, …) |
| Git, Python-Skripte, `gh` (wenn lauffähig) | Längerer Background / wake-lock | Copilot Cloud Agent Tasks |
| Grok **Web/App** als schwerer Agent | Owner-Filesystem am Phone | Sentry |

**Nicht erwarten:** 24/7-Daemon nur in a-Shell, NetHunter auf iOS, großes Offline-LLM auf dem iPad.

---

## Stufe A — Sofort (kein Kernel auf dem iPad)

1. Safari öffnen: https://isaac-free.onrender.com  
2. Chat testen: `Hallo Isaac`, `status:pipeline`  
3. Gleiche Cognee-Keys wie lokal (Memory geteilt)  
4. S8 weiter für Gerätestatus / Owner-Ops  

Fertig: du nutzt die **M3-UI**, Rechenlast der Modelle bleibt bei den **Cloud-APIs**.

---

## Stufe B — Isaac-Kernel in a-Shell (Smoke)

Nur wenn Python 3.10+ und `pip` in a-Shell verfügbar sind.

### 1. Repo

```bash
# Beispiel — Pfade je nach a-Shell anpassen
cd ~
git clone https://github.com/sco0rp/IsaacNew.git isaacnew   # oder dein Remote
cd isaacnew
git checkout main
git pull
```

### 2. Slim-Deps (Free-Profil)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements-free.txt
# falls requirements-free fehlt: aiohttp websockets python-dotenv sentry-sdk …
```

### 3. Env (niemals in Screenshots posten)

```bash
cat > ~/.isaac.env << 'EOF'
ACTIVE_PROVIDER=openrouter
OPENROUTER_API_KEY=
# oder GROQ_API_KEY= / GOOGLE_API_KEY=
ISAAC_DISABLE_VECTOR_MEMORY=1
ISAAC_BIND_HOST=127.0.0.1
MONITOR_HTTP_PORT=8766
MONITOR_PORT=8765
ISAAC_COGNEE_ENABLED=1
ISAAC_COGNEE_ALLOW_CLOUD=1
COGNEE_BASE_URL=
COGNEE_API_KEY=
ISAAC_EXTERNAL_MEMORY_WRITE=1
SENTRY_DSN=
EOF
chmod 600 ~/.isaac.env
set -a; source ~/.isaac.env; set +a
```

### 4. Start

```bash
cd ~/isaacnew
source .venv/bin/activate
set -a; source ~/.isaac.env; set +a
python3 isaac_core.py
```

Safari (auf dem iPad): http://127.0.0.1:8766  

### 5. Smoke

- `Hallo Isaac` → lokale Antwort  
- `status:pipeline` → Render/Cognee/Sentry-Zeilen  
- App wechseln → Prozess kann sterben → **normal unter iOS**

---

## Stufe C — Agenten „wie Grok“

| Weg | Empfehlung |
|-----|------------|
| Schwere Dialoge / Planung | **Grok Web oder App** auf dem iPad |
| Isaac + Tools auf Render | Safari → Render |
| Repo-PRs | GitHub im Browser oder CCA (Cloud Agent), nicht NetHunter |
| Optional CLI in a-Shell | nur wenn `node`/`grok`/`gh` installierbar und stabil |

Isaac-Companion-Flags (`ISAAC_GROK_AGENT_ENABLED=1` …) nur, wenn der Kernel in a-Shell stabil läuft **und** das Binary im PATH ist.

---

## Stufe D — S8 vom iPad aus erreichen

1. **Tailscale** auf iPad + S8 (gleicher Account)  
2. S8: Isaac + optional `s8_remote` Hub (`install_termux.sh`)  
3. iPad Safari: `http://<tailscale-ip-s8>:8766` (Dashboard) oder Hub-Port  
4. Shortcuts analog `s8_remote/IPHONE_SHORTCUTS.md`  

So bleibt die **Rechen-/Chat-Arbeit am iPad**, die **Geräte-Hände am S8**.

---

## Rollen-Cheat-Sheet

```text
iPad M3     → denken, schreiben, Agents (UI + Cloud-APIs)
S8 NH       → fühlen, tun, NetHunter, Termux-API
Render      → immer erreichbarer Isaac-Chat
Cognee      → gemeinsames Gedächtnis
Sentry      → Fehler
```

---

## Troubleshooting a-Shell

| Problem | Idee |
|---------|------|
| `pip` / wheels fail | slim `requirements-free`, kein onnx/chroma |
| Port belegt | andere `MONITOR_HTTP_PORT` |
| Kein Netz zu Render | a-Shell Netzwerk-Rechte / VPN |
| Prozess weg nach App-Wechsel | akzeptieren oder Render als Always-on nutzen |
| Zu wenig Speicher | kein Vector-Memory, ein Provider |

---

## Siehe auch

- [ISAAC_REMOTE.md](ISAAC_REMOTE.md) — `cloud:` / `both:` Fleet  
- [FREE_HOSTING.md](FREE_HOSTING.md) — Render Free  
- [OWNER_COMMANDS.md](OWNER_COMMANDS.md) — Termux/S8  
- [AUTOMATION_PIPELINE.md](AUTOMATION_PIPELINE.md) — `status:pipeline`  
- [COPILOT_AGENT.md](COPILOT_AGENT.md) / [GROK_AGENT.md](GROK_AGENT.md) — Companions  
