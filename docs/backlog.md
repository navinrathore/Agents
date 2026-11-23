# Agent Development Backlog

The following items represent architectural improvements for the autonomous agent loop and core framework utilities:

## Core Architectural Milestones
- [x] 🔴 P0 **Loop/Repetition Detection**: Implement logic in `analyst.py` to hash or compare consecutive `STDERR` outputs. If the agent repeats the exact same error 3 times, break the loop and alert the user. #reliability #safety
  - [ ] 🟢 P2 *(Nice-to-have)* **Hash-based non-consecutive detection**: Upgrade `RepetitionDetector` in `utils.py` to use `hashlib` and maintain a sliding window of past output hashes. This would catch repeated errors that are non-consecutive (e.g., error A → error B → error A) rather than only back-to-back repeats. #reliability #algorithms
- [x] 🔴 P0 **Context Pruning**: Implement a token counter in the `BaseLLMClient`. When the context size approaches a threshold (e.g., 4000 tokens), replace older `user`/`assistant` turns with a summarized representation of the task progress. #performance #context
- [ ] 🟢 P2 **Amplitude MCP Integration (Phase 2 feature)**: Finalize the integration of the Model Context Protocol (MCP) server for direct querying of Amplitude product analytics. #mcp #observability
- [ ] 🔴 P0 **Robust Sandboxing**: Transition from the basic `PythonExecutor` subprocess to a secure Docker or Firecracker microVM for safe code execution in untrusted environments. #security #sandboxing
- [ ] 🟡 P1 **Prompt-RAG for Enterprise Scale**: Replace the keyword-based `SOPRouter` with a Prompt-RAG system using a vector store (e.g. Chroma/pgvector) to semantically select and retrieve matching SOP instructions based on query context. #architecture #rag

## Framework Utilities Backlog (Grouped by Capability)

### Group 1: Execution Safety & Tool Handling
- [x] 🔴 P0 **Parallel Tool Calling & Async Dispatcher (`core/dispatcher.py`)**: Built `AsyncToolDispatcher` with bounded semaphore concurrency (`max_concurrency`), configurable parallel/sequential execution toggle, per-tool timeout protection, error shielding, order preservation, and native MCP async tool bridging. #architecture #performance #tools
- [x] 🟡 P1 **OpenAPI Spec Tool Auto-Ingestion (`core/openapi_loader.py`)**: Ingest OpenAPI 3.0/3.1 and Swagger specs (JSON/YAML), auto-convert path operations into typed agent tool definitions (`OpenAITool` / `AnthropicTool` schemas), and generate execution handlers wired to `AsyncToolDispatcher`. Supports configurable generation strategies (1:1 direct endpoint mapping vs. generic dynamic API runner, tag/method filtering, dry-run simulation, and read-only safety modes). #architecture #tools #integration
- [ ] 🟢 P2 **Hash-based Non-Consecutive Repetition Detection**: Upgrade `RepetitionDetector` in `core/utils.py` to use `hashlib` and maintain a sliding window of past output hashes to catch non-consecutive loop repeats (e.g. error A → error B → error A). #reliability #safety
- [x] 🟡 P1 **OutputGuard & Payload Offloader (`core/output_guard.py`)**: Unified tool output truncation and payload offloading engine. Truncates oversized tool results using smart head/tail preservation while offloading full lossless payloads to content-addressed storage (`DataPointer`). Seamlessly hooks into `AsyncToolDispatcher` with configurable byte/token thresholds and provides selective query tools (`read_pointer_slice`, `query_pointer_json`, `grep_pointer`). #architecture #performance #safety
- [ ] 🟡 P1 **CodeSanitizer**: Clean and extract pure code blocks from raw LLM responses (stripping markdown backticks, shell wrappers, or extraneous explanation text). #reliability #dx
- [x] 🟡 P1 **Human-in-the-Loop (HITL) Checkpoints / UX Friction (`core/hitl.py`)**: Implement stateful pause/resume mechanisms for high-risk tool execution. When an agent requests a sensitive action, pause the loop, dispatch a review notification (Telegram, Webhook, Console, Mock), and resume execution with the user's explicit approval or rejection injected back into context. #ux #security

