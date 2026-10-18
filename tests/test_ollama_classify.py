from unittest.mock import MagicMock, patch

import pytest

from cinemath.teaching import ollama as ollama_client
from cinemath.teaching.llm import _try_catalog_plan


def test_use_ollama_classify_reads_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CINEMATH_CLASSIFY_PROVIDER", raising=False)
    assert ollama_client.use_ollama_classify() is False
    monkeypatch.setenv("CINEMATH_CLASSIFY_PROVIDER", "ollama")
    assert ollama_client.use_ollama_classify() is True


def test_anthropic_tools_to_ollama_maps_input_schema() -> None:
    mapped = ollama_client.anthropic_tools_to_ollama(
        [
            {
                "name": "plan_linear",
                "description": "Linear equation",
                "input_schema": {
                    "type": "object",
                    "properties": {"problem_statement": {"type": "string"}},
                    "required": ["problem_statement"],
                },
            }
        ]
    )
    assert mapped[0]["function"]["name"] == "plan_linear"
    assert mapped[0]["function"]["parameters"]["required"] == ["problem_statement"]


@patch("cinemath.teaching.ollama._post_chat")
def test_chat_with_tools_parses_tool_calls(mock_post: MagicMock) -> None:
    mock_post.return_value = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call_1",
                "function": {
                    "name": "plan_linear",
                    "arguments": {"problem_statement": "2x+3=7"},
                },
            }
        ],
    }
    turn = ollama_client.chat_with_tools(
        system="sys",
        messages=[{"role": "user", "content": "Classify: 2x+3=7"}],
        tools=ollama_client.anthropic_tools_to_ollama(
            [
                {
                    "name": "plan_linear",
                    "description": "linear",
                    "input_schema": {
                        "type": "object",
                        "properties": {"problem_statement": {"type": "string"}},
                        "required": ["problem_statement"],
                    },
                }
            ]
        ),
        max_tokens=128,
    )
    assert turn.tool_calls[0].name == "plan_linear"
    assert turn.tool_calls[0].arguments["problem_statement"] == "2x+3=7"


@patch("cinemath.teaching.llm.ollama_chat_with_tools")
def test_try_catalog_plan_ollama_hits_linear(mock_chat: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CINEMATH_CLASSIFY_PROVIDER", "ollama")
    mock_chat.return_value = ollama_client.OllamaChatTurn(
        text="",
        tool_calls=(
            ollama_client.OllamaToolCall(
                id="call_1",
                name="plan_linear",
                arguments={
                    "problem_statement": "Solve $2x+3=7$.",
                    "left": "2*x+3",
                    "right": "7",
                },
            ),
        ),
    )
    hit = _try_catalog_plan("Solve 2x+3=7")
    assert hit is not None
    plan, planner = hit
    assert planner == "plan_linear"
    assert plan.get("problem")


@patch("cinemath.teaching.llm.ollama_chat_with_tools")
def test_try_catalog_plan_ollama_freeform_tool(mock_chat: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CINEMATH_CLASSIFY_PROVIDER", "ollama")
    mock_chat.return_value = ollama_client.OllamaChatTurn(
        text="",
        tool_calls=(
            ollama_client.OllamaToolCall(
                id="call_1",
                name="teach_freeform",
                arguments={"reason": "no catalog fit"},
            ),
        ),
    )
    assert _try_catalog_plan("Some exotic PDE") is None
