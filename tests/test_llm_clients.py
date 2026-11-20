"""Unit tests for Universal LLM Client Engine in projects/Agents/core/llm_clients.py."""

import json
import pytest
from pydantic import BaseModel, Field

from core.llm_clients import (
    AnthropicClient,
    BaseLLMClient,
    HuggingFaceClient,
    MockLLMClient,
    OpenAILLMClient,
    get_llm_client,
    prepare_strict_json_schema,
    resolve_hf_token,
)


class SampleAgentSchema(BaseModel):
    plan_name: str = Field(..., min_length=1)
    priority: int = Field(..., ge=1, le=5)
    action_items: list[str] = Field(default_factory=list)


def test_mock_llm_client_stateless_and_stateful():
    """Verify MockLLMClient works in both stateful ReAct and stateless graph modes."""
    client = MockLLMClient(canned_responses=["Step 1", "Step 2"])

    # Stateless generate
    r1 = client.generate([{"role": "user", "content": "Hello"}])
    assert r1 == "Step 1"

    # Stateful ReAct generate_response
    client.add_user_message("What next?")
    r2 = client.generate_response()
    assert r2["text"] == "Step 2"
    assert len(client.call_history) == 2


def test_mock_llm_client_structured_generation():
    """Verify generate_structured parses JSON canned response into Pydantic model."""
    valid_payload = json.dumps({
        "plan_name": "Autonomous Data Pipeline",
        "priority": 1,
        "action_items": ["Download dataset", "Compute aggregates"],
    })
    client = MockLLMClient(canned_responses=[f"```json\n{valid_payload}\n```"])

    model = client.generate_structured(
        messages=[{"role": "user", "content": "Create plan"}],
        schema=SampleAgentSchema,
    )

    assert isinstance(model, SampleAgentSchema)
    assert model.plan_name == "Autonomous Data Pipeline"
    assert model.priority == 1
    assert len(model.action_items) == 2


def test_structured_generation_repair():
    """Verify single-repair loop handles initial syntax glitch."""
    bad_json = "plan_name: unquoted, priority: 2"
    good_json = json.dumps({
        "plan_name": "Repaired Plan",
        "priority": 2,
        "action_items": ["Fixed syntax"],
    })
    client = MockLLMClient(canned_responses=[bad_json, good_json])

    model = client.generate_structured(
        messages=[{"role": "user", "content": "Create plan"}],
        schema=SampleAgentSchema,
    )

    assert isinstance(model, SampleAgentSchema)
    assert model.plan_name == "Repaired Plan"
    assert model.priority == 2


def test_hf_client_token_enforcement_and_router_endpoint():
    """Verify HuggingFaceClient requires token and configures router URL."""
    with pytest.raises(ValueError, match="HF_TOKEN is required"):
        HuggingFaceClient(hf_token="")

    client = HuggingFaceClient(hf_token="test_hf_token_123")
    assert str(client.client.base_url) == "https://router.huggingface.co/v1/"


def test_get_llm_client_factory_options():
    """Verify factory returns appropriate provider client."""
    mock = get_llm_client(provider="mock")
    assert isinstance(mock, MockLLMClient)

    openai = get_llm_client(provider="openai", api_key="sk-test-123")
    assert isinstance(openai, OpenAILLMClient)

    hf = get_llm_client(provider="hf", hf_token="hf-test-123")
    assert isinstance(hf, HuggingFaceClient)


def test_prepare_strict_json_schema():
    """Verify strict schema preparation sets additionalProperties: False and required list."""
    strict = prepare_strict_json_schema(SampleAgentSchema)
    assert strict["additionalProperties"] is False
    assert "properties" in strict
    assert set(strict["properties"].keys()) == set(strict["required"])
    assert "plan_name" in strict["required"]
    assert "priority" in strict["required"]
    assert "action_items" in strict["required"]


def test_mock_llm_client_structured_modes():
    """Verify MockLLMClient explicitly respects native vs prompt_injection modes."""
    valid_payload = json.dumps({
        "plan_name": "Native Mode Plan",
        "priority": 1,
        "action_items": ["Verify native decoding"],
    })
    
    # 1. Native mode
    client = MockLLMClient(canned_responses=[valid_payload])
    model = client.generate_structured(
        messages=[{"role": "user", "content": "Run"}],
        schema=SampleAgentSchema,
        mode="native",
    )
    assert isinstance(model, SampleAgentSchema)
    assert model.plan_name == "Native Mode Plan"
    assert client.last_structured_mode == "native"

    # 2. Prompt injection mode
    client_prompt = MockLLMClient(canned_responses=[f"```json\n{valid_payload}\n```"])
    model2 = client_prompt.generate_structured(
        messages=[{"role": "user", "content": "Run"}],
        schema=SampleAgentSchema,
        mode="prompt_injection",
    )
    assert isinstance(model2, SampleAgentSchema)
    assert client_prompt.last_structured_mode == "prompt_injection"


