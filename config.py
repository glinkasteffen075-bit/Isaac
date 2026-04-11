from __future__ import annotations

import json
import os
from pathlib import Path
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "data"
LOG_DIR    = BASE_DIR / "logs"
WORKSPACE  = BASE_DIR / "workspace"
DB_PATH    = DATA_DIR / "isaac.db"
AUDIT_PATH = DATA_DIR / "audit.jsonl"
RUNTIME_SETTINGS_PATH = DATA_DIR / "runtime_settings.json"

for d in [DATA_DIR, LOG_DIR, WORKSPACE]:
    d.mkdir(parents=True, exist_ok=True)

class Level:
    STEFFEN = 100
    ISAAC   = 70
    TASK    = 40
    GUEST   = 10

@dataclass
class ProviderConfig:
    name:          str
    api_key:       str
    base_url:      str
    default_model: str
    rpm:           int
    tpm:           int
    timeout:       int  = 60
    enabled:       bool = True

    @property
    def available(self) -> bool:
        return self.enabled and (bool(self.api_key) or self.name == "ollama")


def _build_providers() -> dict[str, ProviderConfig]:
    return {
        "ollama": ProviderConfig(
            name="ollama",
            api_key="",
            base_url=os.getenv("OLLAMA_HOST", "http://localhost:11434") + "/api/chat",
            default_model=os.getenv("OLLAMA_MODEL", "phi3:latest"),
            rpm=999, tpm=999_999,
            timeout=int(os.getenv("OLLAMA_TIMEOUT", "180")),
        ),
        "groq": ProviderConfig(
            name="groq",
            api_key=os.getenv("GROQ_API_KEY", ""),
            base_url="https://api.groq.com/openai/v1/chat/completions",
            default_model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            rpm=30, tpm=6_000,
        ),
        "openrouter": ProviderConfig(
            name="openrouter",
            api_key=os.getenv("OPENROUTER_API_KEY", ""),
            base_url="https://openrouter.ai/api/v1/chat/completions",
            default_model=os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.2-3b-instruct:free"),
            rpm=20, tpm=50_000,
        ),
        "huggingface": ProviderConfig(
            name="huggingface",
            api_key=os.getenv("HF_API_KEY", ""),
            base_url="https://api-inference.huggingface.co/models",
            default_model=os.getenv("HF_MODEL", "mistralai/Mistral-7B-Instruct-v0.3"),
            rpm=10, tpm=20_000,
        ),
        "together": ProviderConfig(
            name="together",
            api_key=os.getenv("TOGETHER_API_KEY", ""),
            base_url="https://api.together.xyz/v1/chat/completions",
            default_model=os.getenv("TOGETHER_MODEL", "meta-llama/Llama-3-8b-chat-hf"),
            rpm=60, tpm=100_000,
        ),
        "perplexity": ProviderConfig(
            name="perplexity",
            api_key=os.getenv("PERPLEXITY_API_KEY", ""),
            base_url="https://api.perplexity.ai/chat/completions",
            default_model=os.getenv("PERPLEXITY_MODEL", "llama-3.1-sonar-small-128k-online"),
            rpm=20, tpm=50_000,
        ),
        "mistral": ProviderConfig(
            name="mistral",
            api_key=os.getenv("MISTRAL_API_KEY", ""),
            base_url="https://api.mistral.ai/v1/chat/completions",
            default_model=os.getenv("MISTRAL_MODEL", "open-mistral-7b"),
            rpm=20, tpm=50_000,
        ),
        "gemini": ProviderConfig(
            name="gemini",
            api_key=os.getenv("GOOGLE_API_KEY", ""),
            base_url="https://generativelanguage.googleapis.com/v1beta/models",
            default_model=os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
            rpm=15, tpm=32_000,
        ),
        "openai": ProviderConfig(
            name="openai",
            api_key=os.getenv("OPENAI_API_KEY", ""),
            base_url="https://api.openai.com/v1/chat/completions",
            default_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            rpm=20, tpm=40_000,
        ),
        "anthropic": ProviderConfig(
            name="anthropic",
            api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            base_url="https://api.anthropic.com/v1/messages",
            default_model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
            rpm=50, tpm=100_000,
        ),
        "cohere": ProviderConfig(
            name="cohere",
            api_key=os.getenv("COHERE_API_KEY", ""),
            base_url="https://api.cohere.ai/v2/chat",
            default_model=os.getenv("COHERE_MODEL", "command-r"),
            rpm=20, tpm=100_000,
        ),
    }

@dataclass
class LogicConfig:
    min_quality_score:     float = 5.5
    max_followup_rounds:   int   = 3
    max_task_iterations:   int   = 8
    min_word_count:        int   = 80
    min_topic_coverage:    float = 0.6
    weight_length:         float = 0.20
    weight_coverage:       float = 0.35
    weight_specificity:    float = 0.25
    weight_coherence:      float = 0.20
    instance_switch_score: float = 7.2
    default_followup_mode: str   = "targeted"
    causal_neg_threshold:  float = 0.70
    qualia_penalty:        float = 2.0

