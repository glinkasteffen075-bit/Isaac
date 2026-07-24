"""
Isaac – Optional Sentry AI Agent Monitoring
=============================================
No-op when SENTRY_DSN is unset. Manual gen_ai spans for the custom aiohttp
relay (no OpenAI/Anthropic SDK auto-integration).

Env:
  SENTRY_DSN                 — enable Sentry (required)
  SENTRY_TRACES_SAMPLE_RATE  — optional override (default: 1.0 dev, 0.1 production)
  SENTRY_ENVIRONMENT         — default development / ISAAC_ENV / production
  SENTRY_RELEASE             — default isaac@5.3
  SENTRY_INCLUDE_PROMPTS     — default 1 (owner-confirmed PII capture)

Docs: https://docs.sentry.io/platforms/python/tracing/instrumentation/custom-instrumentation/ai-agents-module/
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from contextlib import contextmanager
from typing import Any, Iterator, Optional

log = logging.getLogger("Isaac.Sentry")

_initialized = False
_include_prompts = True
_session_conversation_id: Optional[str] = None


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def is_enabled() -> bool:
    return _initialized


def include_prompts() -> bool:
    return _include_prompts and _initialized


def init_sentry() -> bool:
    """Initialize Sentry once. Safe to call repeatedly. Returns True if active."""
    global _initialized, _include_prompts, _session_conversation_id

    if _initialized:
        return True

    dsn = (os.getenv("SENTRY_DSN") or "").strip()
    if not dsn:
        log.info("Sentry: SENTRY_DSN not set — AI monitoring disabled")
        return False

    try:
        import sentry_sdk
    except ImportError:
        log.warning("Sentry: sentry-sdk not installed (pip install 'sentry-sdk>=2.60.0')")
        return False

    _include_prompts = _env_bool("SENTRY_INCLUDE_PROMPTS", True)

    environment = (
        os.getenv("SENTRY_ENVIRONMENT")
        or os.getenv("ISAAC_ENV")
        or ("production" if _env_bool("ISAAC_FREE_CLOUD", False) else "development")
    ).strip() or "development"

    # Production default 0.1 (cost/volume); full sample in development unless overridden
    default_rate = "0.1" if environment.lower() in {"production", "prod", "live"} else "1.0"
    try:
        sample_rate = float(
            os.getenv("SENTRY_TRACES_SAMPLE_RATE", default_rate) or default_rate
        )
    except ValueError:
        sample_rate = float(default_rate)
    sample_rate = max(0.0, min(1.0, sample_rate))

    init_kwargs: dict[str, Any] = {
        "dsn": dsn,
        "traces_sample_rate": sample_rate,
        "send_default_pii": _include_prompts,
        # Standalone gen_ai envelopes (default True on SDK ≥2.60; required for Conversations)
        "stream_gen_ai_spans": True,
        "environment": environment,
        "release": os.getenv("SENTRY_RELEASE", "isaac@5.3"),
    }

    try:
        sentry_sdk.init(**init_kwargs)
    except TypeError:
        # Older SDK: drop unknown kwargs and retry
        init_kwargs.pop("stream_gen_ai_spans", None)
        sentry_sdk.init(**init_kwargs)

    _initialized = True
    _session_conversation_id = f"isaac-{uuid.uuid4().hex[:16]}"
    set_conversation_id(_session_conversation_id)

    owner = (os.getenv("ISAAC_OWNER") or "owner").strip() or "owner"
    try:
        sentry_sdk.set_user({"id": owner, "username": owner})
    except Exception:
        pass

    log.info(
        "Sentry AI monitoring active (traces_sample_rate=%s include_prompts=%s)",
        sample_rate,
        _include_prompts,
    )
    return True


def session_conversation_id() -> Optional[str]:
    return _session_conversation_id


def set_conversation_id(conversation_id: str) -> None:
    """Attach gen_ai.conversation.id for multi-turn Conversations view."""
    if not _initialized or not conversation_id:
        return
    try:
        import sentry_sdk.ai

        sentry_sdk.ai.set_conversation_id(str(conversation_id))
    except Exception:
        try:
            import sentry_sdk

            sentry_sdk.set_tag("conversation_id", str(conversation_id)[:120])
        except Exception:
            pass


def _messages_json(system: str, user_prompt: str) -> str:
    msgs: list[dict[str, Any]] = []
    if system:
        msgs.append(
            {
                "role": "system",
                "parts": [{"type": "text", "content": system[:8000]}],
            }
        )
    msgs.append(
        {
            "role": "user",
            "parts": [{"type": "text", "content": (user_prompt or "")[:12000]}],
        }
    )
    return json.dumps(msgs, ensure_ascii=False)


def _output_json(text: str) -> str:
    return json.dumps(
        [
            {
                "role": "assistant",
                "parts": [{"type": "text", "content": (text or "")[:12000]}],
            }
        ],
        ensure_ascii=False,
    )


@contextmanager
def gen_ai_chat_span(
    *,
    model: str,
    provider: str,
    system: str = "",
    prompt: str = "",
    agent_name: str = "Isaac",
) -> Iterator[Any]:
    """
    Manual gen_ai.chat span around a relay LLM call.
    Yields a span-like object with set_data, or a no-op stub.
    """
    if not _initialized:
        yield _NoopSpan()
        return

    import sentry_sdk

    model_name = (model or "unknown").strip() or "unknown"
    provider_name = (provider or "unknown").strip().lower() or "unknown"
    name = f"chat {model_name}"

    with sentry_sdk.start_span(op="gen_ai.chat", name=name) as span:
        try:
            span.set_data("gen_ai.operation.name", "chat")
            span.set_data("gen_ai.request.model", model_name)
            span.set_data("gen_ai.response.model", model_name)
            span.set_data("gen_ai.provider.name", provider_name)
            span.set_data("gen_ai.agent.name", agent_name)
            span.set_data("gen_ai.pipeline.name", "isaac-relay")
            if _include_prompts:
                if system:
                    span.set_data("gen_ai.system_instructions", system[:8000])
                span.set_data(
                    "gen_ai.input.messages",
                    _messages_json(system, prompt),
                )
        except Exception as exc:
            log.debug("gen_ai.chat span setup: %s", exc)
        yield span


def finish_chat_span(
    span: Any,
    *,
    result_text: str,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
    model: Optional[str] = None,
    success: bool = True,
) -> None:
    """Attach response + usage attributes to an open gen_ai.chat span."""
    if not _initialized or span is None or isinstance(span, _NoopSpan):
        return
    try:
        if model:
            span.set_data("gen_ai.response.model", model)
        if _include_prompts and result_text is not None:
            span.set_data("gen_ai.output.messages", _output_json(result_text))
        if input_tokens is not None and input_tokens >= 0:
            span.set_data("gen_ai.usage.input_tokens", int(input_tokens))
        if output_tokens is not None and output_tokens >= 0:
            span.set_data("gen_ai.usage.output_tokens", int(output_tokens))
        if total_tokens is not None and total_tokens >= 0:
            span.set_data("gen_ai.usage.total_tokens", int(total_tokens))
        elif input_tokens is not None and output_tokens is not None:
            span.set_data(
                "gen_ai.usage.total_tokens",
                int(input_tokens) + int(output_tokens),
            )
        if not success:
            span.set_data("gen_ai.response.finish_reasons", json.dumps(["error"]))
        else:
            span.set_data("gen_ai.response.finish_reasons", json.dumps(["stop"]))
    except Exception as exc:
        log.debug("finish_chat_span: %s", exc)


@contextmanager
def invoke_agent_span(
    *,
    agent_name: str = "Isaac",
    model: str = "isaac-kernel",
    user_input: str = "",
) -> Iterator[Any]:
    """gen_ai.invoke_agent span for a full kernel process turn."""
    if not _initialized:
        yield _NoopSpan()
        return

    import sentry_sdk

    name = f"invoke_agent {agent_name}"
    with sentry_sdk.start_span(op="gen_ai.invoke_agent", name=name) as span:
        try:
            span.set_data("gen_ai.operation.name", "invoke_agent")
            span.set_data("gen_ai.agent.name", agent_name)
            span.set_data("gen_ai.request.model", model or "isaac-kernel")
            span.set_data("gen_ai.pipeline.name", "isaac-kernel")
            if _include_prompts and user_input:
                span.set_data(
                    "gen_ai.input.messages",
                    json.dumps(
                        [
                            {
                                "role": "user",
                                "parts": [
                                    {
                                        "type": "text",
                                        "content": user_input[:12000],
                                    }
                                ],
                            }
                        ],
                        ensure_ascii=False,
                    ),
                )
        except Exception as exc:
            log.debug("invoke_agent span setup: %s", exc)
        yield span


def finish_agent_span(span: Any, *, result_text: str = "", model: str = "") -> None:
    if not _initialized or span is None or isinstance(span, _NoopSpan):
        return
    try:
        if model:
            span.set_data("gen_ai.request.model", model)
            span.set_data("gen_ai.response.model", model)
        if _include_prompts and result_text is not None:
            span.set_data("gen_ai.output.messages", _output_json(result_text))
    except Exception as exc:
        log.debug("finish_agent_span: %s", exc)


@contextmanager
def execute_tool_span(
    tool_name: str,
    *,
    arguments: Any = None,
    description: str = "",
) -> Iterator[Any]:
    if not _initialized:
        yield _NoopSpan()
        return

    import sentry_sdk

    name = f"execute_tool {tool_name}"
    with sentry_sdk.start_span(op="gen_ai.execute_tool", name=name) as span:
        try:
            span.set_data("gen_ai.operation.name", "execute_tool")
            span.set_data("gen_ai.tool.name", tool_name)
            span.set_data("gen_ai.tool.type", "function")
            if description:
                span.set_data("gen_ai.tool.description", description[:500])
            if arguments is not None and _include_prompts:
                if not isinstance(arguments, str):
                    arguments = json.dumps(arguments, ensure_ascii=False, default=str)
                span.set_data("gen_ai.tool.call.arguments", arguments[:8000])
        except Exception as exc:
            log.debug("execute_tool span setup: %s", exc)
        yield span


def finish_tool_span(span: Any, result: Any = None) -> None:
    if not _initialized or span is None or isinstance(span, _NoopSpan):
        return
    if result is None or not _include_prompts:
        return
    try:
        if not isinstance(result, str):
            result = json.dumps(result, ensure_ascii=False, default=str)
        span.set_data("gen_ai.tool.call.result", result[:8000])
    except Exception as exc:
        log.debug("finish_tool_span: %s", exc)


class _NoopSpan:
    def set_data(self, *args: Any, **kwargs: Any) -> None:
        return None

    def set_attribute(self, *args: Any, **kwargs: Any) -> None:
        return None
