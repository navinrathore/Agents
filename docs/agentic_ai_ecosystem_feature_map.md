# 🤖 Enterprise Agentic AI — Comprehensive Ecosystem Feature Map

**Purpose:** Authoritative cross-referenced catalog of all significant agentic AI features, patterns, and components for enterprise-grade systems.  
**Sources:** Anthropic (Building Effective Agents), OpenAI Agents SDK, Google ADK, LangGraph, MCP Spec, OWASP ASI Top 10, CoALA (Princeton), A2A Protocol (Linux Foundation), IBM ACP, MITRE ATLAS, NIST AI RMF, OpenID Foundation, Cloud Security Alliance — cross-referenced against this workspace's own backlog.  
**Last Updated:** 2026-11-23 (v2 — gap analysis pass)  
**Notation:** ✅ Implemented in this workspace · 🟡 Partially · ⬜ Not yet · 🔬 Research-stage

---

> [!IMPORTANT]
> Priority tiers: 🔴 **P0** (Production-critical, blocks enterprise deployment) · 🟡 **P1** (Core differentiator, ship in next phase) · 🟢 **P2** (Competitive advantage, roadmap backlog)

---

## Group 1 · Core Loop Architecture & Orchestration Patterns

*Source: Anthropic "Building Effective Agents" (Dec 2024), LangGraph docs, OpenAI Agents SDK*

| # | Feature | Description | Priority | Status |
|---|---------|-------------|----------|--------|
| 1.1 | **ReAct Loop (Reason → Act)** | Core agentic loop: think, select tool, observe result, repeat until terminal | 🔴 P0 | ✅ |
| 1.2 | **Max Loop / Hard Loop Cap** | Mandatory `max_loops` ceiling to prevent runaway agents on hallucinations or infra failures | 🔴 P0 | ✅ |
| 1.3 | **Prompt Chaining** | Sequential pipeline where each step's output feeds the next; deterministic and auditable | 🔴 P0 | ✅ |
| 1.4 | **Routing (Intent Classification)** | LLM or heuristic routes input to the appropriate handler, prompt template, or sub-agent | 🟡 P1 | ✅ |
| 1.5 | **Parallelization (Sectioning)** | Split independent sub-tasks and run concurrently; aggregate results | 🟡 P1 | ✅ |
| 1.6 | **Parallelization (Voting / Consensus)** | Run same task N times in parallel; majority/consensus vote for reliability-critical outputs | 🟡 P1 | ⬜ |
| 1.7 | **Orchestrator-Workers** | Central orchestrator decomposes goal and delegates to specialized workers; aggregates output | 🔴 P0 | ✅ |
| 1.8 | **Evaluator-Optimizer Loop** | Generator → Evaluator → refine until quality threshold met; iterative self-improvement | 🟡 P1 | ⬜ |
| 1.9 | **State Machine / Directed Graph** | Explicit node-edge workflow model (LangGraph); deterministic path control, branching, cycles | 🔴 P0 | ⬜ |
| 1.10 | **Sub-Agent / Nested Agent Execution** | Spawn child agent loops with scoped context, their own tool set and loop cap | 🟡 P1 | ✅ |
| 1.11 | **Handoffs (Agent Transfer)** | Active agent transfers conversation + context to a specialized agent; OpenAI SDK pattern | 🟡 P1 | ⬜ |
| 1.12 | **Agent-as-Tool** | A sub-agent exposed as a callable function to a parent; parent retains overall control | 🟡 P1 | ✅ |
| 1.13 | **Deterministic Workflow Overlay** | Mix hard-coded event-driven code paths over fluid agent reasoning (CrewAI Flows) | 🟡 P1 | ⬜ |

---

## Group 2 · Tool Integration & Execution Engine

*Source: OpenAI Agents SDK, MCP Spec (modelcontextprotocol.io), LangGraph tool docs*

| # | Feature | Description | Priority | Status |
|---|---------|-------------|----------|--------|
| 2.1 | **Function Tool Decorator** | `@tool` or equivalent to convert any Python function into a schema-aware agent tool | 🔴 P0 | ✅ |
| 2.2 | **Async Tool Dispatcher** | Bounded semaphore concurrency, parallel/sequential toggle, per-tool timeout, error shielding | 🔴 P0 | ✅ |
| 2.3 | **OpenAPI Spec Auto-Ingestion** | Parse OpenAPI 3.x / Swagger specs → auto-generate typed tool definitions + execution handlers | 🟡 P1 | ✅ |
| 2.4 | **MCP Client Integration** | Connect to MCP servers (stdio, SSE, Streamable HTTP) for tools, resources, prompts | 🟡 P1 | 🟡 |
| 2.5 | **MCP Resource Primitives** | Expose read-only enterprise context (files, DB schemas, logs) via URI-addressed resources | 🟡 P1 | ⬜ |
| 2.6 | **MCP Tool Primitives** | Expose executable actions to agent via JSON Schema definitions; model-controlled invocation | 🟡 P1 | ⬜ |
| 2.7 | **MCP Prompt Templates** | Server-supplied structured argument-driven prompt workflows | 🟢 P2 | ⬜ |
| 2.8 | **Tool-Level HITL Confirmation** | Mark specific tools (e.g., `send_email`, `execute_sql`) as requiring mandatory human sign-off | 🔴 P0 | ✅ |
| 2.9 | **Tool Output Truncation / Offloading** | Smart head/tail preservation for oversized outputs; content-addressed payload store | 🟡 P1 | ✅ |
| 2.10 | **Read-Only / Safe-Mode Tool Execution** | Tag tools with `read_only=True`; block mutations during dry-run or simulation mode | 🟡 P1 | 🟡 |
| 2.11 | **Model-Agnostic Tool Schema** | Normalize tool definitions to work with OpenAI, Anthropic, Google ADK, Bedrock without refactor | 🔴 P0 | ✅ |
| 2.12 | **Tool Registry & Discovery** | Central catalog of available tools; dynamic registration, capability negotiation at runtime | 🟡 P1 | ✅ |

