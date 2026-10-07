"""Mock MCP server used for automated testing of client manager and adapters."""

import sys
from mcp.server.fastmcp import FastMCP

server = FastMCP("TestEchoServer")


@server.tool()
def echo(message: str) -> str:
    """Echoes back the received message."""
    return f"echo: {message}"


@server.tool()
def add(a: int, b: int) -> int:
    """Adds two numbers together."""
    return a + b


if __name__ == "__main__":
    server.run(transport="stdio")
