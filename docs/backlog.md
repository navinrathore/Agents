# Agent Development Backlog

The following items represent architectural improvements for the autonomous agent loop:

- [x] **Loop/Repetition Detection**: Implement logic in `analyst.py` to hash or compare consecutive `STDERR` outputs. If the agent repeats the exact same error 3 times, break the loop and alert the user.
- [x] **Context Pruning**: Implement a token counter in the `BaseLLMClient`. When the context size approaches a threshold (e.g., 4000 tokens), replace older `user`/`assistant` turns with a summarized representation of the task progress.
- [ ] **Amplitude MCP Integration (Phase 2 feature)**: Finalize the integration of the Model Context Protocol (MCP) server for direct querying of Amplitude product analytics.
- [ ] **Robust Sandboxing**: Transition from the basic `PythonExecutor` subprocess to a secure Docker or Firecracker microVM for safe code execution in untrusted environments.
