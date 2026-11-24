import asyncio
import os
import sys
import time
from pathlib import Path
import pytest

AGENTS_ROOT = str(Path(__file__).resolve().parent.parent)
if AGENTS_ROOT not in sys.path:
    sys.path.insert(0, AGENTS_ROOT)

from core.dispatcher import AsyncToolDispatcher, ToolExecutionResult, to_async_tool


@pytest.mark.anyio
async def test_dispatcher_concurrency_speedup():
    """
    Verify that multiple async tools execute concurrently rather than sequentially.
    3 tools sleeping 0.15s should finish in well under 0.35s (sequential would be 0.45s).
    """
    dispatcher = AsyncToolDispatcher(default_timeout=5.0)

    async def mock_sleep_tool(delay: float, value: str):
        await asyncio.sleep(delay)
        return f"done: {value}"

    dispatcher.register_tool("sleep_tool", mock_sleep_tool)

    tool_calls = [
        {"id": "call_1", "name": "sleep_tool", "input": {"delay": 0.15, "value": "A"}},
        {"id": "call_2", "name": "sleep_tool", "input": {"delay": 0.15, "value": "B"}},
        {"id": "call_3", "name": "sleep_tool", "input": {"delay": 0.15, "value": "C"}},
    ]

    start = time.perf_counter()
    results = await dispatcher.dispatch(tool_calls)
    elapsed = time.perf_counter() - start

    assert len(results) == 3
    assert elapsed < 0.35, f"Execution took {elapsed:.2f}s, expected concurrent fan-out < 0.35s"

    for idx, (res, val) in enumerate(zip(results, ["A", "B", "C"], strict=False)):
        assert res.success is True
        assert res.tool_call_id == f"call_{idx + 1}"
        assert res.result == f"done: {val}"
        assert res.error is None
        assert res.duration >= 0.14


@pytest.mark.anyio
async def test_dispatcher_order_preservation():
    """
    Verify that results match the exact sequence of incoming tool_calls, even if
    later tools finish significantly earlier than earlier tools.
    """
    dispatcher = AsyncToolDispatcher(default_timeout=5.0)

    async def mock_varied_tool(delay: float, name: str):
        await asyncio.sleep(delay)
        return f"result_{name}"

    dispatcher.register_tool("varied_tool", mock_varied_tool)

    # Call 1 is slowest (0.2s), Call 2 is medium (0.1s), Call 3 is fastest (0.01s)
    tool_calls = [
        {"id": "call_slow", "name": "varied_tool", "input": {"delay": 0.2, "name": "slow"}},
        {"id": "call_med", "name": "varied_tool", "input": {"delay": 0.1, "name": "med"}},
        {"id": "call_fast", "name": "varied_tool", "input": {"delay": 0.01, "name": "fast"}},
    ]

    results = await dispatcher.dispatch(tool_calls)

    assert len(results) == 3
    assert [r.tool_call_id for r in results] == ["call_slow", "call_med", "call_fast"]
    assert [r.result for r in results] == ["result_slow", "result_med", "result_fast"]


@pytest.mark.anyio
async def test_dispatcher_resilient_partial_return():
    """
    Verify that an unhandled exception in one tool does not fail or abort sibling tools.
    """
    dispatcher = AsyncToolDispatcher(default_timeout=5.0)

    async def good_tool(msg: str):
        await asyncio.sleep(0.05)
        return f"success: {msg}"

    async def bad_tool(msg: str):
        await asyncio.sleep(0.05)
        raise ValueError(f"Crash simulated: {msg}")

    dispatcher.register_tool("good_tool", good_tool)
    dispatcher.register_tool("bad_tool", bad_tool)

    tool_calls = [
        {"id": "call_good", "name": "good_tool", "input": {"msg": "hello"}},
        {"id": "call_bad", "name": "bad_tool", "input": {"msg": "boom"}},
    ]

    results = await dispatcher.dispatch(tool_calls)

    assert len(results) == 2

    # Good tool succeeded
    assert results[0].tool_call_id == "call_good"
    assert results[0].success is True
    assert results[0].result == "success: hello"
    assert results[0].error is None

    # Bad tool captured failure gracefully
    assert results[1].tool_call_id == "call_bad"
    assert results[1].success is False
    assert "ValueError: Crash simulated: boom" in results[1].result
    assert results[1].error is not None


@pytest.mark.anyio
async def test_dispatcher_per_tool_timeout():
    """
    Verify that a slow tool exceeding timeout fails cleanly without cancelling faster siblings.
    """
    dispatcher = AsyncToolDispatcher(default_timeout=5.0)

    async def quick_tool():
        await asyncio.sleep(0.02)
        return "quick_ok"

    async def hanging_tool():
        await asyncio.sleep(2.0)
        return "never_reached"

    dispatcher.register_tool("quick_tool", quick_tool)
    dispatcher.register_tool("hanging_tool", hanging_tool)

    tool_calls = [
        {"id": "call_quick", "name": "quick_tool", "input": {}},
        {"id": "call_hang", "name": "hanging_tool", "input": {}},
    ]

    # Set explicit tight timeout of 0.15s
    start = time.perf_counter()
    results = await dispatcher.dispatch(tool_calls, timeout=0.15)
    elapsed = time.perf_counter() - start

    assert len(results) == 2
    assert elapsed < 0.3  # Did not wait for the 2.0s hanging tool

    assert results[0].tool_call_id == "call_quick"
    assert results[0].success is True
    assert results[0].result == "quick_ok"

    assert results[1].tool_call_id == "call_hang"
    assert results[1].success is False
    assert "timed out after 0.15s" in results[1].result
    assert "timed out after 0.15s" in results[1].error


