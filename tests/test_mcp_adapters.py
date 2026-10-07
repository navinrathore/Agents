"""Unit and integration tests for MCPToolAdapter and LangGraph StructuredTool conversion."""

import sys
from pathlib import Path
import pytest
from pydantic import ValidationError
import mcp.types as mcp_types

# Ensure projects/Agents is on sys.path
AGENTS_ROOT = Path(__file__).resolve().parent.parent
if str(AGENTS_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENTS_ROOT))

from core.mcp.config import MCPServerConfig, MCPRegistryConfig
from core.mcp.client import MCPClientManager
from core.mcp.adapters import (
    json_schema_to_pydantic_model,
    format_mcp_result,
    adapt_mcp_tool_to_langgraph,
    adapt_all_mcp_tools,
)

MOCK_SERVER_SCRIPT = str(Path(__file__).resolve().parent / "mock_mcp_server.py")


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_json_schema_to_pydantic_model_types():
    """Verify JSON schema properties correctly convert to Pydantic types and validation rules."""
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "limit": {"type": "integer", "description": "Max results", "default": 10},
            "ratio": {"type": "number", "description": "Threshold ratio"},
            "is_active": {"type": "boolean"},
            "tags": {"type": "array"},
            "metadata": {"type": "object"},
        },
        "required": ["query"],
    }

    Model = json_schema_to_pydantic_model("SearchArgs", schema)

    # Valid instantiation
    instance = Model(query="Agentic AI")
    assert instance.query == "Agentic AI"
    assert instance.limit == 10
    assert instance.ratio is None
    assert instance.is_active is None

    # Missing required field raises ValidationError
    with pytest.raises(ValidationError):
        Model(limit=5)


def test_format_mcp_result():
    """Verify result formatting from MCP CallToolResult content blocks."""
    # Success text block
    res_success = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="Hello world")],
        isError=False,
    )
    assert format_mcp_result(res_success) == "Hello world"

    # Multi-block output
    res_multi = mcp_types.CallToolResult(
        content=[
            mcp_types.TextContent(type="text", text="Line 1"),
            mcp_types.TextContent(type="text", text="Line 2"),
        ],
        isError=False,
    )
    assert format_mcp_result(res_multi) == "Line 1\nLine 2"

    # Error output
    res_error = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="Subprocess crashed")],
        isError=True,
    )
    assert format_mcp_result(res_error) == "[ERROR] Subprocess crashed"


@pytest.mark.anyio
async def test_adapt_mcp_tool_to_langgraph_invocation():
    """Verify that adapted MCP tools execute seamlessly as LangGraph StructuredTools."""
    server_cfg = MCPServerConfig(
        command=sys.executable,
        args=[MOCK_SERVER_SCRIPT],
        timeout_seconds=10.0,
    )
    registry = MCPRegistryConfig(servers={"mock_echo": server_cfg})

    async with MCPClientManager(registry) as manager:
        conn = await manager.get_connection("mock_echo")
        tools = await conn.list_tools()

        echo_mcp = next(t for t in tools if t.name == "echo")
        add_mcp = next(t for t in tools if t.name == "add")

        # Convert to LangGraph StructuredTool
        echo_tool = adapt_mcp_tool_to_langgraph(echo_mcp, manager, "mock_echo")
        add_tool = adapt_mcp_tool_to_langgraph(add_mcp, manager, "mock_echo")

        # Check metadata
        assert echo_tool.name == "echo"
        assert "Echoes back" in echo_tool.description
        assert "message" in echo_tool.args_schema.model_fields

        assert add_tool.name == "add"
        assert "a" in add_tool.args_schema.model_fields
        assert "b" in add_tool.args_schema.model_fields

        # Test asynchronous ainvoke
        echo_output = await echo_tool.ainvoke({"message": "Hello from LangGraph!"})
        assert echo_output == "echo: Hello from LangGraph!"

        add_output = await add_tool.ainvoke({"a": 120, "b": 230})
        assert add_output == "350"


@pytest.mark.anyio
async def test_adapt_all_mcp_tools():
    """Verify batch discovery and adaptation of all tools across servers."""
    server_cfg = MCPServerConfig(
        command=sys.executable,
        args=[MOCK_SERVER_SCRIPT],
        timeout_seconds=10.0,
    )
    registry = MCPRegistryConfig(servers={"mock_echo": server_cfg})

    async with MCPClientManager(registry) as manager:
        adapted_tools = await adapt_all_mcp_tools(manager)
        assert len(adapted_tools) == 2
        tool_names = {t.name for t in adapted_tools}
        assert tool_names == {"echo", "add"}
