"""Async Model Context Protocol (MCP) Client and Subprocess Lifecycle Manager."""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional
import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import mcp.types as mcp_types

from .config import MCPServerConfig, MCPRegistryConfig

logger = logging.getLogger(__name__)


class MCPServerConnection:
    """Manages an individual active connection to an MCP server over stdio."""

    def __init__(self, name: str, config: MCPServerConfig):
        self.name = name
        self.config = config
        self.session: Optional[ClientSession] = None
        self._exit_stack: Optional[AsyncExitStack] = None
        self._tools_cache: Optional[List[mcp_types.Tool]] = None

    @property
    def is_connected(self) -> bool:
        return self.session is not None

    async def connect(self) -> None:
        """Start the server subprocess and complete protocol initialization."""
        if self.is_connected:
            return

        params = StdioServerParameters(
            command=self.config.command,
            args=self.config.args,
            env=self.config.get_effective_env(),
            cwd=self.config.cwd,
        )

        logger.info(
            "Starting MCP server '%s' via subprocess: %s %s",
            self.name,
            self.config.command,
            " ".join(self.config.args),
        )

        stack = AsyncExitStack()
        try:
            read_stream, write_stream = await stack.enter_async_context(
                stdio_client(params)
            )
            session = await stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            with anyio.fail_after(self.config.timeout_seconds):
                await session.initialize()

            self.session = session
            self._exit_stack = stack
            logger.info("Successfully initialized MCP session for server '%s'", self.name)
        except Exception as e:
            logger.error("Failed to connect to MCP server '%s': %s", self.name, e)
            await stack.aclose()
            self.session = None
            self._exit_stack = None
            raise

    async def list_tools(self, refresh: bool = False) -> List[mcp_types.Tool]:
        """Fetch all tools exposed by this MCP server."""
        if not self.is_connected:
            await self.connect()

        if self._tools_cache is not None and not refresh:
            return self._tools_cache

        assert self.session is not None
        with anyio.fail_after(self.config.timeout_seconds):
            response = await self.session.list_tools()
            self._tools_cache = response.tools
            return self._tools_cache

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> mcp_types.CallToolResult:
        """Execute a tool on the remote server with timeout protection."""
        if not self.is_connected:
            await self.connect()

        effective_timeout = timeout or self.config.timeout_seconds
        assert self.session is not None
        logger.debug("Calling MCP tool '%s:%s' with args %s", self.name, tool_name, arguments)

        with anyio.fail_after(effective_timeout):
            result = await self.session.call_tool(tool_name, arguments=arguments)
            return result

    async def close(self) -> None:
        """Gracefully close the session and terminate the server subprocess."""
        if self._exit_stack:
            logger.info("Closing MCP server connection '%s'", self.name)
            try:
                await self._exit_stack.aclose()
            except Exception as e:
                logger.warning("Error during MCP server '%s' shutdown: %s", self.name, e)
            finally:
                self.session = None
                self._exit_stack = None
                self._tools_cache = None


class MCPClientManager:
    """Orchestrates connections to multiple MCP servers defined in an MCPRegistryConfig."""

    def __init__(self, registry: MCPRegistryConfig):
        self.registry = registry
        self.connections: Dict[str, MCPServerConnection] = {
            name: MCPServerConnection(name, cfg)
            for name, cfg in registry.servers.items()
            if cfg.enabled
        }

    async def __aenter__(self) -> MCPClientManager:
        await self.connect_all()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close_all()

    async def connect_all(self) -> None:
        """Establish connections to all enabled servers."""
        for name, conn in self.connections.items():
            await conn.connect()

    async def get_connection(self, server_name: str) -> MCPServerConnection:
        """Retrieve connection for a specific server name."""
        if server_name not in self.connections:
            raise KeyError(f"MCP Server '{server_name}' is not configured or enabled.")
        conn = self.connections[server_name]
        if not conn.is_connected:
            await conn.connect()
        return conn

    async def list_all_tools(self) -> Dict[str, List[mcp_types.Tool]]:
        """List tools across all connected servers grouped by server name."""
        all_tools: Dict[str, List[mcp_types.Tool]] = {}
        for name, conn in self.connections.items():
            all_tools[name] = await conn.list_tools()
        return all_tools

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> mcp_types.CallToolResult:
        """Call a specific tool on a designated server."""
        conn = await self.get_connection(server_name)
        return await conn.call_tool(tool_name, arguments, timeout=timeout)

    async def close_all(self) -> None:
        """Close all active server connections and terminate subprocesses."""
        for name, conn in self.connections.items():
            await conn.close()
