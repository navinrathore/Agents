"""Unit tests for Universal LLM Client Engine in projects/Agents/core/llm_clients.py."""

import json
import pytest
from pydantic import BaseModel, Field

from core.llm_clients import (
    BaseLLMClient,
    HuggingFaceClient,
    MockLLMClient,
    OpenAILLMClient,
    get_llm_client,
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

