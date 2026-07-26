# Isaac Dashboard v6 — Cognitive Cockpit

**Owner-Override:** Explizites Redesign trotz AGENTS „kein UI-Expand“.

## USP

- **NOW Stream** — Kernel-Pipeline live (classify → … → memory)
- **Rot / Blau / Grün** — Control / Memory / Execution
- **Focus | Cockpit** — Chat-first vs. volle Monitore
- **Causal Timeline** — DecisionTrace pro Task
- **Capability Map** — Tools nach Kategorie
- **Ops** — Remote smoke / anti-sleep Status

## Scroll

Shell `100dvh`, Stage + Chat + Nav: `min-height:0` + `overflow-y:auto`.

## Backend

- `monitor_now.py` — `build_now_snapshot()` fail-open
- `_build_state()` additiv: `now`, `goals`, `missions`, `remote_smoke`

## Dateien

| Pfad | Rolle |
|------|--------|
| `dashboard.html` | Single-file UI (FileResponse) |
| `dashboard.v5.backup.html` | Pre-v6 Backup (lokal, nicht deployed Pflicht) |
| `monitor_now.py` | NOW assembler |

## Nutzung

Lokal: Dashboard-Port (default 8766) oder unified Free `/`.  
Toggle Focus/Cockpit speichert in `localStorage`.
