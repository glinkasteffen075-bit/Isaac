# MCP Capability Matrix (Isaac)

**Track C2** · Stand: 2026-07-27 · Kernel v5.3  
**Scope:** Contract surface only — **kein** MCP-Subagent, kein Framework-Import.

---

## Transport

| Weg | Modul | Status |
|-----|-------|--------|
| JSON-RPC 2.0 (stdio) | `mcp_server.run_stdio_transport`, `mcp_jsonrpc` | ✅ |
| HTTP REST (optional) | `mcp_server` Flask blueprint | ✅ |
| Client | `mcp_client` | ✅ |

**Methoden:** `initialize`, `ping`, `tools/list`, `tools/call`, `resources/list`, `resources/read`, `prompts/list`, `prompts/get`.

---

## Tools (6)

| Name | Privilege | Constitution-gated | Beschreibung |
|------|-----------|--------------------|--------------|
| `isaac.task_status` | `read_memory` | — | Task-Status / recent tasks |
| `isaac.audit_recent` | `read_audit` | — | Audit-Tail |
| `isaac.query_memory` | `read_memory` | — | `build_retrieval_context` |
| `isaac.start_task` | `chat_response` | ✅ | Task anlegen (ohne Auto-Execute) |
| `isaac.search_web` | `internet_search` | ✅ | Websuche |
| `isaac.run_browser_action` | `browser_navigate` | ✅ | Explizite Browser-Aktion |

**Autorität:** Registry = Struktur · Privilege/Strategy = Permission · Executor = Execution.  
MCP-Tools umgehen **nicht** Classification/Strategy im Kernel-Hauptpfad.

---

## Resources (7)

| URI | Privilege | Inhalt |
|-----|-----------|--------|
| `resource://constitution` | `read_memory` | Verfassung export/summary/version |
| `resource://self-model` | `read_memory` | Self-Model States |
| `resource://memory/blocks` | `read_memory` | Strukturierte Memory-Blöcke |
| `resource://procedures` | `read_memory` | Procedure store (+ degraded) |
| `resource://audit/tail` | `read_audit` | Letzte Audit-Einträge |
| `isaac://tasks/recent` | `read_memory` | Recent tasks |
| `isaac://tools/registry` | `read_memory` | Lokale Tool-Registry |

**Error-Shape (unknown):**  
`{"ok": false, "error": "Unknown MCP resource: …"}`  
JSON-RPC: `error.message` mit gleichem Text.

---

## Prompts (2)

| Name | Zweck |
|------|-------|
| `tool.refine_input` | Nächster Arbeitsinput aus Tool-Ergebnis |
| `research.next_step` | Nächster Recherche-Schritt zu `topic` |

**Error-Shape (unknown):**  
`{"ok": false, "error": "Unknown MCP prompt: …"}`

---

## Privilege & Governance

| Schicht | Ort |
|---------|-----|
| Tool → Privilege | `MCP_TOOL_PRIVILEGES` in `mcp_registry.py` |
| Resource → Privilege | `MCP_RESOURCE_PRIVILEGES` |
| Constitution outside-effect | `MCP_CONSTITUTION_GATED_TOOLS` |
| Gate | `privilege.get_gate().authorize` |

Admin-Modus (`ISAAC_PRIVILEGE_MODE=admin`) erweitert Rechte; Audit bleibt an.  
Siehe auch [ADMIN_CAPABILITY_MATRIX.md](ADMIN_CAPABILITY_MATRIX.md).

---

## Contract-Tests

```bash
ISAAC_DISABLE_VECTOR_MEMORY=1 python3 -m evals.mcp_eval
```

Erwartung: alle Cases `ok`, Exit 0. Suite prüft u. a.:

- Inventar tools/resources/prompts exakt  
- Jede Resource lesbar mit `ok` + `uri`  
- Unknown tool/resource/prompt rejected  
- Privilege-Maps vollständig und sensitiv korrekt  
- Constitution-gated Set stabil  
- stdio `initialize` → `serverInfo`

---

## Explizit **nicht** im Scope (Do-NOT)

- MCP-Subagent-Orchestrierung / Multi-Agent-Handoffs  
- Wholesale MCP-SDK als Kernel-Ersatz  
- Opportunistische Tool-Freigabe aus normalem Chat  
- Neue Architektur-Layer parallel zu ROT/BLAU/GRÜN  

---

## Ownership

| Modul | Rolle |
|-------|-------|
| `mcp_registry.py` | Struktur, Handler, Privilege-Maps |
| `mcp_jsonrpc.py` | JSON-RPC Dispatcher |
| `mcp_server.py` | stdio + HTTP surface |
| `mcp_client.py` | Outbound client |
| `evals/mcp_eval.py` | Contract suite (C2) |
