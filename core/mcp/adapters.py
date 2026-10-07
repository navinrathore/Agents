"""Adapters converting Model Context Protocol (MCP) tool definitions into LangGraph/LangChain StructuredTools."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field, create_model
from langchain_core.tools import StructuredTool
import mcp.types as mcp_types

from .client import MCPClientManager

logger = logging.getLogger(__name__)


def _map_json_type_to_python(prop_schema: Dict[str, Any]) -> Type[Any]:
    """Map JSON Schema primitive types to Python types."""
    json_type = prop_schema.get("type")
    if json_type == "string":
        return str
    elif json_type == "integer":
        return int
    elif json_type == "number":
        return float
    elif json_type == "boolean":
        return bool
    elif json_type == "array":
        return list
    elif json_type == "object":
        return dict
    return Any


def json_schema_to_pydantic_model(model_name: str, schema: Optional[Dict[str, Any]]) -> Type[BaseModel]:
    """Convert an MCP tool's JSON Schema inputSchema to a dynamic Pydantic BaseModel."""
    if not schema or not isinstance(schema, dict):
        return create_model(model_name)

    properties: Dict[str, Any] = schema.get("properties", {})
    required_fields = set(schema.get("required", []))

    field_definitions: Dict[str, Any] = {}
    for prop_name, prop_spec in properties.items():
        if not isinstance(prop_spec, dict):
            prop_spec = {}

        py_type = _map_json_type_to_python(prop_spec)
        description = prop_spec.get("description")

        if prop_name in required_fields:
            field_definitions[prop_name] = (
                py_type,
                Field(..., description=description),
            )
        else:
            default_val = prop_spec.get("default", None)
            field_definitions[prop_name] = (
                Optional[py_type],
                Field(default=default_val, description=description),
            )

    return create_model(model_name, **field_definitions)


def format_mcp_result(result: mcp_types.CallToolResult) -> str:
    """Format CallToolResult content blocks into a single consolidated string output."""
    output_parts: List[str] = []
    for block in result.content:
        if isinstance(block, mcp_types.TextContent):
            output_parts.append(block.text)
        elif hasattr(block, "text"):
            output_parts.append(getattr(block, "text"))
        else:
            output_parts.append(str(block))

    combined = "\n".join(output_parts) if output_parts else "Success"
    if result.isError:
        return f"[ERROR] {combined}"
    return combined


def _run_sync(coro: Any) -> Any:
    """Safely execute an asynchronous coroutine from a synchronous context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Inside an existing running event loop; run via thread pool to prevent deadlock
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


def adapt_mcp_tool_to_langgraph(
    mcp_tool: mcp_types.Tool,
    client_manager: MCPClientManager,
    server_name: str,
) -> StructuredTool:
    """Transform an individual MCP Tool definition into a LangGraph-compatible StructuredTool."""
    sanitized_name = "".join(part.capitalize() for part in mcp_tool.name.split("_"))
    model_name = f"{sanitized_name}Args"
    args_model = json_schema_to_pydantic_model(model_name, mcp_tool.inputSchema)

    description = (
        mcp_tool.description
        or f"MCP tool '{mcp_tool.name}' from server '{server_name}'"
    )

    async def _coroutine(**kwargs: Any) -> str:
        res = await client_manager.call_tool(server_name, mcp_tool.name, kwargs)
        return format_mcp_result(res)

    def _sync_func(**kwargs: Any) -> str:
        return _run_sync(_coroutine(**kwargs))

    return StructuredTool(
        name=mcp_tool.name,
        description=description,
        args_schema=args_model,
        func=_sync_func,
        coroutine=_coroutine,
    )


async def adapt_all_mcp_tools(client_manager: MCPClientManager) -> List[StructuredTool]:
    """Discover all tools across all configured MCP servers and adapt them into StructuredTools."""
    structured_tools: List[StructuredTool] = []
    tools_by_server = await client_manager.list_all_tools()
    for server_name, tools in tools_by_server.items():
        for tool in tools:
            st = adapt_mcp_tool_to_langgraph(tool, client_manager, server_name)
            structured_tools.append(st)
    return structured_tools