@pytest.mark.anyio
async def test_dispatcher_unknown_tool():
    """
    Verify unknown tool requests return a structured error result.
    """
    dispatcher = AsyncToolDispatcher()

    tool_calls = [
        {"id": "call_missing", "name": "non_existent_tool", "input": {"foo": "bar"}}
    ]

    results = await dispatcher.dispatch(tool_calls)
    assert len(results) == 1
    assert results[0].success is False
    assert "Unknown or unregistered tool 'non_existent_tool'" in results[0].result


@pytest.mark.anyio
async def test_dispatcher_sync_tool_adaptation():
    """
    Verify that synchronous functions are automatically adapted and run concurrently via to_async_tool.
    """
    dispatcher = AsyncToolDispatcher()

    def sync_compute(val: int) -> int:
        time.sleep(0.1)
        return val * 2

    # Registering normal synchronous function
    dispatcher.register_tool("compute", sync_compute)
    assert dispatcher.has_tool("compute")

    tool_calls = [
        {"id": "call_c1", "name": "compute", "input": {"val": 10}},
        {"id": "call_c2", "name": "compute", "input": {"val": 20}},
    ]

    start = time.perf_counter()
    results = await dispatcher.dispatch(tool_calls)
    elapsed = time.perf_counter() - start

    assert len(results) == 2
    assert elapsed < 0.25  # Ran concurrently on threads, not 0.3s+ sequentially
    assert results[0].result == "20"
    assert results[1].result == "40"
    assert results[0].success is True
    assert results[1].success is True


@pytest.mark.anyio
async def test_dispatcher_empty_tool_calls():
    """
    Dispatching empty tool call list returns empty list immediately.
    """
    dispatcher = AsyncToolDispatcher()
    results = await dispatcher.dispatch([])
    assert results == []


@pytest.mark.anyio
async def test_dispatcher_configurable_sequential_mode():
    """
    Verify that when parallel_execution=False, tools execute strictly sequentially.
    3 tools sleeping 0.1s sequentially should take >= 0.28s.
    """
    dispatcher = AsyncToolDispatcher(parallel_execution=False)

    execution_order = []

    async def step_tool(name: str):
        execution_order.append(f"start_{name}")
        await asyncio.sleep(0.1)
        execution_order.append(f"end_{name}")
        return f"result_{name}"

    dispatcher.register_tool("step_tool", step_tool)

    tool_calls = [
        {"id": "call_1", "name": "step_tool", "input": {"name": "1"}},
        {"id": "call_2", "name": "step_tool", "input": {"name": "2"}},
        {"id": "call_3", "name": "step_tool", "input": {"name": "3"}},
    ]

    start = time.perf_counter()
    results = await dispatcher.dispatch(tool_calls)
    elapsed = time.perf_counter() - start

    assert len(results) == 3
    assert elapsed >= 0.28, f"Expected sequential elapsed >= 0.28s, got {elapsed:.2f}s"
    assert execution_order == [
        "start_1", "end_1",
        "start_2", "end_2",
        "start_3", "end_3",
    ]


@pytest.mark.anyio
async def test_dispatcher_semaphore_max_concurrency_throttling():
    """
    Verify that max_concurrency caps the number of simultaneously active tasks.
    With max_concurrency=2, running 4 tasks of 0.1s must run in 2 waves (taking >= 0.18s).
    """
    dispatcher = AsyncToolDispatcher(parallel_execution=True, max_concurrency=2)

    active_concurrent_count = 0
    max_observed_concurrency = 0

    async def monitored_tool():
        nonlocal active_concurrent_count, max_observed_concurrency
        active_concurrent_count += 1
        if active_concurrent_count > max_observed_concurrency:
            max_observed_concurrency = active_concurrent_count
        await asyncio.sleep(0.1)
        active_concurrent_count -= 1
        return "ok"

    dispatcher.register_tool("monitored", monitored_tool)

    tool_calls = [
        {"id": f"call_{i}", "name": "monitored", "input": {}}
        for i in range(4)
    ]

    start = time.perf_counter()
    results = await dispatcher.dispatch(tool_calls)
    elapsed = time.perf_counter() - start

    assert len(results) == 4
    assert max_observed_concurrency <= 2, f"Observed {max_observed_concurrency} tasks exceeding max_concurrency=2"
    assert elapsed >= 0.18


@pytest.mark.anyio
async def test_dispatcher_sequential_only_barrier():
    """
    Verify that if any tool in the batch is registered as sequential_only=True,
    the dispatcher automatically falls back to safe sequential execution.
    """
    dispatcher = AsyncToolDispatcher(parallel_execution=True)

    execution_order = []

    async def read_tool():
        execution_order.append("read_start")
        await asyncio.sleep(0.08)
        execution_order.append("read_end")
        return "read_done"

    async def write_tool():
        execution_order.append("write_start")
        await asyncio.sleep(0.08)
        execution_order.append("write_end")
        return "write_done"

    dispatcher.register_tool("read_tool", read_tool, sequential_only=False)
    dispatcher.register_tool("write_tool", write_tool, sequential_only=True)
    assert dispatcher.is_sequential("write_tool") is True

    tool_calls = [
        {"id": "c1", "name": "read_tool", "input": {}},
        {"id": "c2", "name": "write_tool", "input": {}},
    ]

    results = await dispatcher.dispatch(tool_calls)
    assert len(results) == 2
    # Ran in strict sequential sequence because write_tool is sequential_only
    assert execution_order == ["read_start", "read_end", "write_start", "write_end"]