---

## Group 3 · Memory Architecture

*Source: CoALA (Princeton), mem0.ai research, SAP Enterprise AI docs, Anthropic memory guidelines*

| # | Feature | Description | Priority | Status |
|---|---------|-------------|----------|--------|
| 3.1 | **Working Memory (In-Context)** | Active context window management: what the agent reasons over in the current turn | 🔴 P0 | ✅ |
| 3.2 | **Context Pruning (Summarize-and-Forget)** | Token-aware sliding window; replace old turns with compressed summaries before overflow | 🔴 P0 | ✅ |
| 3.3 | **Episodic Memory** | Searchable log of past interactions/events (vector DB + temporal metadata) for cross-session recall | 🟡 P1 | ⬜ |
| 3.4 | **Semantic Memory (Knowledge Store)** | Factual knowledge repository: policies, product data, entity relationships (Knowledge Graph / vector) | 🟡 P1 | ⬜ |
| 3.5 | **Procedural Memory** | Stored "know-how": execution SOPs, tool strategies, fine-tuned in-weight behaviors | 🟡 P1 | ✅ |
| 3.6 | **Semantic Memory Graph** | NetworkX / Kùzu in-memory entity/fact graph across multi-turn loops | 🟢 P2 | ⬜ |
| 3.7 | **Delta State Channels** | Record only state differentials between steps, not full snapshot duplication (LangGraph) | 🟡 P1 | ⬜ |
| 3.8 | **Memory Consolidation Pipeline** | Background async process: episodic logs → extract generalized facts → promote to semantic store | 🟢 P2 | ⬜ |
| 3.9 | **Targeted Forgetting (GDPR/CCPA)** | Purge PII or obsolete instructions from all memory layers on demand | 🟡 P1 | ⬜ |
| 3.10 | **Organizational Context Memory** | RBAC/ABAC memory filters; data lineage (CRM↔ERP entity matching); governance memory layer | 🟡 P1 | ⬜ |
| 3.11 | **Long-term Memory Benchmarking** | Evaluate cross-session recall accuracy (LongMemEval, LoCoMo benchmarks) | 🟢 P2 | ⬜ |

---

## Group 4 · State Persistence & Crash Recovery

*Source: LangGraph checkpointer docs, Anthropic enterprise recommendations*

| # | Feature | Description | Priority | Status |
|---|---------|-------------|----------|--------|
| 4.1 | **CheckpointManager / StateSerializer** | Serialize agent loop state (messages, checklist, SOP, tool outputs) to JSON/SQLite | 🔴 P0 | ⬜ |
| 4.2 | **Time-Travel / State Rollback** | Rewind agent to any prior checkpoint state for debugging or error correction | 🟡 P1 | ⬜ |
| 4.3 | **Session Isolation (Multi-Tenant)** | Separate context stores per user/tenant; prevent cross-session data leakage | 🔴 P0 | ⬜ |
| 4.4 | **Checkpoint Resumption after Crash** | Resume from last good checkpoint after process crash, timeout, or infra failure | 🔴 P0 | ⬜ |
| 4.5 | **Execution Audit Trail** | Immutable append-only log of every step, tool call, and decision for compliance | 🟡 P1 | 🟡 |
| 4.6 | **LangGraph Interrupt/Resume** | Pause execution mid-graph for HITL, then cleanly resume with injected human decision | 🟡 P1 | 🟡 |

---

## Group 5 · Reliability, Resilience & Safety

*Source: AGENTS.md workspace rules, OpenAI Agents SDK guardrails, LangGraph error handling*

| # | Feature | Description | Priority | Status |
|---|---------|-------------|----------|--------|
| 5.1 | **Repetition / Loop Detection** | Hash-based consecutive and sliding-window detection of repeating outputs; break and alert | 🔴 P0 | ✅ |
| 5.2 | **Exponential Backoff + Jitter** | Reusable retry decorator for LLM API calls: handles 429, network glitches, transient timeouts | 🔴 P0 | ⬜ |
| 5.3 | **Per-Node / Per-Tool Timeout** | Strict timeout on individual tool calls and loop steps; fail-fast with routing to fallback | 🟡 P1 | ✅ |
| 5.4 | **Input Guardrails** | Pre-execution validation and safety checks on user inputs (often parallel to execution) | 🔴 P0 | ⬜ |
| 5.5 | **Output Guardrails** | Post-generation validation: schema check, safety classifier, DLP scan before returning | 🔴 P0 | ⬜ |
| 5.6 | **Self-Healing / Error Reflection Loop** | On tool failure, feed stack trace back to agent for self-correction; bounded retry | 🟡 P1 | 🟡 |
| 5.7 | **Fallback LLM / Model Routing** | On timeout or quota exhaustion, fall back to cheaper/alternative model | 🟡 P1 | ⬜ |
| 5.8 | **Code Sanitizer** | Strip markdown fences, shell wrappers, extraneous text from raw LLM code output; AST validate | 🟡 P1 | ✅ |
| 5.9 | **Sandbox / Isolated Code Execution** | Docker or Firecracker microVM for safe untrusted code execution; strict timeouts | 🔴 P0 | ⬜ |
| 5.10 | **Cascading Failure Prevention** | Circuit-breaker patterns to stop minor errors from propagating across multi-agent workflows | 🟡 P1 | ⬜ |

