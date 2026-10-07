"""Declarative configuration models and YAML parser for MCP servers."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field


def _expand_env_vars(value: Any) -> Any:
    """Recursively expand environment variables in strings, lists, and dicts."""
    if isinstance(value, str):
        # Matches ${VAR_NAME} or $VAR_NAME
        pattern = re.compile(r"\$(?:(\w+)|\{([^}]+)\})")

        def _replace(match: re.Match) -> str:
            var_name = match.group(1) or match.group(2)
            return os.environ.get(var_name, "")

        return pattern.sub(_replace, value)
    elif isinstance(value, list):
        return [_expand_env_vars(v) for v in value]
    elif isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    return value


class MCPServerConfig(BaseModel):
    """Specification for a single Model Context Protocol (MCP) server."""

    command: str = Field(..., description="Executable command to run (e.g. 'npx', 'python', 'docker')")
    args: List[str] = Field(default_factory=list, description="Command line arguments passed to the server")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables injected into subprocess")
    cwd: Optional[str] = Field(None, description="Working directory for the subprocess")
    enabled: bool = Field(True, description="Whether this server is active")
    timeout_seconds: float = Field(30.0, description="Default timeout in seconds for tool calls on this server")

    def get_effective_env(self) -> Dict[str, str]:
        """Merge system environment with configured server environment variables."""
        merged = os.environ.copy()
        for k, v in self.env.items():
            merged[k] = str(v)
        return merged


class MCPRegistryConfig(BaseModel):
    """Registry holding one or more MCP server configurations."""

    servers: Dict[str, MCPServerConfig] = Field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MCPRegistryConfig:
        """Create configuration registry from raw dictionary with env variable expansion."""
        expanded = _expand_env_vars(data)
        raw_servers = expanded.get("servers", expanded)
        servers = {}
        for name, s_cfg in raw_servers.items():
            if isinstance(s_cfg, dict):
                servers[name] = MCPServerConfig.model_validate(s_cfg)
        return cls(servers=servers)

    @classmethod
    def from_yaml(cls, path_or_stream: str | Path) -> MCPRegistryConfig:
        """Load and parse registry configuration from a YAML file or string."""
        if isinstance(path_or_stream, (str, Path)) and os.path.exists(str(path_or_stream)):
            with open(path_or_stream, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        else:
            data = yaml.safe_load(str(path_or_stream)) or {}
        return cls.from_dict(data)
