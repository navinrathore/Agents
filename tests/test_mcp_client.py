"""Unit and integration tests for MCPClientManager and MCPServerConfig."""

import os
import sys
from pathlib import Path
import pytest
import anyio

# Ensure projects/Agents is on sys.path
AGENTS_ROOT = Path(__file__).resolve().parent.parent
if str(AGENTS_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENTS_ROOT))

from core.mcp.config import MCPServerConfig, MCPRegistryConfig
from core.mcp.client import MCPClientManager, MCPServerConnection


@pytest.fixture
def anyio_backend():
    return "asyncio"


MOCK_SERVER_SCRIPT = str(Path(__file__).resolve().parent / "mock_mcp_server.py")



def test_mcp_config_env_expansion(monkeypatch):
    """Test that environment variables are expanded within YAML configurations."""
    monkeypatch.setenv("TEST_APP_TOKEN", "secret_token_123")
    monkeypatch.setenv("TEST_TIMEOUT", "45")

    yaml_content = """
    servers:
      echo_server:
        command: "python"
        args: ["-m", "mock_server", "--token", "${TEST_APP_TOKEN}"]
        env:
          AUTH: "$TEST_APP_TOKEN"
        timeout_seconds: 45.0
    """
    registry = MCPRegistryConfig.from_yaml(yaml_content)
    assert "echo_server" in registry.servers
    server = registry.servers["echo_server"]
    assert server.args == ["-m", "mock_server", "--token", "secret_token_123"]
    assert server.env["AUTH"] == "secret_token_123"
    assert server.timeout_seconds == 45.0


@pytest.mark.anyio
async def test_mcp_client_connect_and_list_tools():
    """Test starting the mock MCP server over stdio and discovering tools."""
    server_cfg = MCPServerConfig(
        command=sys.executable,
        args=[MOCK_SERVER_SCRIPT],
        timeout_seconds=10.0,
    )
    registry = MCPRegistryConfig(servers={"mock_echo": server_cfg})

    async with MCPClientManager(registry) as manager:
        conn = await manager.get_connection("mock_echo")
        assert conn.is_connected

        tools = await conn.list_tools()
        tool_names = [t.name for t in tools]
        assert "echo" in tool_names
        assert "add" in tool_names

        # Validate docstring passed through
        echo_tool = next(t for t in tools if t.name == "echo")
        assert "Echoes back" in echo_tool.description


@pytest.mark.anyio
async def test_mcp_client_call_tool():
    """Test executing tools on the remote MCP server via stdio transport."""
    server_cfg = MCPServerConfig(
        command=sys.executable,
        args=[MOCK_SERVER_SCRIPT],
        timeout_seconds=10.0,
    )
    registry = MCPRegistryConfig(servers={"mock_echo": server_cfg})

    async with MCPClientManager(registry) as manager:
        # Call echo tool
        echo_res = await manager.call_tool(
            "mock_echo", "echo", {"message": "Agentic AI Test"}
        )
        assert not echo_res.isError
        assert len(echo_res.content) > 0
        assert "echo: Agentic AI Test" in echo_res.content[0].text

        # Call add tool
        add_res = await manager.call_tool("mock_echo", "add", {"a": 15, "b": 27})
        assert not add_res.isError
        assert "42" in add_res.content[0].text


@pytest.mark.anyio
async def test_mcp_client_clean_teardown():
    """Test that subprocesses are properly terminated when closed."""
    server_cfg = MCPServerConfig(
        command=sys.executable,
        args=[MOCK_SERVER_SCRIPT],
        timeout_seconds=10.0,
    )
    registry = MCPRegistryConfig(servers={"mock_echo": server_cfg})

    manager = MCPClientManager(registry)
    await manager.connect_all()
    conn = await manager.get_connection("mock_echo")
    assert conn.is_connected

    # Close manager
    await manager.close_all()
    assert not conn.is_connected
    assert conn.session is None


@pytest.mark.anyio
async def test_mcp_client_unknown_server():
    """Test requesting a server that is not configured raises KeyError."""
    registry = MCPRegistryConfig(servers={})
    manager = MCPClientManager(registry)
    with pytest.raises(KeyError, match="not configured"):
        await manager.get_connection("non_existent")
