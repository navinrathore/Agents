# Validation Specification: Parallel Tool Calling

## Automated Verification Strategy

All verification must run hermetically in the existing virtual environment without external API calls or token burn.

### 1. Test Command
```bash
/home/navin/work/AI/.venv/bin/pytest projects/Agents/tests/test_tool_dispatcher.py projects/Agents/tests/test_agent_parallel_execution.py -v
```

### 2. Required Test Assertions

#### Core Dispatcher Tests (`test_tool_dispatcher.py`)
- **Concurrence & Wall-Clock Speedup**:
  - Dispatch 3 tools each sleeping for 0.2s.
  - Assert total elapsed time is $< 0.35s$ (demonstrating true concurrent fan-out, not $0.6s$).
- **Resilient Partial Return (Failure Isolation)**:
  - Dispatch tool A (returns `"success"`) and tool B (raises `RuntimeError("database offline")`).
  - Assert dispatch returns 2 results.
  - Tool A has `success == True` with result `"success"`.
  - Tool B has `success == False` with result containing `"Error: database offline"`.
- **Per-Tool Timeout**:
  - Dispatch tool A (sleeps 0.05s) and tool B (sleeps 1.0s) with `timeout=0.2s`.
  - Assert tool A succeeds.
  - Assert tool B fails with `"Error: Tool execution timed out after 0.2s"`.
- **Order Preservation**:
  - Dispatch 5 tools with varying sleep times (e.g. tool 1 sleeps 0.2s, tool 2 sleeps 0.01s).
  - Assert returned result list strictly preserves original input order: `[call_1, call_2, call_3, call_4, call_5]`.
- **Unregistered Tool Handling**:
  - Dispatch unknown tool name.
  - Assert returned result has `success == False` and error indicates unknown tool.

#### Agent Integration Tests (`test_agent_parallel_execution.py`)
- **Multi-Tool Turn Resolution**:
  - Configure `MockLLMClient` to emit 2 `tool_calls` in Turn 1:
    - Call 1: `execute_python(code="x = 10; print(x)")`
    - Call 2: `manage_checklist(action="add", task_name="clean_data")`
  - Assert `DataAnalystAgent` runs without errors.
  - Assert `agent.checklist` contains `"clean_data"`.
  - Assert `llm.add_tool_result` was invoked for both `tool_call_id`s before Turn 2.

---

## Manual / Interactive Verification
1. Run `DataAnalystAgent` in verbose mode with sample script executing two print operations.
2. Confirm console logs render concurrent execution timing:
   ```text
   🔄 [Parallel Dispatch]: Executing 2 tool calls concurrently...
   ⚙️ [Tool Complete]: execute_python (0.04s)
   ⚙️ [Tool Complete]: manage_checklist (0.001s)
   ```

---

## Definition of Done (DoD)
1. `AsyncToolDispatcher` is implemented in `projects/Agents/core/dispatcher.py`.
2. `DataAnalystAgent` supports both `run_async` and backwards-compatible `run`.
3. All new unit tests pass in `.venv/bin/pytest`.
4. All 43 pre-existing tests in `projects/Agents/tests/` continue to pass without regression.
5. Concept gap in [docs/agentic_concepts_master_extraction.md](file:///home/navin/work/AI/docs/agentic_concepts_master_extraction.md) is marked closed.
