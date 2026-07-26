# Isaac Ops-Roadmap 2026-07-26 — **Safety Review Pass (detailliert)**

**Review-Datum:** 2026-07-26  
**Code:** `sco0rp/main` @ `e76260f` = Render live  
**Lokal live:** `:8766` / WS `:8765` · provider openrouter · browser=true · directives=[]  

Dieser Pass **prüft und korrigiert** die detaillierte Ops-Roadmap gegen Code, Live-Evidenz und AGENTS.md.

---

## Safety-Verdict (Kurz)

| Track | Verdict | Korrektur gegenüber Roh-Roadmap |
|-------|---------|----------------------------------|
| **T0 Sentry** | ✅ sinnvoll, sicher | ISAAC-9 eher **LoggingIntegration ERROR** als capture_exception — Fix = log-level/filter, nicht nur „nicht capture“ |
| **T1 Chat-Hijack** | ✅ kritisch, aber **Hypothese schärfen** | `allow_tools` ist bei CHAT **schon false**; „Und?“ = **NORMAL_CHAT**, nicht SHORT_CLARIFICATION. Hijack = **LLM+Retrieval/History**, kein Tool-Pfad |
| **T2 Browser E2E** | ✅ ok | Nur lokal; Policy authorized-only bleibt |
| **T3 Smoke** | ✅ ok | WS-Port-Split lokal dokumentieren |
| **T4 Dashboard 6.1** | ⚠️ optional | Kein Redesign 2.0 ohne Owner-Feedback (AGENTS) |
| **T5 glinka** | ✅ non-blocking | Auth-abhängig |
| **T6 Secrets** | ✅ Owner | Kein Code ohne Anlass |
| **T7 Master C** | ✅ parallel | Nicht mit Ops vermischen |

**Gesamt:** Roadmap freigabefähig nach Einbau der Korrekturen unten.  
**Empfohlener Start:** T0.1 + T0.2 + T1 (korrigiert) — kein Big-Bang, keine Architektur-Neuerfindung.

---

## Evidenz-Checkliste (was stimmt / was nicht)

### Deploy & Tests

| Claim | Evidenz | OK? |
|-------|---------|-----|
| main = Render e76260f | healthz + check_deploy_sync | ✅ |
| Smoke remote 4/4 | remote_smoke_last.json | ✅ |
| Lokal A/B/C grün (Re-Run) | Session log | ✅ C jetzt klar „4“ |
| Lokal G hijack | „Anmeldedaten… Google-API-Keys“ | ✅ Bug bestätigt |
| directives lokal leer | monitor state | ✅ nicht Key-Direktive-Gate |
| browser lokal an | settings + Playwright processes | ✅ |

### T1 — Code-Wahrheit (wichtigste Korrektur)

| Hypothese alt | Messung | Neue Haltung |
|---------------|---------|--------------|
| Tools bei G erlaubt | `_select_response_strategy`: CHAT → `allow_tools=False` | **Nicht** primärer Fix |
| „Und?“ = SHORT_CLARIFICATION | `classify_interaction_result("Und?")` → **NORMAL_CHAT** | Optional: Marker erweitern **oder** Continuity im Prompt/Retrieval |
| provider_auto_connect aktiv | directives=[] lokal | Nicht die Ursache im Live-Snapshot |
| Retrieval/History/System prompt | Free-Prompt filtert Keys; **local** hat mehr Kontext/History | **Primär:** Kontext-Hygiene + Follow-up-Continuity |

**Sichere Fix-Richtung T1 (architekturkonform):**

1. **Conversation continuity:** Bei kurzen Follow-ups (`und?`, `und dann?`, `weiter?`, `warum?`) Strategy-Note / system: *beziehe dich auf letzten User-Turn; keine neuen Missionen/Keys/Browser*  
2. **Retrieval filter:** Für NORMAL_CHAT mit `word_count ≤ 3` oder Follow-up-Muster: **keine** Provider-Key-/Browser-Provisioning-Direktiven und keine Mission-Noise in `wissen_kontext`  
3. **Optional classify:** `und?` / `und` → SHORT_CLARIFICATION **nur wenn** riskant (kann „Alles gut. Verstanden.“ lokal machen — **Produktentscheidung**: lieber Continuity-LLM als stummes ACK)  
4. **Regression-Test** mit gemocktem Retrieval, das Key-Direktiven enthält → Antwort darf keine Login-Forderung sein  

