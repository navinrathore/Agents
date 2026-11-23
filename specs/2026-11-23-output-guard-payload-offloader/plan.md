v b # Plan: OutputGuard & Payload Offloader (Data Pointer)

## Proposed Architecture & Component Flow

```
              Tool Execution Result (str)
                          │
                          ▼
            ┌───────────────────────────┐
            │        OutputGuard        │
            └─────────────┬─────────────┘
                          │
              len(text) > threshold?
               ├── NO  ──► Return raw string unchanged
               └── YES ──► Mode Selection:
                            │
       ┌────────────────────┼────────────────────┐
       ▼                    ▼                    ▼
[OFFLOAD_AND_TRUNCATE]   [TRUNCATE_ONLY]    [PASSTHROUGH]
       │                    │                    │
 1. SHA-256 Storage    1. Head/Tail Excerpt  Raw String
    (PayloadStore)     2. Warning Banner
 2. Head/Tail Excerpt
 3. Return DataPointer
```

---

## Phased Implementation Plan

### Phase 1: Core Engine (`projects/Agents/core/output_guard.py`)
1. **`ToolOutputTruncator`**:
   - `truncate(text, max_chars, head_lines, tail_lines) -> TruncationResult`
   - Handles multi-line log excerpts, preserves line endings, counts omitted lines and omitted character counts.
2. **`BasePayloadStore` & `LocalDiskPayloadStore`**:
   - `store(payload: str, media_type: str = "text/plain") -> DataPointer`
   - `retrieve(pointer_id: str) -> Optional[str]`
   - `exists(pointer_id: str) -> bool`
   - Content-addressable file storage (`sha256(content)[:16]`), preventing redundant disk writes.
3. **`OutputGuard` Coordinator**:
   - Manages modes (`OFFLOAD_AND_TRUNCATE`, `TRUNCATE_ONLY`, `PASSTHROUGH`).
   - Generates the standard LLM-friendly summary contract and metadata banner.

### Phase 2: Dispatcher Middleware (`projects/Agents/core/dispatcher.py`)
1. Extend `AsyncToolDispatcher.__init__`:
   - `output_guard: Optional[OutputGuard] = None`
   - Default: automatically instantiate `OutputGuard(mode=OutputGuardMode.OFFLOAD_AND_TRUNCATE)` when enabled.
2. In `AsyncToolDispatcher._execute_single_tool`:
   - Pass tool execution result through `self.output_guard.process(result_str)`.
   - Record pointer ID and offload status in `ToolExecutionResult` metadata.

### Phase 3: Selective Pointer Query Tools (`projects/Agents/core/pointer_tools.py`)
Register agent tools that allow the LLM to interactively query offloaded files:
1. `read_pointer_slice(pointer_id: str, start_line: int, end_line: int) -> str`
2. `query_pointer_json(pointer_id: str, json_path: str) -> str`
3. `grep_pointer(pointer_id: str, pattern: str, max_matches: int = 20) -> str`

### Phase 4: Verification & Test Suite (`projects/Agents/tests/test_output_guard.py`)
1. Unit tests for pure truncation (`ToolOutputTruncator`).
2. Unit tests for `LocalDiskPayloadStore` (deduplication, round-trip retrieval, error handling).
3. Integration tests with `AsyncToolDispatcher` verifying automatic interception of oversized outputs.
4. Selective query tool tests (`read_pointer_slice`, `query_pointer_json`, `grep_pointer`).