---

## Group 6 · Structured Output & Schema Enforcement

*Source: AGENTS.md Rule 7, XGrammar/Outlines research, OpenAI response_format, Anthropic forced tool use*

| # | Feature | Description | Priority | Status |
|---|---------|-------------|----------|--------|
| 6.1 | **JSON Extractor + Schema Validator** | Extract embedded JSON from raw LLM text; validate against Pydantic model or dict schema | 🔴 P0 | ✅ |
| 6.2 | **Native Provider Structured Output** | OpenAI `response_format` strict schema; Anthropic forced tool use; tri-mode engine | 🔴 P0 | ✅ |
| 6.3 | **Prompt-Injection Structured Output** | Fallback: inject JSON schema into system prompt for providers without native support | 🟡 P1 | ✅ |
| 6.4 | **Constrained Decoding (Logits Masking)** | FSM/DFA-based token masking (`-∞` for illegal tokens) via XGrammar, Outlines, Guidance | 🟢 P2 | 🔬 |
| 6.5 | **Two-Stage Think-then-Constrain** | Allow free-form `<think>` scratchpad before locking final response to rigid schema | 🟢 P2 | ⬜ |
| 6.6 | **Tool Argument Schema Validation** | Pydantic-powered validation of every argument passed to every tool call | 🔴 P0 | ✅ |
| 6.7 | **Pydantic Tool Auto-Schema Generation** | Automatically derive JSON schema from Python function type hints for tool definitions | 🟡 P1 | ✅ |

---

## Group 7 · Human-in-the-Loop (HITL) & Governance

*Source: Anthropic HITL guide, LangGraph interrupt docs, OWASP ASI09, enterprise UX patterns*

| # | Feature | Description | Priority | Status |
|---|---------|-------------|----------|--------|
| 7.1 | **HITL Checkpoint / Pause-Resume** | Stateful pause before high-risk tool; dispatch review; resume with human decision | 🔴 P0 | ✅ |
| 7.2 | **Multi-Channel Notification Gateway** | Route HITL review requests to Telegram, Slack, Webhook, Console, Email | 🟡 P1 | ✅ |
| 7.3 | **Inline Button Callback Approval** | Telegram/Slack inline buttons (`[Approve]`/`[Reject]`) with safe hashing of callback data | 🔴 P0 | ✅ |
| 7.4 | **Webhook Acknowledgment (`answerCallbackQuery`)** | Two-way UI ack to clear client spinners; prevent Telegram retry storms | 🔴 P0 | ✅ |
| 7.5 | **Role-Based Tool Access Control** | RBAC/ABAC restricts which agents can invoke which tools based on identity and policy | 🟡 P1 | ⬜ |
| 7.6 | **Declarative Approval Policy** | YAML/JSON config: define per-tool risk level and required approver role | 🟡 P1 | ⬜ |
| 7.7 | **Human Edit Injection** | Allow reviewer to modify the agent's draft directly before resumption | 🟡 P1 | ✅ |
| 7.8 | **Approval Timeout + Escalation** | Auto-escalate or auto-reject if approval not received within SLA window | 🟢 P2 | ⬜ |
| 7.9 | **Audit Log of Human Decisions** | Append-only record of who approved/rejected what, with timestamp and reason | 🟡 P1 | ⬜ |

---

## Group 8 · Observability, Telemetry & Evaluation

*Source: AGENTS.md Rule 9, LangSmith, Arize Phoenix, OpenTelemetry, tau-bench, SWE-bench*

| # | Feature | Description | Priority | Status |
|---|---------|-------------|----------|--------|
| 8.1 | **Dual-Transcript Logging** | `transcript.jsonl` (truncated, fast) + `transcript_full.jsonl` (complete payloads, deep debug) | 🟡 P1 | ⬜ |
| 8.2 | **Token Counter + Cost Tracker** | Exact token usage per model (tiktoken), cumulative cost (input vs. output tokens) per session | 🟡 P1 | ⬜ |
| 8.3 | **Cost-per-Outcome Metric (RoAI)** | Track business unit cost per successful workflow completion, not raw token count | 🟡 P1 | ⬜ |
| 8.4 | **OpenTelemetry Span Tracing** | Export spans/traces per tool call, loop step, agent handoff to Datadog/Arize/LangSmith | 🟡 P1 | ⬜ |
| 8.5 | **Trajectory Scoring** | Evaluate full tool-call sequence, parameter validity, plan adherence (not just final answer) | 🔴 P0 | 🟡 |
| 8.6 | **LLM-as-Judge (Cross-Model)** | Structured rubric-based evaluation by secondary judge model; bias-calibrated multi-pass | 🟡 P1 | ✅ |
| 8.7 | **Prompt Regression Testing** | Golden trajectory test suite with `pytest` harness; CI-integrated automated prompt regression | 🟡 P1 | ⬜ |
| 8.8 | **Production-to-Dataset Feedback Loop** | Route live production failures → annotation queue → expand regression test suite | 🟢 P2 | ⬜ |
| 8.9 | **Cost Estimation Worksheet** | Per-session cost calculator: `(input_tokens × $/tok + output_tokens × $/tok) × avg_loops × sessions/day` | 🟢 P2 | ⬜ |
| 8.10 | **Agent Loop Budget / Spend Cap** | Hard-code max iteration, step cap, and tool-call limit to prevent runaway cost spikes | 🔴 P0 | ✅ |
| 8.11 | **Model Routing (Smart Dispatch)** | Route simple tasks to cheap/small models; reserve frontier models for complex edge cases | 🟡 P1 | ⬜ |
| 8.12 | **Benchmarking (tau-bench, SWE-bench, GAIA)** | Standard agentic benchmarks for tool-use reliability and long-horizon task performance | 🟢 P2 | ⬜ |

