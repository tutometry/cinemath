"""Local Ollama HTTP client for classify / extract-text (not freeform teach)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from cinemath.core.logger import get_logger

log = get_logger("ollama")

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_CLASSIFY_MODEL = "llama3.1:8b"


@dataclass(frozen=True)
class OllamaToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class OllamaChatTurn:
    text: str
    tool_calls: tuple[OllamaToolCall, ...]


def use_ollama_classify() -> bool:
    return (os.environ.get("CINEMATH_CLASSIFY_PROVIDER") or "").strip().lower() == "ollama"


def ollama_base_url() -> str:
    raw = (os.environ.get("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE_URL).strip()
    return raw.rstrip("/")


def ollama_classify_model() -> str:
    return (
        os.environ.get("OLLAMA_CLASSIFY_MODEL")
        or os.environ.get("OLLAMA_MODEL")
        or DEFAULT_OLLAMA_CLASSIFY_MODEL
    )


def ollama_timeout_sec() -> float:
    raw = (os.environ.get("OLLAMA_TIMEOUT_SEC") or "180").strip()
    try:
        return max(5.0, float(raw))
    except ValueError:
        return 180.0


def anthropic_tools_to_ollama(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tool in tools:
        out.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description") or "",
                    "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
                },
            }
        )
    return out


def _parse_tool_arguments(raw: object) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    return {}


def _post_chat(body: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"{ollama_base_url()}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=ollama_timeout_sec()) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama chat failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama unreachable at {ollama_base_url()}: {exc.reason}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Ollama returned a non-object JSON response.")
    message = data.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("Ollama response missing message object.")
    return message


def chat_text(
    *,
    system: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    model: str | None = None,
) -> str:
    chosen = model or ollama_classify_model()
    log.debug("ollama chat model=%s max_tokens=%d messages=%d", chosen, max_tokens, len(messages))
    message = _post_chat(
        {
            "model": chosen,
            "messages": _with_system(system, messages),
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
    )
    return str(message.get("content") or "").strip()


def chat_with_tools(
    *,
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    max_tokens: int,
    model: str | None = None,
) -> OllamaChatTurn:
    chosen = model or ollama_classify_model()
    log.debug(
        "ollama chat+tools model=%s max_tokens=%d tools=%d",
        chosen,
        max_tokens,
        len(tools),
    )
    message = _post_chat(
        {
            "model": chosen,
            "messages": _with_system(system, messages),
            "tools": tools,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
    )
    text = str(message.get("content") or "").strip()
    raw_calls = message.get("tool_calls")
    tool_calls: list[OllamaToolCall] = []
    if isinstance(raw_calls, list):
        for index, item in enumerate(raw_calls):
            if not isinstance(item, dict):
                continue
            fn = item.get("function")
            if not isinstance(fn, dict):
                continue
            name = str(fn.get("name") or "").strip()
            if not name:
                continue
            call_id = str(item.get("id") or f"call_{index}")
            tool_calls.append(
                OllamaToolCall(
                    id=call_id,
                    name=name,
                    arguments=_parse_tool_arguments(fn.get("arguments")),
                )
            )
    return OllamaChatTurn(text=text, tool_calls=tuple(tool_calls))


def _with_system(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not system.strip():
        return list(messages)
    return [{"role": "system", "content": system}, *messages]


def append_assistant_tool_turn(
    messages: list[dict[str, Any]],
    turn: OllamaChatTurn,
) -> None:
    if not turn.tool_calls:
        messages.append({"role": "assistant", "content": turn.text})
        return
    tool_calls_payload: list[dict[str, Any]] = []
    for call in turn.tool_calls:
        tool_calls_payload.append(
            {
                "id": call.id,
                "function": {
                    "name": call.name,
                    "arguments": call.arguments,
                },
            }
        )
    messages.append(
        {
            "role": "assistant",
            "content": turn.text,
            "tool_calls": tool_calls_payload,
        }
    )


def append_tool_result(
    messages: list[dict[str, Any]],
    *,
    tool_name: str,
    content: str,
) -> None:
    messages.append({"role": "tool", "content": content, "tool_name": tool_name})
