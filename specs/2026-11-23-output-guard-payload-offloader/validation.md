# Validation: OutputGuard & Payload Offloader (Data Pointer)

## Test Coverage Matrix

| Test Case | Component | Verification Criteria |
| :--- | :--- | :--- |
| **Below Threshold Passthrough** | `OutputGuard` | Text with length $\le$ `threshold_chars` returned unchanged with zero disk writes. |
| **Truncation Excerpt Fidelity** | `ToolOutputTruncator` | Preserves exact first N lines and last M lines. Accurately reports omitted line and byte counts. |
| **Content-Addressable Storage** | `LocalDiskPayloadStore` | Identical payloads yield identical `pointer_id`s; file exists on disk with exact payload content. |
| **Roundtrip Retrieve** | `LocalDiskPayloadStore` | `retrieve(pointer_id)` restores 100% of the original string. Missing pointer returns `None`. |
| **Dispatcher Integration** | `AsyncToolDispatcher` | A tool returning 50 KB has its output replaced with a `DataPointer` string, while `ToolExecutionResult` retains `duration` and success status. |
| **Slice Tooling** | `pointer_tools.py` | `read_pointer_slice` correctly paginates lines from the offloaded file on disk. |
| **Grep Tooling** | `pointer_tools.py` | `grep_pointer` finds regex matches in the offloaded file and reports line numbers. |
| **JSON Query Tooling** | `pointer_tools.py` | `query_pointer_json` navigates dot-notation or JSON keys without loading the full file into the LLM context. |