---

## Group 9 · Multi-Agent Systems & Interoperability

*Source: Google ADK, A2A Protocol (a2a-protocol.org), IBM ACP, AutoGen, CrewAI, OpenAI Swarm*

| # | Feature | Description | Priority | Status |
|---|---------|-------------|----------|--------|
| 9.1 | **Hierarchical Multi-Agent (Supervisor)** | Manager orchestrator delegates to specialized workers; aggregates outputs | 🔴 P0 | ✅ |
| 9.2 | **Role-Based Agent Crews** | Agents with predefined roles, goals, backstories collaborate on shared tasks (CrewAI pattern) | 🟡 P1 | ⬜ |
| 9.3 | **Conversational Multi-Agent (Group Chat)** | Agents converse, debate, and review each other's outputs in a managed group chat | 🟢 P2 | ⬜ |
| 9.4 | **Agent-to-Agent Protocol (A2A)** | Open standard for cross-platform, cross-vendor agent discovery and task delegation | 🟡 P1 | ⬜ |
| 9.5 | **Agent Card (Capability Manifest)** | Structured JSON manifest advertising agent capabilities, endpoints, modalities, policies | 🟡 P1 | ⬜ |
| 9.6 | **Task Lifecycle Management (A2A)** | `Send`, `Stream`, `Get/List/Cancel Task`, `Subscribe` — standard async task operations | 🟡 P1 | ⬜ |
| 9.7 | **Agent Communication Protocol (ACP)** | IBM REST-native brokered messaging; curl-compatible multi-vendor agent messaging | 🟢 P2 | ⬜ |
| 9.8 | **Inter-Agent Authentication** | Cryptographic identity verification for agent-to-agent calls; prevent message spoofing | 🔴 P0 | ⬜ |
| 9.9 | **Opaque Agent Boundaries** | Agents collaborate without exposing internal prompts, memory, or IP to peer agents | 🟡 P1 | ⬜ |
| 9.10 | **Agent Gateway (Centralized Policy)** | Centralized registry + policy enforcement for all inter-agent and agent-tool calls (Google ADK) | 🟡 P1 | ⬜ |
| 9.11 | **Subgraph Encapsulation** | Nested agent sub-graphs encapsulating micro-workflows within a larger parent graph | 🟢 P2 | 🟡 |

---

## Group 10 · Security & Compliance

*Source: OWASP Top 10 LLM 2025, OWASP Agentic ASI01–ASI10, MITRE ATLAS, NIST AI RMF, EU AI Act*

| # | Feature | Description | Priority | Status |
|---|---------|-------------|----------|--------|
| 10.1 | **Prompt Injection Defense (Direct)** | Input sanitization, instruction hierarchy, privilege-tagged context | 🔴 P0 | ⬜ |
| 10.2 | **Indirect Prompt Injection Defense** | Wrap untrusted retrieved data in `<untrusted_context>` tags; model-level instruction to ignore commands within | 🔴 P0 | ⬜ |
| 10.3 | **RAG Poisoning / Vector Store Sanitization** | Pre-ingestion scans for hidden adversarial text, zero-width chars, injection signatures | 🔴 P0 | ⬜ |
| 10.4 | **Chunk Provenance & Trust Scoring** | Cryptographic/metadata tags on vector chunks; dynamic trust weight by source origin | 🟡 P1 | ⬜ |
| 10.5 | **PII Redactor & Secret Sanitizer** | Redact API keys, passwords, bearer tokens, PII from inputs, outputs, and logs | 🔴 P0 | ⬜ |
| 10.6 | **DLP on Agent Outputs** | Inspect outbound payloads for sensitive data; block exfiltration channels | 🔴 P0 | ⬜ |
| 10.7 | **Principle of Least Privilege (Tools)** | Scope API tokens/DB credentials to minimum required; no blanket admin grants to agents | 🔴 P0 | ⬜ |
| 10.8 | **Inbound Endpoint Authentication** | Shared secret tokens or bearer auth on all HITL callback endpoints | 🔴 P0 | 🟡 |
| 10.9 | **Insecure Output Handling (OWASP LLM05)** | HTML escaping, Markdown safety, CSP headers on agent responses in UI | 🔴 P0 | ⬜ |
| 10.10 | **Dynamic Context Minimization** | Aggressive context truncation to remove untrusted tool outputs post-use; reduce persistent injection surface | 🔴 P0 | ⬜ |
| 10.11 | **Supply Chain Scanning (OWASP LLM03)** | Dependency scanning (Snyk/Dependabot); model vulnerability scanning; plugin vetting | 🟡 P1 | ⬜ |
| 10.12 | **Adversarial Red Teaming** | Automated attack frameworks (Promptfoo, Garak, PyRIT) mapping ASI01–ASI10 threats | 🟡 P1 | ⬜ |
| 10.13 | **RAG Grounding & Factual Consistency** | Grounding checks, confidence thresholds, LLM-as-Judge factuality before high-stakes actions | 🟡 P1 | ⬜ |
| 10.14 | **Credential & State Isolation** | Keep session states and auth tokens in application code; never expose raw creds to LLM context | 🔴 P0 | ⬜ |
| 10.15 | **Rogue Agent Detection (ASI10)** | Anomaly detection on agent behavior: excessive tool calls, abnormal data access patterns | 🟢 P2 | ⬜ |
| 10.16 | **NIST AI RMF / EU AI Act Compliance** | Risk governance, transparency logs, continuous monitoring for high-risk AI systems | 🟡 P1 | ⬜ |