### Group 2: Token Accounting & Cost Tracking
- [ ] 🟡 P1 **TokenCounter & CostTracker**: Calculate exact token usage per model (using model-specific tokenizers or tiktoken) and track cumulative API spend (input vs. output tokens) across agent loops. #observability #cost

### Group 3: Resilience & State Persistence (Crash Recovery)
- [ ] 🔴 P0 **CheckpointManager / StateSerializer**: Serialize and hydrate agent loop state (messages, checklist, active SOP, tool outputs) to JSON/SQLite for crash recovery and checkpoint resumption. #reliability #resilience
- [ ] 🟢 P2 **Semantic Memory Graph (`NetworkX` / `Kùzu`)**: Maintain an in-memory entity/fact graph across multi-turn ReAct loops to store validated environment knowledge, schema discoveries, and task milestones without saturating prompt context. #architecture #memory
- [ ] 🔴 P0 **ExponentialBackoffRetry**: Reusable retry decorator/context manager with jitter for LLM API calls to gracefully handle rate limits (`429`), network glitches, and transient timeouts. #reliability #resilience

### Group 4: Structured Output Parsing
- [x] 🔴 P0 **JsonExtractor & SchemaValidator**: Extract embedded JSON objects from raw LLM text outputs and validate structure against Pydantic models (or raw dictionary key/type schemas when Pydantic models are not present). #reliability #architecture
- [x] 🔴 P0 **Universal Provider-Native Structured Output Engine**: Added tri-mode structured output (`auto`, `native`, `prompt_injection`) to `core/llm_clients.py` with OpenAI `response_format` strict schema, Anthropic forced tool use, and `prepare_strict_json_schema`. #architecture #reliability
- [ ] 🟢 P2 **[Logits Tweaking Spike] Standalone Constrained Decoding & Fast-Forwarding Test**: Implement a minimal PyTorch/HuggingFace `LogitsProcessor` or Outlines/XGrammar prototype testing custom logit masking ($-\infty$ to non-DFA tokens) and static token fast-forwarding to measure latency and token savings. #performance #research

### Group 5: Observability, Telemetry & Security
- [ ] 🔴 P0 **PIIRedactor & SecretSanitizer**: Redact sensitive data (API keys, passwords, bearer tokens, PII) from agent inputs, tool outputs, and execution logs. #security #compliance
- [ ] 🟡 P1 **TrajectoryLogger**: Dual-transcript logging helper (`transcript.jsonl` with truncated parameters and `transcript_full.jsonl` with complete raw payloads) for daily debugging and trajectory evaluation. #observability #telemetry
- [ ] 🔴 P0 **Dynamic Context Minimization (Summarize-and-Forget)**: Implement summarize-and-forget patterns to aggressively truncate conversation history and remove raw untrusted data (like tool outputs from malicious PDFs) from the context window, reducing the persistent prompt injection attack surface. #security #performance

### Group 6: Modular Skill Registry & Plugin Architecture
- [x] 🟡 P1 **SkillRegistry & SkillManager (`core/skills.py`)**: Implement framework-level automatic discovery of `SKILL.md` YAML frontmatter metadata, dynamic prompt loading, and tool schema registration. Features the Cascading Hybrid Router (Tier 1 deterministic fast path + Tier 2 LLM/semantic fallback). #architecture #plugin
- [x] 🟡 P1 **Declarative Skill Package Specification**: Standardize user-defined skill package directory layouts (`SKILL.md`, `tools.py`, `templates/`, `resources/`) across agents. Validated with reference `data_analyst` skill package. #architecture #standards
- [ ] 🟢 P2 **Sub-Agent Skill Execution Engine**: Support spawning isolated child ReAct agent loops for complex sub-agent skill execution. #architecture #multi-agent

