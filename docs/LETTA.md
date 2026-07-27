# Letta — External Memory + Companion (bounded)

**Rolle:** Optionaler BLAU/Companion-Adapter unter `external_memory/`.  
**Nicht:** zweiter Kernel, Orchestrator oder Ersatz für `memory.py`.

---

## Flags

| Env | Default | Bedeutung |
|-----|---------|-----------|
| `ISAAC_LETTA_ENABLED` | `0` | Adapter an |
| `ISAAC_LETTA_ALLOW_CLOUD` | `0` | Cloud REST erlauben |
| `LETTA_API_KEY` | — | Cloud API key (`sk-let-…`) |
| `LETTA_BASE_URL` | `https://api.letta.com` | API base |
| `LETTA_AGENT_ID` | — | Optional fester Agent |
| `LETTA_AGENT_NAME` | `isaac` | Auto-Create/Resolve Name |
| `LETTA_MODEL` | `openai/gpt-4o-mini` | Agent-Modell (Create) |
| `LETTA_EMBEDDING` | `openai/text-embedding-3-small` | Embeddings |
| `LETTA_BIN` | `letta` | CLI Companion |
| `ISAAC_EXTERNAL_MEMORY_WRITE` | `0` | Archival-Write freigeben |

**Niemals** Keys committen. Nur `.env` / Render Secrets / `data/cli_auth_backup/`.

---

## Was wofür

| Pfad | Verhalten |
|------|-----------|
| Retrieval (`search`) | Lokale `.letta/*` Dateien + Cloud archival passages + core-memory blocks |
| Write (`remember`) | Cloud archival-memory, nur wenn Write-Flag + Score-Gate im Bridge |
| `letta: …` | Cloud `messages` wenn Credits ok, sonst CLI `@letta-ai/letta-code` |

Fail-soft: fehlende Credits/Packages → Fehlerstring, Kernel bleibt runnable.

---

## Status prüfen

```bash
python3 - <<'PY'
from external_memory import get_external_memory_bridge, reset_external_memory_bridge
reset_external_memory_bridge()
b = get_external_memory_bridge()
print(b.letta.status())
print('hits', b.letta.search('Isaac owner', limit=3))
PY
```

Agent-ID Cache: `data/letta_state.json` (lokal, kein Secret).

---

## Credits

Cloud **Messages** (`letta:`) brauchen Letta-Platform-Credits.  
**Memory search/write** (archival + core) funktionieren auch mit schmalem Kontingent — bei `402`/Rate-Limit greift fail-soft.

Top-up: https://platform.letta.com/settings/organization/usage

---

## Architektur-Grenze

- Classification → Retrieval → Strategy → Task bleibt Isaac-Pipeline  
- Letta liefert nur **Kontext-Snippets** / expliziten Companion  
- Keine MCP-Subagent-Expansion, kein Auto-Tool-Spam aus Chat  

Siehe auch: [OPEN_SOURCE_PATTERNS.md](OPEN_SOURCE_PATTERNS.md), [ADMIN_CAPABILITY_MATRIX.md](ADMIN_CAPABILITY_MATRIX.md).