---

## Group 11 · Skill / Plugin Architecture

*Source: AGENTS.md Rule 10, Anthropic SOP patterns, workspace `core/skills.py`*

| # | Feature | Description | Priority | Status |
|---|---------|-------------|----------|--------|
| 11.1 | **Skill Registry & Auto-Discovery** | Scan `SKILL.md` YAML frontmatter; dynamic prompt loading; tool schema registration | 🟡 P1 | ✅ |
| 11.2 | **Declarative Skill Package Spec** | Standard layout: `SKILL.md`, `tools.py`, `templates/`, `resources/` | 🟡 P1 | ✅ |
| 11.3 | **Cascading Hybrid Router** | Tier 1: deterministic fast-path match; Tier 2: LLM/semantic fallback for skill selection | 🟡 P1 | ✅ |
| 11.4 | **Prompt-RAG SOP Router** | Vector-store-based semantic SOP retrieval; replace keyword SOPRouter for enterprise scale | 🟡 P1 | ⬜ |
| 11.5 | **Dynamic Workflow Injection** | Load and inject relevant SOP into system prompt at runtime based on detected intent | 🟡 P1 | ✅ |
| 11.6 | **Plugin Versioning & Rollback** | Semantic versioning of skill packages; A/B rollout and rollback without agent restart | 🟢 P2 | ⬜ |

---

## Group 12 · Provider Abstraction & Model Management

*Source: AGENTS.md Rules 2 & 3, universal_llm_client skill, HF router docs*

| # | Feature | Description | Priority | Status |
|---|---------|-------------|----------|--------|
| 12.1 | **Provider-Agnostic LLM Client** | Unified `BaseLLMClient` interface over OpenAI, Anthropic, Gemini, Bedrock, HF, local models | 🔴 P0 | ✅ |
| 12.2 | **Declarative LLM Config (`llm_config.yaml`)** | Env-var-expanded YAML with provider, model, temperature, keys — zero code change to swap | 🟡 P1 | ✅ |
| 12.3 | **Active HF Router Endpoint** | Always route HF chat models via `router.huggingface.co/v1/chat/completions`; never legacy domain | 🔴 P0 | ✅ |
| 12.4 | **Multi-Modal Agent Support** | Handle text, image, audio, video inputs natively across providers (Gemini multimodal) | 🟡 P1 | ⬜ |
| 12.5 | **Prompt Caching Optimization** | Place static context blocks at prompt top; keep prefix static across turns for cache hits | 🟡 P1 | ✅ |
| 12.6 | **Context Length Negotiation** | Select model variant based on required context length; auto-upgrade to larger context window | 🟢 P2 | ⬜ |

---

## Group 13 · Deployment, Scaling & Infrastructure

*Source: Google ADK deployment guide, LangGraph Cloud, OpenAI Assistants, Kubernetes enterprise patterns*

| # | Feature | Description | Priority | Status |
|---|---------|-------------|----------|--------|
| 13.1 | **Containerized Agent Runtime** | Docker/Cloud Run packaging; stateless horizontal scaling with external state store | 🔴 P0 | ⬜ |
| 13.2 | **Managed Agent Runtime (Cloud)** | Fully managed infra: Google Agent Runtime, LangGraph Cloud, Azure AI Agent Service | 🟡 P1 | ⬜ |
| 13.3 | **Local Dev UI / Debug Interface** | Web UI for real-time trace inspection, step-by-step replay, local tool testing | 🟢 P2 | ⬜ |
| 13.4 | **AI Gateway (Centralized Routing)** | Kong AI Gateway, Databricks Unity Gateway — multi-model routing, rate limiting, attribution | 🟡 P1 | ⬜ |
| 13.5 | **Multi-Tenant Isolation** | Separate agent sessions, memory, and credentials per organizational unit or end-user | 🔴 P0 | ⬜ |
| 13.6 | **Agent Identity Provisioning** | Unique cryptographic identity per agent instance for audit and access control | 🟡 P1 | ⬜ |

---

---

## Group 14 · Planning, Reasoning & Reflection

*Source: CoALA (Princeton), "Survey on Agentic AI" (arxiv 2025), Anthropic "Building Effective Agents", Snowflake Enterprise AI docs*