**Nicht tun:** allow_tools global enger (schon false); Executor umbauen; Memory wholesale redesign.

### T0 — Sentry-Wahrheit

| Issue | lastSeen (Review) | Code-Bezug | Sichere Aktion |
|-------|-------------------|------------|----------------|
| ISAAC-4/7/5 Unclosed | ~12:4x, vor Nachmittag | MCP close fix in tool_runtime | resolve + reopen-if-recurs |
| ISAAC-9 Ollama | ~12:42 | `relay` ProviderErr + **LoggingIntegration event_level=ERROR** | free_cloud: Ollama-Probe skip / log ≤ warning; filter before_send |
| ISAAC-6 anomalous | **noch 21:01** | volume | Alert UI / rate-limit, nicht blind ignore all |
| ISAAC-B Connection header | Test-Zeit | HTTP auf :8765 | resolve; optional WS-only response |
| ISAAC-1/2/3/A/8 | alt/one-off | — | resolve |

**before_send Guardrails (Sicherheit):**  
Keine Secrets; keine Passwörter; optional drop events matching `Ollama nicht erreichbar` wenn `free_cloud` or primary ≠ ollama.

### T2 Browser — Safety

- Nur **Owner-Accounts**, Creds nur store, redact in Evidence  
- Bounty: authorized_only (execution_contract) — **kein** Scope erweitern  
- Free: browser oft aus — Tests primär lokal  

### T4 Dashboard — AGENTS

- v6 ist Owner-Override **done**  
- T4 nur **blockierende Scroll-Bugs** oder explizites Owner-Feedback  
- Kein zweites Full-Redesign in dieser Roadmap ohne neuen Auftrag  

### Untracked / Repo-Hygiene

- `openapi_letta.json` untracked — **nicht** committen ohne Review (groß, evtl. generated)  
- Keine Secrets in Roadmap-Commits  

---

## Korrigierte Track-Reihenfolge (verbindlich)

```text
Sprint O1 (sicher, klein):
  T0.1 Resolve Noise (API/UI)
  T0.2 ISAAC-9 dampen (log/filter/free_cloud)
  T1   Chat-Follow-up Continuity + Test   ← korrigierte Ursache
  Deploy + Smoke A–G lokal/remote

Sprint O2:
  T0.3 ISAAC-6
  T2   Browser E2E lokal (a–c)
  T3   Smoke WS_URL docs, ntfy optional

Sprint O3 (optional):
  T4 nur bei Bugs/Feedback
  T5 glinka
  T6 Owner passwords
```

---

## T0 — Sentry-Hygiene (unverändert sinnvoll, Details geschärft)

### T0.1 Resolve-Liste

| Issue | Aktion |
|-------|--------|
| ISAAC-1,2,3 | resolve intentional |
| ISAAC-A | resolve KeyboardInterrupt |
| ISAAC-8, B | resolve one-off HTTP-on-WS |
| ISAAC-4,5,7 | resolve „fixed session close; monitor“ |

### T0.2 ISAAC-9

| Schritt | Detail | Risiko |
|---------|--------|--------|
| 1 | Health free_cloud: kein Ollama-Probe (ggf. schon) | low |
| 2 | relay: Ollama connection fail → log.warning not error wenn primary nicht ollama / free | low |
| 3 | isaac_sentry before_send drop oder level info | low |
| 4 | Test mock | low |

### T0.3 ISAAC-6

Diagnose first (1h), dann Alert oder rate-limit — **kein** breites Log-Mute.

### T0 DoD

- [ ] Unresolved < 3 echte Items oder nur 6 in Beobachtung  
- [ ] Keine neuen ISAAC-9 auf Free nach 24h  
- [ ] `docs/SENTRY.md` Hygiene-Absatz  

---

## T1 — Chat-Fokus (korrigierte Spezifikation)

### Problem