def test_mock_llm_client_auto_fallback_on_native_failure():
    """Verify auto mode seamlessly falls back to prompt injection when native fails."""
    valid_payload = json.dumps({
        "plan_name": "Fallback Recovered Plan",
        "priority": 3,
        "action_items": ["Auto fallback activated"],
    })
    client = MockLLMClient(
        canned_responses=[valid_payload],
        native_fail=True,  # Simulate native endpoint rejection
        structured_output_mode="auto",
    )

    model = client.generate_structured(
        messages=[{"role": "user", "content": "Run"}],
        schema=SampleAgentSchema,
    )
    assert isinstance(model, SampleAgentSchema)
    assert model.plan_name == "Fallback Recovered Plan"
    # Fallen back to prompt injection
    assert client.last_structured_mode == "prompt_injection"


def test_mock_llm_client_strict_native_mode_raises_on_failure():
    """Verify mode='native' strictly raises when native fails without silent fallback."""
    client = MockLLMClient(
        canned_responses=["{}"],
        native_fail=True,
    )
    with pytest.raises(RuntimeError, match="Mock native generation failed"):
        client.generate_structured(
            messages=[{"role": "user", "content": "Run"}],
            schema=SampleAgentSchema,
            mode="native",
        )


def test_openai_client_native_structured_request(monkeypatch):
    """Verify OpenAILLMClient passes strict response_format to OpenAI API."""
    client = OpenAILLMClient(api_key="sk-dummy-test")

    captured_kwargs = {}

    class DummyChoice:
        class DummyMsg:
            content = json.dumps({
                "plan_name": "OpenAI Strict Plan",
                "priority": 2,
                "action_items": ["Native grammar tested"],
            })
        message = DummyMsg()

    class DummyResponse:
        choices = [DummyChoice()]

    def mock_create(**kwargs):
        captured_kwargs.update(kwargs)
        return DummyResponse()

    monkeypatch.setattr(client.client.chat.completions, "create", mock_create)

    result = client.generate_structured(
        messages=[{"role": "user", "content": "Create plan"}],
        schema=SampleAgentSchema,
        mode="native",
    )

    assert isinstance(result, SampleAgentSchema)
    assert result.plan_name == "OpenAI Strict Plan"
    assert "response_format" in captured_kwargs
    rf = captured_kwargs["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["name"] == "SampleAgentSchema"
    assert rf["json_schema"]["schema"]["additionalProperties"] is False


def test_anthropic_client_native_forced_tool_use(monkeypatch):
    """Verify AnthropicClient passes forced tool definition and tool_choice."""
    # Initialize without needing real API key by mocking Anthropic client
    client = AnthropicClient.__new__(AnthropicClient)
    client.model = "claude-3-5-sonnet-20241022"
    client.model_name = client.model
    client.messages = []
    client.system_prompt = ""
    client.temperature = 0.1
    client.max_retries = 1
    client.structured_output_mode = "native"

    captured_kwargs = {}

    class DummyBlock:
        type = "tool_use"
        name = "SampleAgentSchema"
        input = {
            "plan_name": "Claude Tool Use Plan",
            "priority": 1,
            "action_items": ["Forced tool verified"],
        }

    class DummyResponse:
        content = [DummyBlock()]

    class MockMessages:
        def create(self, **kwargs):
            captured_kwargs.update(kwargs)
            return DummyResponse()

    class MockAnthropic:
        messages = MockMessages()

    client.client = MockAnthropic()

    result = client.generate_structured(
        messages=[{"role": "user", "content": "Create plan"}],
        schema=SampleAgentSchema,
        mode="native",
    )

    assert isinstance(result, SampleAgentSchema)
    assert result.plan_name == "Claude Tool Use Plan"
    assert "tools" in captured_kwargs
    assert captured_kwargs["tools"][0]["name"] == "SampleAgentSchema"
    assert captured_kwargs["tool_choice"] == {"type": "tool", "name": "SampleAgentSchema"}


