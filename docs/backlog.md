# Agent Development Backlog

The following items represent architectural improvements for the autonomous agent loop and core framework utilities:

## Core Architectural Milestones
- [x] **Loop/Repetition Detection**: Implement logic in `analyst.py` to hash or compare consecutive `STDERR` outputs. If the agent repeats the exact same error 3 times, break the loop and alert the user.
  - [ ] *(Nice-to-have)* **Hash-based non-consecutive detection**: Upgrade `RepetitionDetector` in `utils.py` to use `hashlib` and maintain a sliding window of past output hashes. This would catch repeated errors that are non-consecutive (e.g., error A → error B → error A) rather than only back-to-back repeats.
- [x] **Context Pruning**: Implement a token counter in the `BaseLLMClient`. When the context size approaches a threshold (e.g., 4000 tokens), replace older `user`/`assistant` turns with a summarized representation of the task progress.
- [ ] **Amplitude MCP Integration (Phase 2 feature)**: Finalize the integration of the Model Context Protocol (MCP) server for direct querying of Amplitude product analytics.
- [ ] **Robust Sandboxing**: Transition from the basic `PythonExecutor` subprocess to a secure Docker or Firecracker microVM for safe code execution in untrusted environments.
- [ ] **Prompt-RAG for Enterprise Scale**: Replace the keyword-based `SOPRouter` with a Prompt-RAG system using a vector store (e.g. Chroma/pgvector) to semantically select and retrieve matching SOP instructions based on query context.

## Framework Utilities Backlog (Grouped by Capability)

### Group 1: Execution Safety & Tool Handling
- [ ] **Hash-based Non-Consecutive Repetition Detection**: Upgrade `RepetitionDetector` in `core/utils.py` to use `hashlib` and maintain a sliding window of past output hashes to catch non-consecutive loop repeats (e.g. error A → error B → error A).
- [ ] **ToolOutputTruncator**: Truncate oversized tool STDOUT/STDERR responses to a configurable character/token limit while preserving head and tail excerpts to prevent context window overflow.
- [ ] **CodeSanitizer**: Clean and extract pure code blocks from raw LLM responses (stripping markdown backticks, shell wrappers, or extraneous explanation text).

### Group 2: Token Accounting & Cost Tracking
- [ ] **TokenCounter & CostTracker**: Calculate exact token usage per model (using model-specific tokenizers or tiktoken) and track cumulative API spend (input vs. output tokens) across agent loops.

### Group 3: Resilience & State Persistence (Crash Recovery)
- [ ] **CheckpointManager / StateSerializer**: Serialize and hydrate agent loop state (messages, checklist, active SOP, tool outputs) to JSON/SQLite for crash recovery and checkpoint resumption.
- [ ] **ExponentialBackoffRetry**: Reusable retry decorator/context manager with jitter for LLM API calls to gracefully handle rate limits (`429`), network glitches, and transient timeouts.

### Group 4: Structured Output Parsing
- [ ] **JsonExtractor & SchemaValidator**: Extract embedded JSON objects from raw LLM text outputs and validate structure against Pydantic models or JSON schemas when function calling APIs are unavailable.

### Group 5: Observability, Telemetry & Security
- [ ] **PIIRedactor & SecretSanitizer**: Redact sensitive data (API keys, passwords, bearer tokens, PII) from agent inputs, tool outputs, and execution logs.
- [ ] **TrajectoryLogger**: Dual-transcript logging helper (`transcript.jsonl` with truncated parameters and `transcript_full.jsonl` with complete raw payloads) for daily debugging and trajectory evaluation.
