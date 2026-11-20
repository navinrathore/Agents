# Implementation Plan: Parallel Tool Calling

## Overview
Break the parallel tool calling implementation into 3 distinct, independently testable phases.

---

## Phase 1: Core Async Tool Dispatcher (`core/dispatcher.py`)

### 1.1 Data Structures & Contracts
- [x] Define `ToolExecutionResult` dataclass (`tool_call_id: str`, `name: str`, `result: str`, `success: bool`, `error: Optional[str]`, `duration: float`).
- [x] Implement `AsyncToolDispatcher` class in `projects/Agents/core/dispatcher.py`.
- [x] Support registration of async tool callables (`register_tool(name: str, fn: Callable)`).
- [x] Implement sync-to-async adapter utility (`to_async_tool(fn: Callable)`) via `asyncio.to_thread` for legacy synchronous tools.

### 1.2 Concurrent Execution & Resilience Logic
- [x] Implement `async def dispatch(self, tool_calls: List[Dict[str, Any]], timeout: float = 30.0) -> List[ToolExecutionResult]`.
- [x] Use `asyncio.gather(*tasks, return_exceptions=True)` to ensure concurrent fan-out.
- [x] Enforce per-tool timeout using `asyncio.wait_for(task, timeout=tool_timeout)`.
- [x] Implement fault-tolerant error wrapper: Catch exceptions (TimeoutError, Exception) and convert them to formatted error output string for that specific `tool_call_id`.
- [x] Guarantee order preservation matching the input `tool_calls` list.

### 1.3 Phase 1 Unit Tests
- [x] Create `projects/Agents/tests/test_tool_dispatcher.py`.
- [x] Test concurrent speedup: Run two 0.5s mock tools in parallel and assert total execution time < 0.7s (proving concurrency vs. sequential 1.0s).
- [x] Test partial failure resilience: 1 failing tool + 1 successful tool -> both return results, failure does not propagate or crash sibling.
- [x] Test per-tool timeout: Tool taking 2.0s with timeout=0.2s raises `TimeoutError` cleanly caught and formatted as tool result.
- [x] Test unknown tool handling: Unregistered tool returns clear error result.

---

## Phase 2: Agent Loop Integration (`data_analyst/agent.py`)

### 2.1 Agent Asynchronous Support
- [x] Provide an async execution method `async def run_async(...)` in `DataAnalystAgent` (while keeping `run(...)` as a synchronous wrapper via `asyncio.run(...)` for backwards compatibility).
- [x] Initialize `AsyncToolDispatcher` within `DataAnalystAgent.__init__`.
- [x] Register `execute_python` (wrapped via `asyncio.to_thread(self.executor.execute)`) and `manage_checklist`.

### 2.2 Parallel Tool Dispatch in ReAct Loop
- [x] Replace the blocking `for tc in tool_calls:` execution block with `await self.dispatcher.dispatch(tool_calls)`.
- [x] Feed all concurrent tool results back into `self.llm.add_tool_result(...)` in preserved order.
- [x] Integrate `RepetitionDetector` check against the combined stderr of executed tools.

### 2.3 Phase 2 Integration Tests
- [x] Update or add integration test in `projects/Agents/tests/test_agent_parallel_execution.py`.
- [x] Use `MockLLMClient` configured to return multiple simultaneous `tool_calls` in a single response turn.
- [x] Verify that `DataAnalystAgent` processes all tool calls and feeds all tool result blocks to `llm.add_tool_result`.

---

## Phase 3: Edge Cases, MCP Async Tools & Documentation

### 3.1 MCP Client Tool Bridge
- [x] Register tools from `MCPClientManager` into `AsyncToolDispatcher` using their native `async def session.call_tool` signatures.
- [x] Verify that MCP tools and local Python execution tools can run concurrently within the exact same LLM turn.

### 3.2 Performance Benchmarking & Traceability
- [x] Add execution timing metrics to `ToolExecutionResult` and log concurrency diagnostics when `verbose=True`.
- [x] Benchmark comparison test: Verify wall-clock time reduction when multiple tools are dispatched simultaneously.
- [x] Configurable execution mode (`parallel_execution: True | False`) and concurrency capping via `asyncio.Semaphore(max_concurrency)`.
- [x] Declarative sequential barrier safety (`sequential_only=True`) for mutating/state-modifying tools.

### 3.3 Documentation & Gap Closure
- [x] Update [docs/agentic_concepts_master_extraction.md](file:///home/navin/work/AI/docs/agentic_concepts_master_extraction.md):
  - Mark `Parallel tool calling` as ✅ Implemented under Section 5.1 and the Gap Summary Matrix.
- [x] Update `projects/Agents/docs/backlog.md` with completed milestone.
