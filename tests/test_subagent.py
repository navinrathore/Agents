import asyncio
from pathlib import Path
import sys
import pytest

AGENTS_ROOT = str(Path(__file__).resolve().parent.parent)
if AGENTS_ROOT not in sys.path:
    sys.path.insert(0, AGENTS_ROOT)

from core.dispatcher import AsyncToolDispatcher
from core.llm_clients import MockLLMClient
from core.skills import SkillRegistry
from core.subagent import (
    SkillSubAgent,
    SubAgentConfig,
    SubAgentEngine,
    SubAgentExecutionResult,
)


@pytest.fixture
def skills_registry():
    skills_root = Path(AGENTS_ROOT) / "skills"
    reg = SkillRegistry(search_paths=[skills_root])
    reg.discover_skills()
    return reg


# ==============================================================================
# 1. Single-Turn SubAgent Execution & Synthesis
# ==============================================================================

@pytest.mark.anyio
async def test_subagent_clean_execution(skills_registry):
    pkg = skills_registry.get_skill("data_analyst")
    assert pkg is not None

    # Mock client returns 1 tool call turn, then final answer
    canned_responses = [
        # Turn 1: Call describe_table
        {
            "text": "I will inspect the users table structure first.",
            "tool_calls": [
                {
                    "id": "sub_call_1",
                    "name": "describe_table",
                    "input": {"table_name": "users"},
                }
            ],
        },
        # Turn 2: Synthesize final answer (no tool calls)
        {
            "text": "The users table contains columns: id, name, email, and created_at.",
            "tool_calls": [],
        },
    ]

    mock_llm = MockLLMClient(canned_responses=canned_responses)
    config = SubAgentConfig(max_loops=5, timeout_seconds=5.0)

    subagent = SkillSubAgent(skill_package=pkg, config=config, llm_client=mock_llm)
    result = await subagent.run("What columns exist in the users table?")

    assert result.success is True
    assert result.total_loops == 2
    assert "users table contains columns" in result.final_answer
    assert result.skill_name == "data_analyst"
    assert len(result.trajectory) == 2


# ==============================================================================
# 2. Context Isolation Verification
# ==============================================================================

@pytest.mark.anyio
async def test_subagent_context_isolation(skills_registry):
    pkg = skills_registry.get_skill("data_analyst")
    parent_llm = MockLLMClient()
    parent_llm.add_user_message("Parent initial instruction")

    child_canned = [
        {"text": "Subagent answering directly", "tool_calls": []}
    ]
    child_llm = MockLLMClient(canned_responses=child_canned)

    subagent = SkillSubAgent(skill_package=pkg, llm_client=child_llm)
    res = await subagent.run("Child specific task")

    assert res.final_answer == "Subagent answering directly"

    # Verify parent LLM message history is 100% unaffected
    assert len(parent_llm.messages) == 1
    assert parent_llm.messages[0]["content"] == "Parent initial instruction"

    # Verify child LLM message history has system SOP and child task
    assert child_llm.system_prompt != ""
    assert "data_analyst" in child_llm.system_prompt
    child_roles = [m["role"] for m in child_llm.messages]
    assert "user" in child_roles
    assert "assistant" in child_roles


# ==============================================================================
# 3. Safety Guardrails: Max Loops Limit (Rule 1)
# ==============================================================================

@pytest.mark.anyio
async def test_subagent_max_loops_enforced(skills_registry):
    pkg = skills_registry.get_skill("data_analyst")

    # 3 tool loop iterations followed by final synthesis response
    infinite_tool_responses = [
        {
            "text": f"Iteration {i}",
            "tool_calls": [{"id": f"c_{i}", "name": "query_table", "input": {"table_name": "users"}}],
        }
        for i in range(3)
    ]
    # Plus final synthesis response when forced
    infinite_tool_responses.append({"text": "Forced synthesis report", "tool_calls": []})

    mock_llm = MockLLMClient(canned_responses=infinite_tool_responses)
    config = SubAgentConfig(max_loops=3, timeout_seconds=5.0)

    subagent = SkillSubAgent(skill_package=pkg, config=config, llm_client=mock_llm)
    result = await subagent.run("Endless query loop")

    assert result.total_loops == 3
    assert result.success is True
    assert "Forced synthesis report" in result.final_answer


# ==============================================================================
# 4. Safety Guardrails: Timeout Enforcement (Rule 4)
# ==============================================================================

@pytest.mark.anyio
async def test_subagent_timeout_protection(skills_registry):
    pkg = skills_registry.get_skill("data_analyst")

    # Custom dispatcher with slow tool
    slow_dispatcher = AsyncToolDispatcher()

    async def slow_tool():
        await asyncio.sleep(0.5)
        return "slow done"

    slow_dispatcher.register_tool("slow_tool", slow_tool)

    canned = [
        {"text": "Running slow tool", "tool_calls": [{"id": "s1", "name": "slow_tool", "input": {}}]}
    ]
    mock_llm = MockLLMClient(canned_responses=canned)
    config = SubAgentConfig(timeout_seconds=0.08)  # Timeout less than sleep

    subagent = SkillSubAgent(
        skill_package=pkg,
        config=config,
        llm_client=mock_llm,
        dispatcher=slow_dispatcher,
    )
    result = await subagent.run("Trigger timeout")

    assert result.success is False
    assert "timed out" in result.error.lower()


# ==============================================================================
# 5. Parent Dispatcher Tool Bridging
# ==============================================================================

@pytest.mark.anyio
async def test_subagent_engine_parent_tool_bridge(skills_registry):
    engine = SubAgentEngine(registry=skills_registry)
    parent_dispatcher = AsyncToolDispatcher()

    canned = [
        {"text": "Summary of users analysis from subagent.", "tool_calls": []}
    ]
    mock_llm = MockLLMClient(canned_responses=canned)

    # Register the subagent as a standard tool on the parent dispatcher
    registered_name = engine.register_skill_as_tool(
        dispatcher=parent_dispatcher,
        skill_name="data_analyst",
        llm_client=mock_llm,
    )
    assert registered_name == "delegate_to_data_analyst"
    assert parent_dispatcher.has_tool("delegate_to_data_analyst")

    # Parent dispatcher invokes the subagent via standard dispatch!
    results = await parent_dispatcher.dispatch([
        {
            "id": "parent_call_1",
            "name": "delegate_to_data_analyst",
            "input": {"task": "Audit user database"},
        }
    ])

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].result == "Summary of users analysis from subagent."
