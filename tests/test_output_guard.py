import asyncio
import os
from pathlib import Path
import shutil
import sys
import tempfile
import pytest

AGENTS_ROOT = str(Path(__file__).resolve().parent.parent)
if AGENTS_ROOT not in sys.path:
    sys.path.insert(0, AGENTS_ROOT)

from core.dispatcher import AsyncToolDispatcher, ToolExecutionResult
from core.output_guard import (
    DataPointer,
    LocalDiskPayloadStore,
    OutputGuard,
    OutputGuardMode,
    ToolOutputTruncator,
)


@pytest.fixture
def temp_vault():
    temp_dir = tempfile.mkdtemp(prefix="test_vault_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


# ==============================================================================
# 1. ToolOutputTruncator Unit Tests
# ==============================================================================

def test_truncator_below_threshold():
    text = "Short output line 1\nLine 2\nLine 3"
    res = ToolOutputTruncator.truncate(text, max_chars=1000, head_lines=5, tail_lines=5)
    assert not res.is_truncated
    assert res.text == text
    assert res.omitted_lines == 0
    assert res.omitted_chars == 0
    assert res.total_lines == 3


def test_truncator_multiline_above_threshold():
    lines = [f"Log entry line {i:04d} - status OK" for i in range(100)]
    text = "\n".join(lines)
    # 100 lines * ~30 chars = ~3000 chars. Let threshold be 500 chars.
    res = ToolOutputTruncator.truncate(text, max_chars=500, head_lines=5, tail_lines=5)

    assert res.is_truncated
    assert res.total_lines == 100
    assert res.omitted_lines == 90
    assert res.omitted_chars > 0
    assert "Log entry line 0000" in res.text
    assert "Log entry line 0004" in res.text
    assert "Log entry line 0099" in res.text
    assert "OMITTED 90 lines" in res.text


def test_truncator_single_massive_line():
    text = "A" * 5000
    res = ToolOutputTruncator.truncate(text, max_chars=500, head_lines=5, tail_lines=5)
    assert res.is_truncated
    assert res.omitted_lines == 0
    assert res.omitted_chars == 4500
    assert "OMITTED 4,500 characters" in res.text


# ==============================================================================
# 2. LocalDiskPayloadStore Unit Tests
# ==============================================================================

def test_payload_store_save_and_retrieve(temp_vault):
    store = LocalDiskPayloadStore(storage_dir=temp_vault)
    payload = "Sample heavy payload: " + ("x" * 20000)

    ptr_id, uri = store.store(payload, media_type="text/plain", metadata={"source": "test"})
    assert ptr_id.startswith("ptr_")
    assert uri.startswith("file://")
    assert store.exists(ptr_id)

    retrieved = store.retrieve(ptr_id)
    assert retrieved == payload


def test_payload_store_deduplication(temp_vault):
    store = LocalDiskPayloadStore(storage_dir=temp_vault)
    payload = "Identical payload content repeated"

    ptr_id1, uri1 = store.store(payload)
    ptr_id2, uri2 = store.store(payload)

    assert ptr_id1 == ptr_id2
    assert uri1 == uri2

    # Should only have 1 data file in directory
    files = [f for f in Path(temp_vault).glob("ptr_*") if not f.name.endswith(".meta.json")]
    assert len(files) == 1


def test_payload_store_nonexistent(temp_vault):
    store = LocalDiskPayloadStore(storage_dir=temp_vault)
    assert not store.exists("ptr_does_not_exist")
    assert store.retrieve("ptr_does_not_exist") is None


def test_payload_store_delete(temp_vault):
    store = LocalDiskPayloadStore(storage_dir=temp_vault)
    payload = "Payload to be deleted"
    ptr_id, _ = store.store(payload, metadata={"test": True})

    assert store.exists(ptr_id)
    deleted = store.delete(ptr_id)
    assert deleted is True
    assert not store.exists(ptr_id)
    assert store.retrieve(ptr_id) is None


# ==============================================================================
# 3. OutputGuard Modes & Media Types
# ==============================================================================

def test_output_guard_passthrough(temp_vault):
    store = LocalDiskPayloadStore(storage_dir=temp_vault)
    guard = OutputGuard(
        mode=OutputGuardMode.PASSTHROUGH,
        threshold_chars=100,
        payload_store=store,
    )

    massive_text = "Z" * 1000
    res = guard.process(massive_text)
    assert not res.is_offloaded
    assert not res.is_truncated
    assert res.content == massive_text
    assert res.data_pointer is None


def test_output_guard_truncate_only(temp_vault):
    store = LocalDiskPayloadStore(storage_dir=temp_vault)
    guard = OutputGuard(
        mode=OutputGuardMode.TRUNCATE_ONLY,
        threshold_chars=200,
        payload_store=store,
    )

    lines = [f"Line {i}" for i in range(50)]
    text = "\n".join(lines)
    res = guard.process(text)

    assert res.is_truncated
    assert not res.is_offloaded
    assert res.data_pointer is None
    assert "TOOL OUTPUT TRUNCATED" in res.content
    assert "Storage offloading is disabled" in res.content


def test_output_guard_offload_and_truncate(temp_vault):
    store = LocalDiskPayloadStore(storage_dir=temp_vault)
    guard = OutputGuard(
        mode=OutputGuardMode.OFFLOAD_AND_TRUNCATE,
        threshold_chars=300,
        head_lines=5,
        tail_lines=3,
        payload_store=store,
    )

    lines = [f"Database Record #{i}: {i * 100}" for i in range(100)]
    text = "\n".join(lines)

    res = guard.process(text, tool_name="query_db", tool_call_id="call_999")

    assert res.is_truncated
    assert res.is_offloaded
    assert res.data_pointer is not None
    assert res.data_pointer.size_bytes == len(text.encode("utf-8"))
    assert res.data_pointer.total_lines == 100
    assert "Database Record #0" in res.content
    assert "Database Record #99" in res.content
    assert "TOOL OUTPUT EXCEEDED INLINE THRESHOLD" in res.content
    assert res.data_pointer.storage_uri in res.content

    # Confirm lossless content was saved to store
    retrieved = store.retrieve(res.data_pointer.pointer_id)
    assert retrieved == text


# ==============================================================================
# 4. AsyncToolDispatcher Integration Tests
# ==============================================================================

@pytest.mark.anyio
async def test_dispatcher_with_output_guard_below_threshold(temp_vault):
    store = LocalDiskPayloadStore(storage_dir=temp_vault)
    guard = OutputGuard(threshold_chars=500, payload_store=store)
    dispatcher = AsyncToolDispatcher(output_guard=guard)

    async def small_tool():
        return "Small tool result"

    dispatcher.register_tool("small_tool", small_tool)

    results = await dispatcher.dispatch([
        {"id": "c1", "name": "small_tool", "input": {}}
    ])

    assert len(results) == 1
    res = results[0]
    assert res.success is True
    assert res.result == "Small tool result"
    assert not res.is_offloaded
    assert not res.is_truncated
    assert res.data_pointer is None


@pytest.mark.anyio
async def test_dispatcher_with_output_guard_above_threshold(temp_vault):
    store = LocalDiskPayloadStore(storage_dir=temp_vault)
    guard = OutputGuard(threshold_chars=400, head_lines=3, tail_lines=3, payload_store=store)
    dispatcher = AsyncToolDispatcher(output_guard=guard)

    big_payload = "\n".join([f"Trace item {i}" for i in range(50)])

    async def heavy_tool():
        return big_payload

    dispatcher.register_tool("heavy_tool", heavy_tool)

    results = await dispatcher.dispatch([
        {"id": "call_big_1", "name": "heavy_tool", "input": {}}
    ])

    assert len(results) == 1
    res = results[0]
    assert res.success is True
    assert res.is_offloaded is True
    assert res.is_truncated is True
    assert res.data_pointer is not None
    assert "TOOL OUTPUT EXCEEDED INLINE THRESHOLD" in res.result
    assert "Trace item 0" in res.result
    assert "Trace item 49" in res.result

    # Verify exact roundtrip retrieval
    stored = store.retrieve(res.data_pointer["pointer_id"])
    assert stored == big_payload


@pytest.mark.anyio
async def test_dispatcher_parallel_mixed_output_sizes(temp_vault):
    store = LocalDiskPayloadStore(storage_dir=temp_vault)
    guard = OutputGuard(threshold_chars=300, head_lines=2, tail_lines=2, payload_store=store)
    dispatcher = AsyncToolDispatcher(output_guard=guard, parallel_execution=True)

    async def tool_small():
        await asyncio.sleep(0.01)
        return "Compact output"

    async def tool_large():
        await asyncio.sleep(0.01)
        return "\n".join([f"Huge line {k}" for k in range(80)])

    dispatcher.register_tool("tool_small", tool_small)
    dispatcher.register_tool("tool_large", tool_large)

    tool_calls = [
        {"id": "call_1", "name": "tool_small", "input": {}},
        {"id": "call_2", "name": "tool_large", "input": {}},
        {"id": "call_3", "name": "tool_small", "input": {}},
    ]

    results = await dispatcher.dispatch(tool_calls)

    assert len(results) == 3
    # Call 1: small
    assert results[0].tool_call_id == "call_1"
    assert results[0].result == "Compact output"
    assert not results[0].is_offloaded

    # Call 2: large
    assert results[1].tool_call_id == "call_2"
    assert results[1].is_offloaded is True
    assert "TOOL OUTPUT EXCEEDED INLINE THRESHOLD" in results[1].result

    # Call 3: small
    assert results[2].tool_call_id == "call_3"
    assert results[2].result == "Compact output"
    assert not results[2].is_offloaded