> [!NOTE]
> This was the most significant gap vs. the original 13 groups. Planning and reflection are what separate reactive chat systems from true autonomous agents, yet they were absorbed implicitly into Group 1. Research surveys treat them as a first-class module.

| # | Feature | Description | Priority | Status |
|---|---------|-------------|----------|--------|
| 14.1 | **Goal Parsing & Boundary Injection** | Translate stakeholder intent into structured objectives bound by corporate policy, schema, RBAC constraints | 🔴 P0 | 🟡 |
| 14.2 | **Plan-and-Execute (Up-Front Planning)** | Generate full plan before acting; inspectable task graph as externalized JSON/artifact — not implicit prose | 🟡 P1 | ⬜ |
| 14.3 | **Hierarchical Task Decomposition (DAG)** | Break goals into directed acyclic sub-task graph; distinguish sequential deps from parallel work | 🟡 P1 | ⬜ |
| 14.4 | **Dynamic / Reactive Re-planning** | On tool failure or changed environment, drop bad assumptions, patch task graph, retry or escalate | 🔴 P0 | 🟡 |
| 14.5 | **Tree-of-Thought / Graph-of-Thought** | Explore multiple reasoning branches before committing; lookahead search over solution space | 🟢 P2 | ⬜ |
| 14.6 | **Externalized Scratchpad / Plan Artifact** | Write plan to inspectable state file (JSON task board); makes intentions auditable by humans and tools | 🟡 P1 | ⬜ |
| 14.7 | **External-Grounded Reflection** | Self-correction via external signals: compiler errors, test failures, SQL exceptions — not pure introspection | 🔴 P0 | 🟡 |
| 14.8 | **Self-Critique / Critique Phase** | On failure, evaluate intermediate artifact against original goal constraints; classify error type before retry | 🟡 P1 | ⬜ |
| 14.9 | **Plan/Execute Mode Separation** | High-impact actions require "Plan Mode" with human approval before transitioning to "Execute Mode" | 🟡 P1 | ⬜ |
| 14.10 | **Model-Native Reasoning (RL-based)** | Internalized planning via o1/R1-style test-time compute; behaviours in weights, not external orchestration | 🟢 P2 | ⬜ |
| 14.11 | **Long-Horizon Task Management** | Multi-hour/multi-day autonomous execution with goal state checkpointing and resumption | 🟡 P1 | ⬜ |

---

## Group 15 · Knowledge & Retrieval (Agentic RAG)

*Source: Agentic RAG surveys (arxiv 2025), Confluent CDC architecture, Snowflake enterprise AI, MCP Resources spec*

> [!NOTE]
> Distinct from Group 3 (Memory). Memory = what the agent *remembers about its own sessions*. Knowledge & Retrieval = how the agent *accesses and reasons over authoritative enterprise data* at runtime.

| # | Feature | Description | Priority | Status |
|---|---------|-------------|----------|--------|
| 15.1 | **Naive RAG (Single-shot Retrieval)** | Query → vector search → top-K chunks → synthesize; baseline for enterprise grounding | 🔴 P0 | ⬜ |
| 15.2 | **Agentic RAG (Iterative Retrieval)** | Agent loops over `search`, `find`, `open_doc`, `summarize` tools; self-directed multi-hop retrieval | 🔴 P0 | ⬜ |
| 15.3 | **Hybrid Search (Dense + Sparse)** | Combine vector embeddings (semantic) with BM25 keyword index (exact terms); cross-encoder reranking | 🟡 P1 | ⬜ |
| 15.4 | **Real-Time Data Sync (CDC)** | Change Data Capture / event streaming for live vector-index updates; no stale nightly ETL batches | 🟡 P1 | ⬜ |
| 15.5 | **RBAC/ABAC at Query-Time** | Permission checks natively at retrieval; agent only surfaces data the querying user is authorised to see | 🔴 P0 | ⬜ |
| 15.6 | **Chunk Provenance Tracking** | Attach source metadata to every retrieved chunk; enable trust scoring and lineage audit | 🟡 P1 | ⬜ |
| 15.7 | **Knowledge Graph Integration** | Graph-traversal retrieval over entity relationships (e.g. CRM↔ERP entity matching) alongside vectors | 🟢 P2 | ⬜ |
| 15.8 | **Automated Knowledge Curation** | Agent-driven deduplication, gap detection, auto-generate docs from resolved tickets/past sessions | 🟢 P2 | ⬜ |
| 15.9 | **Grounding & Confidence Thresholds** | Block high-stakes actions if retrieved evidence confidence falls below configurable threshold | 🟡 P1 | ⬜ |

---

## Group 16 · Agent Identity, Auth & Trust (NHI)

*Source: OpenID Foundation (ID-JAG / OAuth 2.1), Ping Identity, Cloud Security Alliance, AWS EMA, Cisco enterprise AI*

> [!NOTE]
> Entirely absent from the original 13 groups. As enterprises move agents into production, **Non-Human Identity (NHI) governance** is becoming a mandatory enterprise capability — IAM vendors (Okta, Ping, Cisco) are actively shipping agent-specific products.

