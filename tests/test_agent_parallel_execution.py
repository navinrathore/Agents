import os
import sys
import tempfile
from pathlib import Path
import pytest

AGENTS_ROOT = str(Path(__file__).resolve().parent.parent)
if AGENTS_ROOT not in sys.path:
    sys.path.insert(0, AGENTS_ROOT)

from core.llm_clients import MockLLMClient
from data_analyst.agent import DataAnalystAgent


@pytest.mark.anyio
async def test_agent_run_parallel_tool_calls_async():
    """
    Verify that DataAnalystAgent.run_async executes multiple tool calls
    from a single LLM response turn concurrently and records all results in order.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        config = {
            "name": "test_parallel_analyst",
            "model": "mock",
            "system": "You are a test analyst.",
            "verbose": True,
            "use_checklist": True,
            "tool_timeout": 5.0,
        }

        agent = DataAnalystAgent(config=config, output_dir=tmp_dir)

        # Mock LLM emits 2 tool calls concurrently on Turn 1, then finishes on Turn 2
        mock_llm = MockLLMClient(
            canned_responses=[
                "I will prepare the checklist and compute the result concurrently.",
                "All tasks finished successfully. Here is the final answer.",
            ],
            canned_tool_calls=[
                [
                    {
                        "id": "tc_py_1",
                        "name": "execute_python",
                        "input": {"code": "print('Parallel Python 1 Finished')"},
                    },
                    {
                        "id": "tc_cl_1",
                        "name": "manage_checklist",
                        "input": {"action": "add", "task_name": "Review sales numbers"},
                    },
                ],
                [],  # Turn 2: no tool calls
            ],
        )
        agent.llm = mock_llm

        await agent.run_async(data_path="test_sales.csv", question="Top revenue items?")

        # 1. Verify checklist state updated
        assert "Review sales numbers" in agent.checklist
        assert agent.checklist["Review sales numbers"] is False

        # 2. Inspect LLM message history
        tool_messages = [m for m in agent.llm.messages if m.get("role") == "tool"]
        assert len(tool_messages) == 2

        # 3. Assert preserved order & content
        assert tool_messages[0]["tool_call_id"] == "tc_py_1"
        assert tool_messages[0]["name"] == "execute_python"
        assert "Parallel Python 1 Finished" in tool_messages[0]["content"]

        assert tool_messages[1]["tool_call_id"] == "tc_cl_1"
        assert tool_messages[1]["name"] == "manage_checklist"
        assert "Task 'Review sales numbers' added to checklist" in tool_messages[1]["content"]


def test_agent_run_sync_wrapper_compatibility():
    """
    Verify that the synchronous agent.run(...) entrypoint remains 100% backwards
    compatible and executes the async agent loop cleanly.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        config = {
            "name": "test_sync_wrapper",
            "model": "mock",
            "system": "You are a test analyst.",
            "verbose": False,
            "use_checklist": True,
        }

        agent = DataAnalystAgent(config=config, output_dir=tmp_dir)

        mock_llm = MockLLMClient(
            canned_responses=["Step 1", "Complete"],
            canned_tool_calls=[
                [
                    {
                        "id": "tc_sync_1",
                        "name": "manage_checklist",
                        "input": {"action": "add", "task_name": "Sync Task"},
                    }
                ],
                [],
            ],
        )
        agent.llm = mock_llm

        # Call synchronous run()
        agent.run(data_path="dummy.csv", question="Summarize")

        assert "Sync Task" in agent.checklist
        tool_msgs = [m for m in agent.llm.messages if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["tool_call_id"] == "tc_sync_1"


@pytest.mark.anyio
async def test_agent_parallel_custom_tool_registration():
    """
    Verify that custom tools registered directly on agent.dispatcher
    participate seamlessly in concurrent multi-tool turns.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        config = {
            "name": "test_custom_tool",
            "model": "mock",
            "system": "You are a test analyst.",
            "verbose": True,
        }

        agent = DataAnalystAgent(config=config, output_dir=tmp_dir)

        # Register custom async tool
        async def fetch_remote_stats(metric: str) -> str:
            return f"Metric {metric}: 42"

        agent.dispatcher.register_tool("fetch_stats", fetch_remote_stats)

        mock_llm = MockLLMClient(
            canned_responses=["Fetching stats and running python", "Done"],
            canned_tool_calls=[
                [
                    {
                        "id": "tc_custom_1",
                        "name": "fetch_stats",
                        "input": {"metric": "churn_rate"},
                    },
                    {
                        "id": "tc_py_custom",
                        "name": "execute_python",
                        "input": {"code": "print('Custom tool test')"},
                    },
                ],
                [],
            ],
        )
        agent.llm = mock_llm

        await agent.run_async(data_path="dummy.csv", question="Metrics")

        tool_msgs = [m for m in agent.llm.messages if m.get("role") == "tool"]
        assert len(tool_msgs) == 2
        assert tool_msgs[0]["tool_call_id"] == "tc_custom_1"
        assert "Metric churn_rate: 42" in tool_msgs[0]["content"]
        assert tool_msgs[1]["tool_call_id"] == "tc_py_custom"
        assert "Custom tool test" in tool_msgs[1]["content"]


@pytest.mark.anyio
async def test_agent_config_sequential_override():
    """
    Verify that setting parallel_tool_calls=False in agent config
    causes the agent dispatcher to execute tools in sequential mode.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        config = {
            "name": "test_sequential_override",
            "model": "mock",
            "system": "You are a test analyst.",
            "verbose": True,
            "parallel_tool_calls": False,
            "max_concurrency": 1,
        }

        agent = DataAnalystAgent(config=config, output_dir=tmp_dir)
        assert agent.dispatcher.parallel_execution is False

        mock_llm = MockLLMClient(
            canned_responses=["Running sequentially", "Finished"],
            canned_tool_calls=[
                [
                    {
                        "id": "tc_s1",
                        "name": "manage_checklist",
                        "input": {"action": "add", "task_name": "Seq Task 1"},
                    },
                    {
                        "id": "tc_s2",
                        "name": "manage_checklist",
                        "input": {"action": "add", "task_name": "Seq Task 2"},
                    },
                ],
                [],
            ],
        )
        agent.llm = mock_llm

        await agent.run_async(data_path="dummy.csv", question="Steps")

        assert agent.checklist["Seq Task 1"] is False
        assert agent.checklist["Seq Task 2"] is False
        tool_msgs = [m for m in agent.llm.messages if m.get("role") == "tool"]
        assert len(tool_msgs) == 2
        assert tool_msgs[0]["tool_call_id"] == "tc_s1"
        assert tool_msgs[1]["tool_call_id"] == "tc_s2"


@pytest.mark.anyio
async def test_agent_parallel_mcp_and_local_tool_execution():
    """
    Verify that remote MCP tools and local Python execution tools can be dispatched
    concurrently within the exact same LLM turn.
    """
    from core.mcp.config import MCPServerConfig, MCPRegistryConfig
    from core.mcp.client import MCPClientManager

    mock_server_script = str(Path(__file__).resolve().parent / "mock_mcp_server.py")
    server_cfg = MCPServerConfig(
        command=sys.executable,
        args=[mock_server_script],
        timeout_seconds=10.0,
    )
    registry = MCPRegistryConfig(servers={"mock_calc": server_cfg})

    with tempfile.TemporaryDirectory() as tmp_dir:
        config = {
            "name": "test_mcp_parallel",
            "model": "mock",
            "system": "Analyst with MCP tools.",
            "verbose": True,
            "parallel_tool_calls": True,
        }

        agent = DataAnalystAgent(config=config, output_dir=tmp_dir)

        async with MCPClientManager(registry) as manager:
            # Register MCP tool into agent dispatcher
            agent.dispatcher.register_mcp_tool(
                tool_name="add",
                conn_or_manager=manager,
                server_name="mock_calc",
            )

            mock_llm = MockLLMClient(
                canned_responses=["Executing MCP add and Python print in parallel", "Finished"],
                canned_tool_calls=[
                    [
                        {
                            "id": "tc_mcp_add",
                            "name": "add",
                            "input": {"a": 20, "b": 22},
                        },
                        {
                            "id": "tc_local_py",
                            "name": "execute_python",
                            "input": {"code": "print('Parallel Local Execution')"},
                        },
                    ],
                    [],
                ],
            )
            agent.llm = mock_llm

            await agent.run_async(data_path="dummy.csv", question="Compute 20 + 22 and print")

            tool_msgs = [m for m in agent.llm.messages if m.get("role") == "tool"]
            assert len(tool_msgs) == 2

            # Assert MCP result
            assert tool_msgs[0]["tool_call_id"] == "tc_mcp_add"
            assert "42" in tool_msgs[0]["content"]

            # Assert local execution result
            assert tool_msgs[1]["tool_call_id"] == "tc_local_py"
            assert "Parallel Local Execution" in tool_msgs[1]["content"]


