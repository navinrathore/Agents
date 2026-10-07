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
- [ ] **Payload Offloading Pattern (Data Pointer)**: Offload oversized tool results (e.g., > 10KB) to persistent storage and return a compact pointer contract (with head/tail preview) to the LLM context to prevent context window overflow.
- [ ] **CodeSanitizer**: Clean and extract pure code blocks from raw LLM responses (stripping markdown backticks, shell wrappers, or extraneous explanation text).
- [ ] [P2] **Human-in-the-Loop (HITL) Checkpoints / UX Friction**: Implement stateful pause/resume mechanisms for high-risk tool execution. When an agent requests a sensitive action, pause the loop, render a confirmation modal to the user, and resume execution with the user's explicit approval or rejection injected back into context.

### Group 2: Token Accounting & Cost Tracking
- [ ] **TokenCounter & CostTracker**: Calculate exact token usage per model (using model-specific tokenizers or tiktoken) and track cumulative API spend (input vs. output tokens) across agent loops.

### Group 3: Resilience & State Persistence (Crash Recovery)
- [ ] **CheckpointManager / StateSerializer**: Serialize and hydrate agent loop state (messages, checklist, active SOP, tool outputs) to JSON/SQLite for crash recovery and checkpoint resumption.
- [ ] **Semantic Memory Graph (`NetworkX` / `Kùzu`)**: Maintain an in-memory entity/fact graph across multi-turn ReAct loops to store validated environment knowledge, schema discoveries, and task milestones without saturating prompt context.
- [ ] **ExponentialBackoffRetry**: Reusable retry decorator/context manager with jitter for LLM API calls to gracefully handle rate limits (`429`), network glitches, and transient timeouts.

### Group 4: Structured Output Parsing
- [x] **JsonExtractor & SchemaValidator**: Extract embedded JSON objects from raw LLM text outputs and validate structure against Pydantic models (or raw dictionary key/type schemas when Pydantic models are not present).

### Group 5: Observability, Telemetry & Security
- [ ] **PIIRedactor & SecretSanitizer**: Redact sensitive data (API keys, passwords, bearer tokens, PII) from agent inputs, tool outputs, and execution logs.
- [ ] **TrajectoryLogger**: Dual-transcript logging helper (`transcript.jsonl` with truncated parameters and `transcript_full.jsonl` with complete raw payloads) for daily debugging and trajectory evaluation.
- [ ] **Dynamic Context Minimization (Summarize-and-Forget)**: Implement summarize-and-forget patterns to aggressively truncate conversation history and remove raw untrusted data (like tool outputs from malicious PDFs) from the context window, reducing the persistent prompt injection attack surface.

### Group 6: Modular Skill Registry & Plugin Architecture
- [ ] **SkillRegistry & SkillManager (`core/skills.py`)**: Implement framework-level automatic discovery of `SKILL.md` YAML frontmatter metadata, dynamic prompt loading, and tool schema registration.
- [ ] **Declarative Skill Package Specification**: Standardize user-defined skill package directory layouts (`SKILL.md`, `tools.py`, `templates/`, `resources/`) across agents.
- [ ] **Sub-Agent Skill Execution Engine**: Support spawning isolated child ReAct agent loops for complex sub-agent skill execution.

### Group 7: Documentation & Structure
- [ ] **Multi-Page Guide Refactoring**: Split `building_agents_master_guide.md` (1,340+ lines) into a modular `docs/master_guide/` folder structure (`01_foundations.md`, `02_config.md`, `03_architectural_facets.md`, `04_multi_agent.md`, `05_evaluation_ops.md`, `06_advanced_topics.md`) for improved readability and maintenance.

### Group 8: Critique-Sourced Improvements (from LLM-as-Judge Review)
- [ ] **Cost Estimation Worksheet**: Add a practical worksheet to the design checklist doc calculating expected per-session cost: `(input_tokens × $/token + output_tokens × $/token) × avg_loops × sessions_per_day`. Include reference costs for Claude Sonnet, Gemini Flash, GPT-4o, and Qwen open-weight.
- [ ] **Prompt Regression Testing Template**: Add a golden trajectory test template to the templates doc with example test cases (input query, expected tool call sequence, expected output assertions) and a `pytest` harness for automated prompt regression CI.

### Group 9: OWASP LLM Vulnerability Mitigation
- [ ] **[OWASP LLM02] Insecure Output Handling**: Implement strict output sanitization (e.g., HTML escaping, Markdown rendering safety) and Content Security Policy (CSP) headers to prevent XSS from agent responses in the UI.
- [ ] **[OWASP LLM03] Training Data Poisoning**: Establish a robust ML-SecOps pipeline for vetting and cryptographic verification of fine-tuning datasets and foundational models.
- [ ] **[OWASP LLM05] Supply Chain Vulnerabilities**: Add dependency scanning (e.g., Snyk/Dependabot), model vulnerability scanning, and secure sandbox execution (Docker/Firecracker VM) for all agent environments.
- [ ] **[OWASP LLM09] Misinformation**: Implement RAG (Retrieval-Augmented Generation) grounding checks, factual consistency evaluators (LLM-as-Judge), and explicit confidence thresholds before taking high-stakes actions.