@dataclass
class BrowserConfig:
    max_instances:           int  = 12
    page_timeout:            int  = 30
    headless:                bool = True
    auto_restart:            bool = True
    max_errors_per_instance: int  = 5
    slowmo:                  int  = 0

@dataclass
class MonitorConfig:
    host:               str   = "localhost"
    port:               int   = int(os.getenv("MONITOR_PORT", "8765"))
    http_port:          int   = int(os.getenv("DASHBOARD_PORT", "8766"))
    push_interval:      float = 0.5
    max_connections:    int   = 10
    task_history_limit: int   = 500
    log_history_limit:  int   = 1000

@dataclass
class MemoryConfig:
    max_working_memory:        int   = 50
    max_facts:                 int   = 10_000
    fact_similarity_threshold: float = 0.85

@dataclass
class RelayConfig:
    primary_provider:  str   = os.getenv("ACTIVE_PROVIDER", "ollama")
    min_interval:      float = float(os.getenv("MIN_REQUEST_INTERVAL", "2.0"))
    max_retries:       int   = int(os.getenv("MAX_RETRIES", "3"))
    cache_ttl:         int   = 30
    max_context_chars: int   = int(os.getenv("MAX_CONTEXT_CHARS", "3000"))
    strip_user_pii:    bool  = True

@dataclass
class IdeenConfig:
    scan_interval:    int   = 420
    max_queue:        int   = 20
    min_notify_score: float = 6.5
    interesse_topics: list  = None

    def __post_init__(self):
        if self.interesse_topics is None:
            self.interesse_topics = [
                "KI-Sprachprotokolle zwischen Modellen",
                "ARM-GPU Beschleunigung llama.cpp",
                "autonome Agenten Architektur",
                "Python async optimierung",
                "Rust WASM performance",
            ]

@dataclass
class IsaacConfig:
    providers: dict[str, ProviderConfig] = field(default_factory=_build_providers)
    logic:     LogicConfig               = field(default_factory=LogicConfig)
    browser:   BrowserConfig             = field(default_factory=BrowserConfig)
    monitor:   MonitorConfig             = field(default_factory=MonitorConfig)
    memory:    MemoryConfig              = field(default_factory=MemoryConfig)
    relay:     RelayConfig               = field(default_factory=RelayConfig)
    ideen:     IdeenConfig               = field(default_factory=IdeenConfig)
    filesystem_full_access: bool         = True
    browser_automation: bool             = True
    browser_external_sites: bool         = True
    free_only_providers: bool            = True
    owner_name: str = os.getenv("ISAAC_OWNER", "Steffen")

    def __post_init__(self):
        self._load_runtime_settings()

    @property
    def available_providers(self) -> list[str]:
        return [n for n, p in self.providers.items() if p.available and self.is_provider_allowed(n)]

    def get_provider(self, name: str) -> Optional[ProviderConfig]:
        return self.providers.get(name)

    @property
    def free_providers(self) -> list[str]:
        free = ["ollama", "groq", "openrouter", "huggingface", "together", "perplexity", "mistral"]
        return [p for p in free if p in self.providers and self.providers[p].available]

    def is_provider_allowed(self, name: str) -> bool:
        if not name:
            return False
        if self.free_only_providers and name not in self.free_providers:
            return False
        provider = self.providers.get(name)
        return bool(provider and provider.enabled)

    def runtime_settings(self) -> dict[str, bool]:
        return {
            "filesystem_full_access": bool(self.filesystem_full_access),
            "browser_automation": bool(self.browser_automation),
            "browser_external_sites": bool(self.browser_external_sites),
            "free_only_providers": bool(self.free_only_providers),
        }

    def update_runtime_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        changed: list[str] = []
        for key, value in (patch or {}).items():
            if not hasattr(self, key):
                continue
            current = getattr(self, key)
            if not isinstance(current, bool):
                continue
            normalized = bool(value)
            if current != normalized:
                setattr(self, key, normalized)
                changed.append(key)
        if changed:
            self._save_runtime_settings()
        return {"changed": changed, "settings": self.runtime_settings()}

    def _load_runtime_settings(self):
        if not RUNTIME_SETTINGS_PATH.exists():
            return
        try:
            raw = json.loads(RUNTIME_SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return
        self.update_runtime_settings(raw.get("settings") or {})

    def _save_runtime_settings(self):
        RUNTIME_SETTINGS_PATH.write_text(
            json.dumps({"settings": self.runtime_settings()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

_config: Optional[IsaacConfig] = None

def get_config() -> IsaacConfig:
    global _config
    if _config is None:
        _config = IsaacConfig()
    return _config