### Group 7: Documentation & Structure
- [ ] 🟢 P2 **Multi-Page Guide Refactoring**: Split `building_agents_master_guide.md` (1,340+ lines) into a modular `docs/master_guide/` folder structure (`01_foundations.md`, `02_config.md`, `03_architectural_facets.md`, `04_multi_agent.md`, `05_evaluation_ops.md`, `06_advanced_topics.md`) for improved readability and maintenance. #dx #docs

### Group 8: Critique-Sourced Improvements (from LLM-as-Judge Review)
- [ ] 🟢 P2 **Cost Estimation Worksheet**: Add a practical worksheet to the design checklist doc calculating expected per-session cost: `(input_tokens × $/token + output_tokens × $/token) × avg_loops × sessions_per_day`. Include reference costs for Claude Sonnet, Gemini Flash, GPT-4o, and Qwen open-weight. #cost #dx
- [ ] 🟡 P1 **Prompt Regression Testing Template**: Add a golden trajectory test template to the templates doc with example test cases (input query, expected tool call sequence, expected output assertions) and a `pytest` harness for automated prompt regression CI. #testing #reliability

### Group 9: OWASP LLM Vulnerability Mitigation
- [ ] 🔴 P0 **[OWASP LLM02] Insecure Output Handling**: Implement strict output sanitization (e.g., HTML escaping, Markdown rendering safety) and Content Security Policy (CSP) headers to prevent XSS from agent responses in the UI. #security #ux
- [ ] 🟢 P2 **[OWASP LLM03] Training Data Poisoning**: Establish a robust ML-SecOps pipeline for vetting and cryptographic verification of fine-tuning datasets and foundational models. #security #data
- [ ] 🟡 P1 **[OWASP LLM05] Supply Chain Vulnerabilities**: Add dependency scanning (e.g., Snyk/Dependabot), model vulnerability scanning, and secure sandbox execution (Docker/Firecracker VM) for all agent environments. #security #devops
- [ ] 🟡 P1 **[OWASP LLM09] Misinformation**: Implement RAG (Retrieval-Augmented Generation) grounding checks, factual consistency evaluators (LLM-as-Judge), and explicit confidence thresholds before taking high-stakes actions. #security #reliability

### Group 10: Multi-Channel Remote Notification Gateway (`core/notifications.py`)
- [x] 🟡 P1 **Universal Notification Contracts**: Standardize `ReviewRequestPayload` and `NotificationAction` Pydantic models for cross-agent approval dispatch. #architecture #contracts
- [ ] 🟡 P1 **Declarative Preference Router (`NotificationGateway`)**: Load user-preferred channels from `notification_config.yaml` or environment variables, supporting single-channel dispatch or multi-target broadcasting. #architecture #routing
- [ ] 🟡 P1 **Freeware Channel Adapters**: Core free notification channels #ux #notifications
  - [x] 🟡 P1 **ConsoleChannel**: Rich ANSI-colored terminal card rendering for local development. #ux
  - [x] 🟡 P1 **MockChannel**: In-memory recording for 100% hermetic offline CI/CD test suites. #testing
  - [x] 🟡 P1 **WebhookChannel**: HTTP POST dispatcher pushing JSON payloads to local FastAPI endpoints, n8n, or custom automation hooks. #integration
  - [x] 🔴 P0 **TelegramChannel**: Free Telegram Bot API integration with inline keyboard callback buttons (`[Approve]`, `[Reject]`) for zero-cost mobile approvals. #ux #notifications
  - [ ] 🟡 P1 **SlackChannel**: Incoming Webhook / Block Kit interactive card dispatcher for free team workspaces. #ux #notifications
- [ ] 🟢 P2 **Future Commercial Adapters**: Enterprise notification targets #integration
  - [ ] 🟢 P2 **WhatsAppChannel**: Plug-in adapter utilizing Twilio WhatsApp / Meta Cloud API (reusing identical payload & callback contracts validated on Telegram). #ux
