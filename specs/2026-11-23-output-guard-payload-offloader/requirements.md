# Requirements: OutputGuard & Payload Offloader (Data Pointer)

## Overview
Large tool responses (e.g. database query dumps, repository search logs, raw web scrape bodies, API responses) rapidly bloat LLM context windows, leading to quadratic token cost scaling, high latency, context degradation ("Lost-in-the-Middle"), and severe prompt injection vulnerabilities. 

`OutputGuard` is a unified execution safety and context protection subsystem. When an output exceeds configurable thresholds (character/byte or token counts), `OutputGuard`:
1. **Preserves the complete, lossless artifact** in persistent, content-addressable local storage (`LocalDiskPayloadStore` / `DataPointer`).
2. **Generates a smart, human- and LLM-readable excerpt** preserving head and tail context (powered by `ToolOutputTruncator`) along with schema/line metadata.
3. **Emits a compact `DataPointer` contract** back to the LLM context, accompanied by specialized query/slice tools (`read_pointer_slice`, `query_pointer_json`, `grep_pointer`) so downstream turns can selectively inspect data on demand.

---

## 1. Scope

### In-Scope
- **Dual Capability Engine (`core/output_guard.py`)**:
  - `ToolOutputTruncator`: Pure in-memory head/tail truncation with line omission statistics and structured warning wrappers.
  - `PayloadStore` / `DataPointer`: Content-addressable SHA-256 storage on disk with metadata hydration (size, token estimates, line count, MIME type).
  - `OutputGuard`: Unified coordinator orchestrating threshold evaluation, storage offloading, and preview truncation.
- **Configurable Operating Modes**:
  - `OFFLOAD_AND_TRUNCATE` *(Default)*: Full payload written to store, smart head/tail preview returned in `DataPointer` contract.
  - `TRUNCATE_ONLY`: Memory-only head/tail truncation with omission notice (no disk write, for ephemeral/stateless runs).
  - `PASSTHROUGH`: Bypasses truncation/offloading (for debugging or small contexts).
- **Dispatcher Middleware Integration**:
  - Seamless hook into `AsyncToolDispatcher._execute_single_tool` in `core/dispatcher.py`.
- **Selective Resolution Tools (`core/pointer_tools.py`)**:
  - `read_pointer_slice(pointer_id, start_line, end_line)`: Paginated line slicing for large logs, text, or code.
  - `query_pointer_json(pointer_id, json_path)`: Extraction of specific sub-nodes or keys from large JSON dumps.
  - `grep_pointer(pointer_id, pattern, max_matches)`: Regex/keyword scanning across large text outputs.
- **Hermetic Testing**: Comprehensive pytest suite verifying threshold boundaries, preview fidelity, content-addressable deduplication, and dispatcher integration.

### Out-of-Scope
- Remote cloud blob storage (AWS S3, GCS) drivers for local runs; local disk storage covers local agent runs, with an extensible `BasePayloadStore` interface for future cloud backends.
- Automatic vector embedding of all offloaded tool outputs (better handled by dedicated RAG stores when needed).

---

## 2. Core Contracts & Data Structures

### DataPointer Contract
```python
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

class DataPointer(BaseModel):
    pointer_id: str
    storage_uri: str
    media_type: str = "text/plain"
    size_bytes: int
    estimated_tokens: int
    total_lines: int
    preview_snippet: str
    omitted_lines: int
    is_offloaded: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_llm_string(self) -> str:
        """Formatted representation passed directly into LLM tool result context."""
        ...
```

### Threshold Defaults
- `threshold_chars`: 8,000 characters (~2,000 tokens).
- `head_lines`: 15 lines.
- `tail_lines`: 10 lines.
- `storage_dir`: `projects/Agents/vault/pointers/` (or configurable session workspace).