User: `Was ist 2+2?` → `Und?`  
Lokal: Login/API-Keys statt Fortsetzung.  
Tools: **aus**. Classify: **NORMAL_CHAT**.

### Lösungsschritte (minimal)

| # | Änderung | Datei | Validierung |
|---|----------|-------|-------------|
| 1 | Follow-up detector (`und?`, `und dann`, `wieso`, `warum`, `und nun`) | `low_complexity` oder `isaac_core` helper | Unit |
| 2 | Bei Follow-up: `style_note` Continuity + „keine Keys/Browser/Login unaufgefordert“ | `_select_response_strategy` | Unit |
| 3 | Retrieval-Strip: key/browser provisioning lines aus Kontext bei Follow-up / short chat | `isaac_core` retrieval post-process **oder** memory filter eng | Unit mit fake retrieval |
| 4 | **Nicht** „Und?“ → starres „Alles gut. Verstanden.“ default (verliert Nutzen) | — | Produkt |
| 5 | `test_followup_und_no_credential_fishing` | tests_phase_a | red-green |

### T1 DoD

- [ ] Lokal Sequenz C→G: Antwort thematisch an 2+2 oder ehrliche Klärung, **kein** Credential-Request  
- [ ] Remote unverändert grün  
- [ ] Intent CHAT bleibt; tools false  

### T1 Anti-Scope

- Kein Memory-Redesign  
- Kein Disable Browser global  
- Kein Execution-Contract abschalten  

---

## T2 — Browser E2E (Safety-ok)

Wie zuvor T2.a–g, plus:

- **Stop** bei captcha/2FA → Owner-Push (schon Contract)  
- Keine echten Google-Passwörter in Tests — nur Dummy/owner_login_probe config gitignored  

### T2 DoD

- [ ] Ein evidence-ok Browser goto lokal  
- [ ] Creds nie in URL  

---

## T3 — Smoke / Observability

| ID | Inhalt | Safety |
|----|--------|--------|
| T3.a | GH remote-smoke runs prüfen | nur read |
| T3.b | `ISAAC_WS_URL` optional in remote_smoke für lokal :8765 vs health :8766 | klein |
| T3.c–i | wie Roh-Roadmap | ntfy secrets nicht committen |

---

## T4 — Dashboard 6.1 (eingeschränkt)

Nur:

1. Reproduzierbarer Scroll-Bug  
2. Explizites Owner-Ticket  

Sonst **zurückstellen**. AGENTS: kein UI-Expand.

---

## T5–T7

Unverändert non-blocking / Owner / Master-C.

---

## Risiken nach Review

| Risiko | Mitigation |
|--------|------------|
| T1 classify „Und?“ → stummes ACK | Continuity-Note statt class change default |
| T0 before_send droppt echte Errors | Nur enge Pattern (Ollama unreachable) |
| T2 Bounty Autonomie | authorized_only enforced bleiben |
| Scope-Explosion Dashboard | T4 gate |
| openapi_letta.json | nicht committen |

---

## Dependency (korrigiert)

```text
T0.1 ──┐
T0.2 ──┼──► clean Sentry signal
T1 ────┴──► weniger false „Mission/Login“-Antworten
T1 ────────► T2 (Execution bleibt für echte Browser-Befehle)
T2 ────────► Owner-Vertrauen in Evidence
T3 parallel nach O1
T4 blocked until feedback
```

---

## Repo-Artefakt nach Implementierungs-Freigabe

`docs/ROADMAP_OPS_2026-07-26.md` = dieses Dokument (Safety-Pass inklusive).  
Optional Link aus Master-Roadmap § Ops-Nachtrag.

---

## Erste konkrete Arbeitspakete (nach Execute-Freigabe)

1. **T0.1** Sentry resolve (API)  
2. **T0.2** Ollama log/Sentry filter  
3. **T1** Follow-up continuity + regression test  
4. Smoke lokal C→G + remote full  
5. Commit + redeploy  

---

## Explizit verifiziert: nichts muss „alles auf einmal“

Big-Bang Dashboard ist **done**. Diese Roadmap ist **inkrementell und fail-safe**.

---

*Safety Review complete — Roadmap bereit zur Ausführungsfreigabe.*