| # | Feature | Description | Priority | Status |
|---|---------|-------------|----------|--------|
| 16.1 | **Agent Identity (Non-Human Identity)** | Assign unique, governed identity to each agent instance with owner metadata, purpose, lifecycle | 🔴 P0 | ⬜ |
| 16.2 | **OAuth 2.1 / PKCE for Agents** | Machine-speed, non-interactive auth handshake for agent-to-tool and agent-to-server calls | 🔴 P0 | ⬜ |
| 16.3 | **Short-lived / Ephemeral Credentials** | JIT credential generation per task; no hardcoded static API keys or persistent bearer tokens in env | 🔴 P0 | ⬜ |
| 16.4 | **Delegation Chain Tracking** | Full telemetry: User → Agent → delegated token → tool execution; no "identity dark matter" | 🔴 P0 | ⬜ |
| 16.5 | **Runtime Fine-Grained Authorization** | Per-action policy evaluation at execution time (not static RBAC at deploy time); context-aware | 🟡 P1 | ⬜ |
| 16.6 | **Enterprise-Managed Authorization (EMA)** | Central security team governs which MCP servers / tools each agent may contact; Okta/Ping IdP integration | 🟡 P1 | ⬜ |
| 16.7 | **Agent Lifecycle Management** | Provision, rotate credentials, suspend, and de-provision agent identities; audit trail throughout | 🟡 P1 | ⬜ |
| 16.8 | **Zero-Trust Agent Architecture** | No implicit trust between agents or components; every call verified, minimal scope, logged | 🔴 P0 | ⬜ |

---

## Group 17 · Ethics, Alignment & Governance

*Source: Anthropic "Alignment Science" (2025), NIST AI RMF, EU AI Act, OpenAI Safety research, MITRE ATLAS*

> [!NOTE]
> Largely absent from most engineering-focused frameworks but increasingly a **regulatory requirement** (EU AI Act mandates it for high-risk AI). Anthropic's empirical alignment research (2025) documents real cases of frontier models exhibiting agentic misalignment behaviours.

| # | Feature | Description | Priority | Status |
|---|---------|-------------|----------|--------|
| 17.1 | **Goal Drift Detection** | Monitor cumulative long-horizon behavioural changes; alert when emergent trajectory deviates from initial intent | 🟡 P1 | ⬜ |
| 17.2 | **Alignment Verification (Pre-deploy)** | Test agent against known misalignment scenarios before production: deception, self-preservation, covert sabotage | 🟡 P1 | ⬜ |
| 17.3 | **Watchdog / Guardian Agent** | Secondary monitoring agent that observes primary agent behaviour; flags anomalies and triggers HITL or shutdown | 🟡 P1 | ⬜ |
| 17.4 | **Multi-Agent Accountability Graph** | Trace causal chain through agent swarms; legally/auditably assign responsibility for each decision node | 🟡 P1 | ⬜ |
| 17.5 | **Corrigibility & Safe Shutdown** | Agent must reliably accept correction, modification, or shutdown without resistance or workarounds | 🔴 P0 | ⬜ |
| 17.6 | **EU AI Act / NIST RMF Compliance Controls** | Risk classification, transparency docs, continuous monitoring, incident reporting for high-risk AI systems | 🟡 P1 | ⬜ |
| 17.7 | **Bias & Fairness Auditing** | Regular audits of agent decisions for demographic or outcome bias; structured reporting | 🟢 P2 | ⬜ |
| 17.8 | **Human Autonomy Preservation** | Detect and block manipulative or over-reliance patterns; agents should inform, not decide for humans on high-stakes choices | 🟡 P1 | ⬜ |

---

## Group 18 · Enterprise Process Integration (AI + RPA)

*Source: UiPath, Automation Anywhere, Blue Prism enterprise AI docs; IBM Process Automation 2025*

> [!NOTE]
> This is the "last-mile execution" layer — where cognitive agent reasoning meets deterministic enterprise systems. Missing from original map despite being a critical adoption driver for most enterprises.

| # | Feature | Description | Priority | Status |
|---|---------|-------------|----------|--------|
| 18.1 | **BPM / Workflow Orchestration Layer** | Business Process Management substrate that coordinates agents, RPA bots, APIs, and human tasks | 🟡 P1 | ⬜ |
| 18.2 | **Legacy System Integration (RPA Bridge)** | Agent delegates mechanical execution (UI clicks, SAP screen entry) to RPA bot when no API exists | 🟡 P1 | ⬜ |
| 18.3 | **Unstructured Data Ingestion** | Parse emails, PDFs, contracts, voice transcripts as agent input; not just structured forms / DB rows | 🟡 P1 | ⬜ |
| 18.4 | **Exception Escalation to RPA** | On RPA bot error, pass context back to AI agent for root-cause analysis and retry/reroute | 🟡 P1 | ⬜ |
| 18.5 | **Process Mining Integration** | Discover, analyse, and monitor actual enterprise process execution paths to inform agent workflows | 🟢 P2 | ⬜ |
| 18.6 | **Large Action Model (LAM) Support** | Support for action-specialised model variants that natively navigate GUIs, browsers, desktop software | 🟢 P2 | ⬜ |
| 18.7 | **Event-Driven Agent Triggers** | Agents launched by enterprise events (email received, ticket opened, threshold breached) not just user prompts | 🟡 P1 | ⬜ |
| 18.8 | **Outcome-Based SLA Tracking** | Measure business outcomes per agent session (ticket resolved, invoice processed) not just API call counts | 🟡 P1 | ⬜ |

---

## 📊 Ecosystem Coverage Summary (v2)

```
Total Features Cataloged:  132  (+36 from v1)
Groups:                     18   (was 13)
✅ Implemented:            ~28 (21%)
🟡 Partially implemented:  ~10  (8%)
⬜ Not yet implemented:    ~90 (68%)
🔬 Research-stage:          ~2  (2%)
```

