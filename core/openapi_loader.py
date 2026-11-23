"""
Lightweight OpenAPI Spec Tool Loader for Agentic Systems.
Designed for educational clarity and rapid experimentation:
1. Ingests OpenAPI 3.0/3.1 specs (JSON/YAML or Python dict).
2. Converts endpoints to standard LLM tool schemas (OpenAI / Anthropic format).
3. Supports two competing architectural strategies:
   - "direct": Generates an explicit 1:1 tool per endpoint (high accuracy, higher token cost).
   - "generic": Generates a single compact meta-tool `call_api` (near-zero token cost).
4. Supports "read_only" guardrail filtering (only exposes GET operations).
5. Provides a "dry_run" execution mode to inspect generated HTTP calls offline.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional
import yaml


class OpenAPIToolLoader:
    """
    Lightweight parser and tool generator for OpenAPI specifications.
    """

    def __init__(self, spec_data: Dict[str, Any], base_url: Optional[str] = None):
        self.spec = spec_data
        # Resolve base URL from spec servers or fallback
        servers = self.spec.get("servers", [])
        self.base_url = (
            base_url
            or (servers[0].get("url") if servers else "https://api.example.com")
        ).rstrip("/")
        self.operations: Dict[str, Dict[str, Any]] = self._parse_operations()

    @classmethod
    def from_text(cls, content: str, base_url: Optional[str] = None) -> OpenAPIToolLoader:
        """Loads spec from a JSON or YAML string."""
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            data = yaml.safe_load(content)
        return cls(data, base_url=base_url)

    def _parse_operations(self) -> Dict[str, Dict[str, Any]]:
        """Parses paths and methods into normalized operation descriptors."""
        ops = {}
        paths = self.spec.get("paths", {})

        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue

            for method in ("get", "post", "put", "delete", "patch"):
                if method not in path_item:
                    continue

                op_data = path_item[method]
                # Determine clean operation identifier
                op_id = op_data.get("operationId")
                if not op_id:
                    clean_path = re.sub(r"[{}/]", "_", path).strip("_")
                    op_id = f"{method}_{clean_path}"

                # Extract summary and parameters
                summary = op_data.get("summary") or op_data.get("description") or f"{method.upper()} {path}"
                parameters = op_data.get("parameters", [])

                # Extract requestBody schema properties if present
                body_schema = {}
                request_body = op_data.get("requestBody", {})
                content_types = request_body.get("content", {})
                json_content = content_types.get("application/json", {})
                if "schema" in json_content:
                    body_schema = json_content["schema"]

                ops[op_id] = {
                    "operation_id": op_id,
                    "method": method.upper(),
                    "path": path,
                    "summary": summary,
                    "tags": op_data.get("tags", []),
                    "parameters": parameters,
                    "body_schema": body_schema,
                }

        return ops

    def generate_tools(
        self,
        strategy: str = "direct",
        read_only: bool = False,
        tag_filter: Optional[List[str]] = None,
        tool_format: str = "openai",
    ) -> List[Dict[str, Any]]:
        """
        Generates tool definitions for the LLM.
        - strategy: 'direct' (1:1 endpoint tools) or 'generic' (single call_api meta-tool).
        - read_only: if True, filters out mutating operations (POST, PUT, DELETE, PATCH).
        - tag_filter: optional list of OpenAPI tags to include.
        - tool_format: 'openai' (type=function) or 'anthropic' (name, description, input_schema).
        """
        # Filter operations
        filtered_ops = {}
        for op_id, op in self.operations.items():
            if read_only and op["method"] != "GET":
                continue
            if tag_filter and not any(tag in op["tags"] for tag in tag_filter):
                continue
            filtered_ops[op_id] = op

        if strategy == "generic":
            return [self._build_generic_meta_tool(filtered_ops, tool_format=tool_format)]
        else:
            return [
                self._build_direct_tool(op, tool_format=tool_format)
                for op in filtered_ops.values()
            ]

    def _build_direct_tool(self, op: Dict[str, Any], tool_format: str = "openai") -> Dict[str, Any]:
        """Converts an individual OpenAPI operation into a typed tool schema."""
        properties: Dict[str, Any] = {}
        required: List[str] = []

        # Map path and query parameters
        for param in op.get("parameters", []):
            p_name = param.get("name")
            p_schema = param.get("schema", {"type": "string"})
            p_desc = param.get("description", f"Parameter in {param.get('in', 'query')}")
            properties[p_name] = {
                "type": p_schema.get("type", "string"),
                "description": f"[{param.get('in', 'query')}] {p_desc}",
            }
            if param.get("required", False):
                required.append(p_name)

        # Merge request body properties if present
        body_schema = op.get("body_schema", {})
        if body_schema.get("type") == "object":
            for b_prop, b_spec in body_schema.get("properties", {}).items():
                properties[b_prop] = {
                    "type": b_spec.get("type", "string"),
                    "description": b_spec.get("description", "[body] Request body field"),
                }
            required.extend(body_schema.get("required", []))

        input_schema = {
            "type": "object",
            "properties": properties,
            "required": list(set(required)),
        }

        desc = f"[{op['method']}] {op['summary']} (Route: {op['path']})"

        if tool_format == "anthropic":
            return {
                "name": op["operation_id"],
                "description": desc,
                "input_schema": input_schema,
            }
        else:
            return {
                "type": "function",
                "function": {
                    "name": op["operation_id"],
                    "description": desc,
                    "parameters": input_schema,
                },
            }

    def _build_generic_meta_tool(
        self,
        operations: Dict[str, Dict[str, Any]],
        tool_format: str = "openai",
    ) -> Dict[str, Any]:
        """
        Creates a single compact meta-tool that accepts route path, method, and parameters.
        Includes a summary catalog in the description to minimize token overhead.
        """
        routes_summary = "\n".join([
            f"- {op['method']} {op['path']} ({op['operation_id']}): {op['summary']}"
            for op in operations.values()
        ])

        description = (
            "Generic API caller for OpenAPI endpoints.\n"
            f"Available Routes:\n{routes_summary}"
        )

        parameters = {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The exact API route path (e.g. '/pets' or '/pets/{id}')",
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                    "description": "HTTP method to use",
                },
                "params": {
                    "type": "object",
                    "description": "Query or path parameters to include in the request",
                },
                "body": {
                    "type": "object",
                    "description": "JSON request body payload for POST/PUT/PATCH requests",
                },
            },
            "required": ["path", "method"],
        }

        if tool_format == "anthropic":
            return {
                "name": "call_api",
                "description": description,
                "input_schema": parameters,
            }
        else:
            return {
                "type": "function",
                "function": {
                    "name": "call_api",
                    "description": description,
                    "parameters": parameters,
                },
            }

    def prepare_request(
        self,
        operation_id: Optional[str] = None,
        path: Optional[str] = None,
        method: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Prepares a structured HTTP request descriptor.
        Interpolates path parameters (e.g. `/users/{id}`), separates query params,
        and constructs headers and body.
        """
        params = dict(params or {})
        params.update(kwargs)

        op = None
        if operation_id and operation_id in self.operations:
            op = self.operations[operation_id]
            target_path = op["path"]
            target_method = op["method"]
        elif path and method:
            target_path = path
            target_method = method.upper()
        else:
            raise ValueError("Must provide either valid operation_id or path and method.")

        # Interpolate path parameters like {user_id}
        url_path = target_path
        query_params = {}
        for key, val in params.items():
            placeholder = f"{{{key}}}"
            if placeholder in url_path:
                url_path = url_path.replace(placeholder, str(val))
            else:
                query_params[key] = val

        full_url = f"{self.base_url}{url_path}"

        return {
            "method": target_method,
            "url": full_url,
            "query_params": query_params,
            "body": body,
            "headers": {"Content-Type": "application/json", "Accept": "application/json"},
        }

    def execute_dry_run(self, **kwargs: Any) -> str:
        """
        Light-mode execution simulator: Generates the full HTTP request contract
        and returns a clean JSON summary without executing network calls.
        """
        req = self.prepare_request(**kwargs)
        return json.dumps(
            {
                "status": "dry_run_success",
                "simulated_request": req,
                "simulated_response": {
                    "status_code": 200,
                    "message": f"Successfully prepared {req['method']} request to {req['url']}",
                },
            },
            indent=2,
        )

    def register_into_dispatcher(
        self,
        dispatcher: Any,
        strategy: str = "direct",
        read_only: bool = False,
        tag_filter: Optional[List[str]] = None,
        dry_run: bool = True,
    ) -> List[str]:
        """
        Registers generated OpenAPI tools directly into an AsyncToolDispatcher.
        Returns a list of registered tool names.
        """
        registered = []

        if strategy == "generic":
            async def _generic_tool(path: str, method: str, params: Optional[dict] = None, body: Optional[dict] = None) -> str:
                if dry_run:
                    return self.execute_dry_run(path=path, method=method, params=params, body=body)
                return self.execute_dry_run(path=path, method=method, params=params, body=body)

            dispatcher.register_tool("call_api", _generic_tool, is_async=True)
            registered.append("call_api")
        else:
            for op_id, op in self.operations.items():
                if read_only and op["method"] != "GET":
                    continue
                if tag_filter and not any(tag in op["tags"] for tag in tag_filter):
                    continue

                def _make_handler(target_op_id: str) -> Callable[..., Any]:
                    async def _handler(**call_kwargs: Any) -> str:
                        return self.execute_dry_run(operation_id=target_op_id, **call_kwargs)
                    return _handler

                is_sequential = op["method"] != "GET"
                dispatcher.register_tool(
                    op_id,
                    _make_handler(op_id),
                    is_async=True,
                    sequential_only=is_sequential,
                )
                registered.append(op_id)

        return registered
