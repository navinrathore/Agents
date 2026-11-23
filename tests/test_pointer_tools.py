import asyncio
import json
from pathlib import Path
import shutil
import sys
import tempfile
import pytest

AGENTS_ROOT = str(Path(__file__).resolve().parent.parent)
if AGENTS_ROOT not in sys.path:
    sys.path.insert(0, AGENTS_ROOT)

from core.dispatcher import AsyncToolDispatcher
from core.output_guard import LocalDiskPayloadStore
from core.pointer_tools import PointerToolSuite, normalize_pointer_id


@pytest.fixture
def temp_vault():
    temp_dir = tempfile.mkdtemp(prefix="test_pointer_tools_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def suite_with_data(temp_vault):
    store = LocalDiskPayloadStore(storage_dir=temp_vault)

    # 1. Multi-line text data (50 lines)
    text_content = "\n".join([f"Line {i:03d}: System event record with status={'ERROR' if i % 10 == 0 else 'OK'}" for i in range(1, 51)])
    text_ptr, _ = store.store(text_content, media_type="text/plain")

    # 2. Structured JSON data
    json_data = {
        "status": "success",
        "code": 200,
        "data": {
            "users": [
                {"id": 101, "name": "Alice", "role": "admin", "tags": ["lead", "ops"]},
                {"id": 102, "name": "Bob", "role": "engineer", "tags": ["backend"]},
                {"id": 103, "name": "Charlie", "role": "analyst", "tags": ["data"]},
            ],
            "metrics": {
                "requests_total": 45000,
                "latency_p99_ms": 12.4,
            },
        },
    }
    json_ptr, _ = store.store(json.dumps(json_data, indent=2), media_type="application/json")

    suite = PointerToolSuite(store=store)
    return suite, text_ptr, json_ptr, text_content, json_data


# ==============================================================================
# 1. normalize_pointer_id tests
# ==============================================================================

def test_normalize_pointer_id():
    assert normalize_pointer_id("ptr_1234567890abcdef") == "ptr_1234567890abcdef"
    assert normalize_pointer_id("pointer://ptr_1234567890abcdef") == "ptr_1234567890abcdef"
    assert normalize_pointer_id("file:///vault/pointers/ptr_1234567890abcdef.json") == "ptr_1234567890abcdef"
    assert normalize_pointer_id("/home/user/vault/ptr_1234567890abcdef.txt") == "ptr_1234567890abcdef"
    assert normalize_pointer_id("  ptr_abc123.txt  ") == "ptr_abc123"


# ==============================================================================
# 2. read_pointer_slice tests
# ==============================================================================

def test_read_pointer_slice_normal(suite_with_data):
    suite, text_ptr, _, _, _ = suite_with_data
    slice_out = suite.read_pointer_slice(text_ptr, start_line=5, end_line=10)

    assert "SLICE: Lines 5-10 of 50" in slice_out
    assert "Line 005:" in slice_out
    assert "Line 010:" in slice_out
    assert "Line 004:" not in slice_out
    assert "Line 011:" not in slice_out
    assert "40 remaining" in slice_out


def test_read_pointer_slice_end_of_file(suite_with_data):
    suite, text_ptr, _, _, _ = suite_with_data
    slice_out = suite.read_pointer_slice(text_ptr, start_line=45, end_line=50)

    assert "SLICE: Lines 45-50 of 50" in slice_out
    assert "Line 050:" in slice_out
    assert "[END OF ARTIFACT]" in slice_out


def test_read_pointer_slice_invalid_start_line(suite_with_data):
    suite, text_ptr, _, _, _ = suite_with_data
    slice_out = suite.read_pointer_slice(text_ptr, start_line=999)
    assert "exceeds total lines (50)" in slice_out


def test_read_pointer_slice_missing_pointer(suite_with_data):
    suite, _, _, _, _ = suite_with_data
    slice_out = suite.read_pointer_slice("ptr_nonexistent_999")
    assert "not found in storage" in slice_out


# ==============================================================================
# 3. grep_pointer tests
# ==============================================================================

def test_grep_pointer_matches(suite_with_data):
    suite, text_ptr, _, _, _ = suite_with_data
    # Status ERROR occurs on lines 10, 20, 30, 40, 50
    grep_out = suite.grep_pointer(text_ptr, pattern="status=ERROR")

    assert "GREP RESULTS: 5 match(es) for 'status=ERROR'" in grep_out
    assert "Line 010" in grep_out
    assert "Line 050" in grep_out


def test_grep_pointer_with_context(suite_with_data):
    suite, text_ptr, _, _, _ = suite_with_data
    grep_out = suite.grep_pointer(text_ptr, pattern="Line 020", context_lines=2)

    assert "GREP RESULTS: 1 match(es)" in grep_out
    assert ">>>    20 | Line 020" in grep_out
    assert "18 | Line 018" in grep_out
    assert "22 | Line 022" in grep_out


def test_grep_pointer_no_matches(suite_with_data):
    suite, text_ptr, _, _, _ = suite_with_data
    grep_out = suite.grep_pointer(text_ptr, pattern="NON_EXISTENT_PATTERN_XYZ")
    assert "No matches found" in grep_out


def test_grep_pointer_max_matches_cap(suite_with_data):
    suite, text_ptr, _, _, _ = suite_with_data
    grep_out = suite.grep_pointer(text_ptr, pattern="status=ERROR", max_matches=2)
    assert "Showing first 2 matches of 5" in grep_out


def test_grep_pointer_invalid_regex(suite_with_data):
    suite, text_ptr, _, _, _ = suite_with_data
    grep_out = suite.grep_pointer(text_ptr, pattern="[unclosed-bracket")
    assert "Error: Invalid regex pattern" in grep_out


# ==============================================================================
# 4. query_pointer_json tests
# ==============================================================================

def test_query_pointer_json_root_summary(suite_with_data):
    suite, _, json_ptr, _, _ = suite_with_data
    res = suite.query_pointer_json(json_ptr, json_path="")
    assert '"status": "success"' in res
    assert '"metrics"' in res


def test_query_pointer_json_nested_keys(suite_with_data):
    suite, _, json_ptr, _, _ = suite_with_data
    res = suite.query_pointer_json(json_ptr, json_path="data.metrics.latency_p99_ms")
    assert res == "12.4"


def test_query_pointer_json_array_indexing(suite_with_data):
    suite, _, json_ptr, _, _ = suite_with_data
    res1 = suite.query_pointer_json(json_ptr, json_path="data.users[1].name")
    assert res1 == "Bob"

    res2 = suite.query_pointer_json(json_ptr, json_path="data.users.0.role")
    assert res2 == "admin"


def test_query_pointer_json_array_out_of_bounds(suite_with_data):
    suite, _, json_ptr, _, _ = suite_with_data
    res = suite.query_pointer_json(json_ptr, json_path="data.users[99].name")
    assert "out of bounds" in res


def test_query_pointer_json_missing_key(suite_with_data):
    suite, _, json_ptr, _, _ = suite_with_data
    res = suite.query_pointer_json(json_ptr, json_path="data.nonexistent")
    assert "Key 'nonexistent' not found" in res
    assert "Available keys at this level" in res


def test_query_pointer_json_invalid_json(temp_vault):
    store = LocalDiskPayloadStore(storage_dir=temp_vault)
    bad_ptr, _ = store.store("Not JSON at all! Just raw text.")
    suite = PointerToolSuite(store=store)

    res = suite.query_pointer_json(bad_ptr, json_path="data")
    assert "does not contain valid JSON" in res


# ==============================================================================
# 5. AsyncToolDispatcher Registration & Schema Validation
# ==============================================================================

@pytest.mark.anyio
async def test_pointer_tools_dispatcher_integration(suite_with_data):
    suite, text_ptr, json_ptr, _, _ = suite_with_data
    dispatcher = AsyncToolDispatcher()
    suite.register_tools(dispatcher)

    # 1. Test read_pointer_slice through dispatcher
    results = await dispatcher.dispatch([
        {
            "id": "c1",
            "name": "read_pointer_slice",
            "input": {"pointer_id": text_ptr, "start_line": 1, "end_line": 3},
        },
        {
            "id": "c2",
            "name": "grep_pointer",
            "input": {"pointer_id": text_ptr, "pattern": "Line 010"},
        },
        {
            "id": "c3",
            "name": "query_pointer_json",
            "input": {"pointer_id": json_ptr, "json_path": "data.metrics.requests_total"},
        },
    ])

    assert len(results) == 3
    assert results[0].success is True
    assert "SLICE: Lines 1-3 of 50" in results[0].result

    assert results[1].success is True
    assert "GREP RESULTS: 1 match(es)" in results[1].result

    assert results[2].success is True
    assert results[2].result == "45000"


def test_pointer_tools_schemas(suite_with_data):
    suite, _, _, _, _ = suite_with_data
    schemas = suite.get_tool_schemas()
    assert len(schemas) == 3
    names = {s["function"]["name"] for s in schemas}
    assert names == {"read_pointer_slice", "grep_pointer", "query_pointer_json"}
