# Requirements: Parallel Tool Calling

## Overview
Enable concurrent execution of multiple tool calls emitted by an LLM in a single response turn. Instead of executing tool calls sequentially in a blocking loop, an `AsyncToolDispatcher` dispatches independent tool calls concurrently using Python's native `asyncio`, enforces per-tool execution timeouts, isolates failures, and returns ordered results mapped to their respective `tool_call_id`s.

---

## 1. Scope

### In-Scope
- **Async-First Execution Engine**: Core dispatcher based on `asyncio.gather` with strict task isolation (`return_exceptions=True` pattern or structured task shielding).
- **Tool Signature Standard**: Require async call signatures (`async def call(...)` or `asyncio.to_thread` wrappers for sync primitives like `PythonExecutor`).
- **Resilient Partial Return**: Per-tool configurable timeout (default 30s). When a tool times out, raises an unhandled exception, or produces an error, it captures the error string as the tool output for that specific `tool_call_id` without cancelling or blocking sibling calls.
- **Order Preservation**: Maintain 1:1 mapping between incoming LLM `tool_call_id`s and outgoing tool execution result messages, ensuring API compliance with Anthropic, OpenAI, and Hugging Face specs.
- **Integration**: Pluggable dispatcher integrated into `DataAnalystAgent` (`projects/Agents/data_analyst/agent.py`) supporting async execution.
- **Zero-Token Hermetic Testing**: Comprehensive unit and integration test suite using `MockLLMClient` and simulated asynchronous/slow tools.

### Out-of-Scope
- Nested/pipelined dependent tool chaining within a single turn (e.g. tool B strictly needing output from tool A). Sequential turns in the ReAct loop already handle multi-turn dependency.
- Dynamic speculative tool execution (invoking tools before LLM completion finishes streaming).
- Distributed Celery/Redis queue dispatching (unnecessary overhead for in-process agent loops).

---

## 2. Decisions & Architectural Rationale

| Decision | Choice | Rationale |
| :--- | :--- | :--- |
| **Execution Model** | **Async-first (`asyncio`)** | Direct compatibility with existing `core/mcp/client.py` and modern async LLM clients. Sync tools (`PythonExecutor`, local file ops) are easily adapted using `asyncio.to_thread`. |
| **Error Handling** | **Resilient Partial Return** | If an LLM requests 3 tool calls (e.g. query database, fetch docs, ping API) and one times out or errors, the agent still receives 2 successful results and 1 error explanation. This allows the LLM to self-correct rather than crashing the whole turn. |
| **Timeout Policy** | **Per-Tool Enforced Limit (default 30s)** | Adheres to Workspace Agentic Rule #4 (Execution Safety). Wraps each tool task in `asyncio.wait_for(..., timeout=timeout)` to prevent indefinite hangs. |
| **State Tracking** | **Order-Preserving Result Accumulation** | Tool outputs are indexed by `tool_call_id` and formatted into `llm.add_tool_result(tool_call_id, name, result)` in deterministic sequence. |

---

## 3. Data & Contract Specifications

### Tool Registration Contract
```python
from typing import Protocol, Any, Dict

class AsyncTool(Protocol):
    name: str
    async def __call__(self, **kwargs: Any) -> str:
        ...
```

### Dispatch Input Shape (from `llm_clients.py`)
```python
[
    {"id": "call_abc123", "name": "execute_python", "input": {"code": "print(1)"}},
    {"id": "call_def456", "name": "execute_python", "input": {"code": "print(2)"}}
]
```

### Dispatch Output Shape
```python
[
    {"tool_call_id": "call_abc123", "name": "execute_python", "result": "Exit Code: 0\nSTDOUT:\n1\nSTDERR:\n", "success": True, "duration": 0.04},
    {"tool_call_id": "call_def456", "name": "execute_python", "result": "Exit Code: 0\nSTDOUT:\n2\nSTDERR:\n", "success": True, "duration": 0.05}
]
```

---

## 4. Constraints & Rules Compliance
- **Rule 1 (Hard Limits)**: Max loop threshold preserved in the ReAct loop.
- **Rule 4 (Execution Safety)**: Strict timeouts enforced on all async tool dispatches.
- **Rule 7 (Structured Outputs)**: Result objects follow standardized dataclass/dict schemas.