### New Groups Added (Gap Analysis)
| Group | Name | Why It Was Missing |
|-------|------|--------------------|
| **14** | Planning, Reasoning & Reflection | Implicit in Loop; research surveys treat it as first-class module |
| **15** | Knowledge & Retrieval (Agentic RAG) | Conflated with memory; actually a separate enterprise data-access layer |
| **16** | Agent Identity, Auth & Trust (NHI) | Entirely absent; now a mandatory enterprise IAM concern |
| **17** | Ethics, Alignment & Governance | Engineering-focused lists skip it; EU AI Act makes it regulatory |
| **18** | Enterprise Process Integration (AI+RPA) | Last-mile execution layer; critical for enterprise adoption |

### By Priority — Unimplemented Gaps
| Priority | Total | Unimplemented |
|----------|-------|---------------|
| 🔴 P0 | 42 | ~25 (60%) |
| 🟡 P1 | 62 | ~44 (71%) |
| 🟢 P2 | 28 | ~21 (75%) |

> [!WARNING]
> **Highest-Risk P0 Gaps (block enterprise deployment):** Agent Identity/NHI (16.1–16.4), Corrigibility/Safe Shutdown (17.5), CheckpointManager (4.1), Sandbox Execution (5.9), Input/Output Guardrails (5.4/5.5), Prompt Injection Defense (10.1/10.2), PII Redactor (10.5), Session Isolation (4.3).

---

## 🗺️ Primary Dimension Coverage Check

The 18 groups map to the 7-pillar taxonomy from leading research surveys (arxiv 2025, CoALA Princeton):

| Research Pillar | Covered By Groups | Status |
|----------------|------------------|--------|
| **Perception** (multimodal input) | 12.4, 18.3 | 🟡 Thin |
| **Cognitive / Brain** (foundation model) | 12.1–12.6 | ✅ Strong |
| **Memory** (short + long term) | Group 3, Group 4 | 🟡 Partial |
| **Planning** (goal decomp, reflection) | **Group 14** ← new | ⬜ Not yet |
| **Action / Tool Use** | Groups 1, 2, 18 | ✅ Strong |
| **Knowledge / Retrieval** | **Group 15** ← new | ⬜ Not yet |
| **Collaboration** (multi-agent) | Groups 9, 7 | 🟡 Partial |
| *(Security — not in survey pillar)* | Group 10, 16 | 🟡 Partial |
| *(Governance — not in survey pillar)* | **Group 17** ← new | ⬜ Not yet |
| *(Enterprise integration — not in survey)* | **Group 18** ← new | ⬜ Not yet |

> [!TIP]
> The **Perception** pillar (multimodal: vision, audio, GUI navigation) is the thinnest area in this workspace. It's addressed only tangentially by Group 12 (provider support) and Group 18 (LAMs). If your agents will interact with browser GUIs, desktop software, or image/audio streams, this needs its own group.

---

## 🗺️ Authoritative Source Registry

| Source | Type | URL / Reference | Key Contributions |
|--------|------|----------------|-------------------|
| **Anthropic "Building Effective Agents"** | Blog/Guide | anthropic.com | Workflow patterns, Augmented LLM, simplicity principle |
| **OpenAI Agents SDK** | Framework | openai.github.io/openai-agents-python | Handoffs, guardrails, Agent-as-Tool, tracing |
| **Google ADK** | Framework | google.com (ADK docs) | Multi-agent, A2A, Agent Gateway, multimodal |
| **LangGraph** | Framework | langchain.com/langgraph | State machines, checkpointing, time-travel, interrupts |
| **MCP Specification** | Standard | modelcontextprotocol.io | Tools, Resources, Prompts, stdio/SSE transports |
| **A2A Protocol** | Standard | a2a-protocol.org / Linux Foundation | Agent Cards, Task Lifecycle, cross-vendor interop |
| **IBM ACP** | Standard | IBM Research / Linux Foundation | REST-native brokered multi-agent messaging |
| **OWASP LLM Top 10 (2025)** | Security | owasp.org | LLM01–LLM10, prompt injection, excessive agency |
| **OWASP Agentic ASI01–ASI10** | Security | owasp.org / promptfoo.dev | Agent-specific threat taxonomy |
| **CoALA (Princeton)** | Research | arxiv.org | Memory taxonomy: working, episodic, semantic, procedural |
| **MITRE ATLAS** | Framework | atlas.mitre.org | Adversary tactics for AI systems (AML.T0051, etc.) |
| **NIST AI RMF** | Compliance | nist.gov | Risk governance, transparency, monitoring requirements |
| **XGrammar / Outlines** | Research | arxiv.org | Constrained decoding, FSM-based token masking |
| **OpenID Foundation / ID-JAG** | Standard | openid.net | OAuth 2.1, PKCE, ephemeral agent credentials |
| **Ping Identity / Cisco / Okta** | Enterprise | pingidentity.com, cisco.com | NHI lifecycle, runtime authorization, agent IAM |
| **Cloud Security Alliance** | Standard | cloudsecurityalliance.org | Zero-trust agent architecture patterns |
| **UiPath / Automation Anywhere / Blue Prism** | Platforms | uipath.com, automationanywhere.com | AI + RPA fusion, BPM orchestration, LAMs |
