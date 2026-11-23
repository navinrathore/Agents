"""
Selective Pointer Query Tools for Agent Workflows.

Provides specialized inspection tools (line slicing, JSON path extraction, and regex grep)
allowing agents to selectively inspect offloaded payloads stored outside context
without reloading the full raw volume.
"""

import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from core.output_guard import BasePayloadStore, LocalDiskPayloadStore

# (clean_id, payload_content, error_message)
PayloadFetchResult = Tuple[str, Optional[str], Optional[str]]


def normalize_pointer_id(raw_id: str) -> str:
    """
    Cleans raw pointer ID string passed by an LLM.
    Handles 'pointer://ptr_xxx', 'file:///path/ptr_xxx.ext', or bare 'ptr_xxx'.
    """
    s = raw_id.strip()
    if s.startswith("pointer://"):
        s = s[len("pointer://"):]
    elif s.startswith("file://"):
        s = Path(s[len("file://"):]).stem
    elif "/" in s or "\\" in s:
        s = Path(s).stem

    # Remove file extensions like .txt, .json, .csv
    if s.endswith((".txt", ".json", ".csv", ".html")):
        s = Path(s).stem

    return s


class PointerToolSuite:
    """
    Encapsulates pointer query tools bound to a specific payload storage engine.
    Can register directly into an AsyncToolDispatcher and provide tool schemas.
    """

    def __init__(self, store: Optional[BasePayloadStore] = None, storage_dir: Optional[Union[str, Path]] = None):
        if store is not None:
            self.store = store
        else:
            path = storage_dir or "vault/pointers"
            self.store = LocalDiskPayloadStore(storage_dir=path)

    def _get_payload(self, pointer_id: str) -> PayloadFetchResult:
        clean_id = normalize_pointer_id(pointer_id)
        if not self.store.exists(clean_id):
            return clean_id, None, f"Error: Pointer ID '{pointer_id}' (normalized: '{clean_id}') not found in storage."
        payload = self.store.retrieve(clean_id)
        if payload is None:
            return clean_id, None, f"Error: Failed to retrieve payload for pointer ID '{clean_id}'."
        return clean_id, payload, None

    def read_pointer_slice(
        self,
        pointer_id: str,
        start_line: int = 1,
        end_line: Optional[int] = None,
        max_lines: int = 100,
    ) -> str:
        """
        Reads a paginated range of lines from an offloaded pointer artifact.
        
        Args:
            pointer_id: The ID of the offloaded artifact (e.g., 'ptr_8f3b2a1c9e').
            start_line: 1-indexed starting line number (default: 1).
            end_line: 1-indexed ending line number (inclusive). Defaults to start_line + max_lines - 1.
            max_lines: Maximum number of lines to return per call (default: 100, hard cap: 500).
        """
        clean_id, payload, err = self._get_payload(pointer_id)
        if err:
            return err

        lines = payload.splitlines()
        total_lines = len(lines)

        if total_lines == 0:
            return f"[Pointer '{clean_id}' is empty (0 lines)]"

        # Sanitize arguments
        start = max(1, start_line)
        capped_max = min(max(1, max_lines), 500)

        if end_line is None:
            end = min(total_lines, start + capped_max - 1)
        else:
            end = max(start, end_line)
            if (end - start + 1) > capped_max:
                end = start + capped_max - 1

        if start > total_lines:
            return (
                f"Error: start_line {start} exceeds total lines ({total_lines}) "
                f"for pointer '{clean_id}'."
            )

        # Slice lines (0-indexed)
        selected_lines = lines[start - 1 : end]
        output = [
            f"--- SLICE: Lines {start}-{end} of {total_lines:,} from {clean_id} ---"
        ]
        for idx, line in enumerate(selected_lines, start=start):
            output.append(f"{idx:5d} | {line}")

        if end < total_lines:
            output.append(f"--- [More lines available ({total_lines - end:,} remaining). Use start_line={end + 1} to continue] ---")
        else:
            output.append("--- [END OF ARTIFACT] ---")

        return "\n".join(output)

    def grep_pointer(
        self,
        pointer_id: str,
        pattern: str,
        max_matches: int = 20,
        context_lines: int = 0,
        ignore_case: bool = True,
    ) -> str:
        """
        Searches an offloaded artifact for regex or substring matches with line numbers.
        
        Args:
            pointer_id: The ID of the offloaded artifact.
            pattern: Regular expression or substring pattern to search for.
            max_matches: Maximum number of matching lines to return (default: 20, cap: 100).
            context_lines: Number of surrounding context lines to include before and after each match (default: 0).
            ignore_case: Whether to perform case-insensitive match (default: True).
        """
        clean_id, payload, err = self._get_payload(pointer_id)
        if err:
            return err

        if not pattern:
            return "Error: Search pattern must not be empty."

        flags = re.IGNORECASE if ignore_case else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return f"Error: Invalid regex pattern '{pattern}': {str(e)}"

        lines = payload.splitlines()
        total_lines = len(lines)
        capped_matches = min(max(1, max_matches), 100)
        context = min(max(0, context_lines), 5)

        matches_found = 0
        output_blocks = []
        visited_lines = set()

        for idx, line in enumerate(lines, start=1):
            if regex.search(line):
                matches_found += 1
                if matches_found <= capped_matches:
                    start_ctx = max(1, idx - context)
                    end_ctx = min(total_lines, idx + context)
                    
                    block = []
                    for c_idx in range(start_ctx, end_ctx + 1):
                        if c_idx not in visited_lines:
                            marker = ">>>" if c_idx == idx else "   "
                            block.append(f"{marker} {c_idx:5d} | {lines[c_idx - 1]}")
                            visited_lines.add(c_idx)
                    if block:
                        output_blocks.append("\n".join(block))

        if matches_found == 0:
            return f"No matches found for pattern '{pattern}' in pointer '{clean_id}' ({total_lines:,} lines scanned)."

        header = [
            f"--- GREP RESULTS: {matches_found:,} match(es) for '{pattern}' in {clean_id} ---"
        ]
        header.extend(output_blocks)

        if matches_found > capped_matches:
            header.append(
                f"--- [Showing first {capped_matches} matches of {matches_found:,}. Refine pattern or increase max_matches] ---"
            )

        return "\n\n".join(header)

    def query_pointer_json(
        self,
        pointer_id: str,
        json_path: str = "",
        max_output_chars: int = 4000,
    ) -> str:
        """
        Parses an offloaded JSON artifact and extracts a nested value by dot/bracket path.
        
        Args:
            pointer_id: The ID of the offloaded JSON artifact.
            json_path: Dot/bracket path (e.g., 'data.users[0].email', 'items.total', or '' for root summary).
            max_output_chars: Maximum character limit for returned JSON string (default: 4000).
        """
        clean_id, payload, err = self._get_payload(pointer_id)
        if err:
            return err

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            return f"Error: Pointer '{clean_id}' does not contain valid JSON: {str(exc)}"

        target = data
        path_str = json_path.strip()

        if path_str and path_str not in ("$", ".", "root"):
            # Normalize bracket notation: 'users[0]' -> 'users.0'
            normalized = re.sub(r"\[(\d+)\]", r".\1", path_str)
            tokens = [t for t in normalized.split(".") if t]

            curr = data
            for token in tokens:
                if isinstance(curr, dict):
                    if token in curr:
                        curr = curr[token]
                    else:
                        available = list(curr.keys())[:10]
                        return (
                            f"Error: Key '{token}' not found at path '{path_str}'. "
                            f"Available keys at this level: {available}"
                        )
                elif isinstance(curr, list):
                    try:
                        idx = int(token)
                        if 0 <= idx < len(curr):
                            curr = curr[idx]
                        else:
                            return (
                                f"Error: Index '{idx}' out of bounds at path '{path_str}'. "
                                f"Array length is {len(curr)}."
                            )
                    except ValueError:
                        return f"Error: Cannot access property '{token}' on a JSON array at path '{path_str}'."
                else:
                    return f"Error: Cannot navigate into primitive value ({type(curr).__name__}) with token '{token}'."
            target = curr

        # Format target
        if isinstance(target, (dict, list)):
            dumped = json.dumps(target, indent=2)
            if len(dumped) > max_output_chars:
                if isinstance(target, dict):
                    keys_summary = {k: type(v).__name__ for k, v in list(target.items())[:20]}
                    dumped = (
                        f"[JSON Object too large ({len(dumped):,} chars). "
                        f"Showing top {len(keys_summary)} keys and types]:\n"
                        + json.dumps(keys_summary, indent=2)
                    )
                elif isinstance(target, list):
                    dumped = (
                        f"[JSON Array too large ({len(dumped):,} chars, {len(target)} items). "
                        f"Showing first 2 items]:\n"
                        + json.dumps(target[:2], indent=2)
                    )
            return dumped
        else:
            return str(target)

    def register_tools(self, dispatcher: Any) -> None:
        """
        Registers read_pointer_slice, grep_pointer, and query_pointer_json
        directly with an AsyncToolDispatcher.
        """
        dispatcher.register_tool("read_pointer_slice", self.read_pointer_slice)
        dispatcher.register_tool("grep_pointer", self.grep_pointer)
        dispatcher.register_tool("query_pointer_json", self.query_pointer_json)

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        Returns JSON schema definitions for the three pointer inspection tools,
        formatted for LLM tool calling (OpenAI/Anthropic compatible).
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "read_pointer_slice",
                    "description": "Reads a paginated line range from an offloaded pointer artifact stored outside context.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pointer_id": {
                                "type": "string",
                                "description": "The ID or URI of the offloaded artifact (e.g. 'ptr_8f3b2a1c9e').",
                            },
                            "start_line": {
                                "type": "integer",
                                "description": "1-indexed starting line number (default: 1).",
                                "default": 1,
                            },
                            "end_line": {
                                "type": "integer",
                                "description": "1-indexed ending line number (inclusive).",
                            },
                            "max_lines": {
                                "type": "integer",
                                "description": "Maximum number of lines to return (default: 100, max: 500).",
                                "default": 100,
                            },
                        },
                        "required": ["pointer_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "grep_pointer",
                    "description": "Searches an offloaded pointer artifact for regex or substring matches with line numbers and context.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pointer_id": {
                                "type": "string",
                                "description": "The ID or URI of the offloaded artifact.",
                            },
                            "pattern": {
                                "type": "string",
                                "description": "Regular expression or substring to search for.",
                            },
                            "max_matches": {
                                "type": "integer",
                                "description": "Maximum matching lines to return (default: 20, max: 100).",
                                "default": 20,
                            },
                            "context_lines": {
                                "type": "integer",
                                "description": "Surrounding context lines to include before and after each match (default: 0).",
                                "default": 0,
                            },
                            "ignore_case": {
                                "type": "boolean",
                                "description": "Case-insensitive matching (default: True).",
                                "default": True,
                            },
                        },
                        "required": ["pointer_id", "pattern"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "query_pointer_json",
                    "description": "Parses an offloaded JSON pointer artifact and extracts a nested value by dot/bracket path.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pointer_id": {
                                "type": "string",
                                "description": "The ID or URI of the offloaded JSON artifact.",
                            },
                            "json_path": {
                                "type": "string",
                                "description": "Path expression (e.g. 'data.users[0].name', 'metrics.latency', or '' for root summary).",
                                "default": "",
                            },
                        },
                        "required": ["pointer_id"],
                    },
                },
            },
        ]
