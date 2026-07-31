# 📋 Agent Design, Decision-Making & Implementation Checklist

> **Practical Engineering Blueprint & QA Audit Checklist** for designing, architecting, and evaluating autonomous AI agents. Built for Spec-Driven Agent Development and strictly aligned with workspace design principles.

---

## 📌 Table of Contents

- [🛡️ 1. Workspace Agent Design Rules (`AGENTS.md` Foundation)](#️-1-workspace-agent-design-rules-agentsmd-foundation)
  - [1.1 New Agent Developer Readiness Audit](#11-new-agent-developer-readiness-audit)
- [🚦 2. Input & Task Complexity Taxonomy Matrix](#-2-input--task-complexity-taxonomy-matrix)
- [🎨 3. Interactive Architectural & Safety Decision Trees](#-3-interactive-architectural--safety-decision-trees)
  - [3.1 Architecture Pattern Selection Tree](#31-architecture-pattern-selection-tree)
  - [3.2 Tool Execution & Sandboxing Safety Tree](#32-tool-execution--sandboxing-safety-tree)
  - [3.3 State Hydration & Memory Strategy Tree](#33-state-hydration--memory-strategy-tree)
  - [3.4 Guardrail & Token Tax Configuration Tree](#34-guardrail--token-tax-configuration-tree)
- [📜 4. Spec-Driven Agent Development Framework](#-4-spec-driven-agent-development-framework)
- [🔍 5. Design Review & QA Brainstorming Checklist (`/grill-me` Ready)](#-5-design-review--qa-brainstorming-checklist-grill-me-ready)
- [📋 6. The 8-Phase Agent Audit Checklist](#-6-the-8-phase-agent-audit-checklist)
- [🔥 7. Failure Modes & Debugging Playbook](#-7-failure-modes--debugging-playbook)
- [🏗️ 8. Worked Example: End-to-End Agent Build](#️-8-worked-example-end-to-end-agent-build)

---

## 🛡️ 1. Workspace Agent Design Rules (`AGENTS.md` Foundation)

When designing or implementing any agent in this workspace, strictly adhere to these 10 core engineering rules:

| # | Rule Name | Rationale & Practical Implementation Requirement |
| :-: | :--- | :--- |
| **1** | **ReAct Loop Safety (Hard Limits)** | Never write an unbounded autonomous `while` loop. Enforce a strict `max_loops` threshold (e.g., 10–15 iterations) and cycle detection to prevent infinite token burn during hallucinations or execution failures. |
| **2** | **Provider Agnosticism** | Abstract all LLM calls behind a unified interface (e.g., `BaseLLMClient`). Ensure seamless fallback or swapping between Anthropic, Hugging Face, OpenAI, or local models without modifying agent core logic. |
| **3** | **Conditional Guardrails (Token Tax)** | Do not blindly enforce rigid internal state-management tools (like an explicit `manage_checklist` tool) on frontier models. Make guardrails conditionally configurable (`use_checklist: false`) to toggle off overhead for smarter models. |
| **4** | **Execution Safety** | Default to safe code execution environments. Enforce strict subprocess timeouts (`timeout=30s`) and strongly recommend Docker or microVM sandboxing for production tool runs. |
| **5** | **Scope Management & Backlog Preservation** | When potential features or improvements arise during design/development, do not immediately write code for them. Record them in [backlog.md](file:///home/navin/work/AI/projects/Agents/docs/backlog.md) to prevent scope creep. |
| **6** | **Prompt Caching Friendliness** | Place large, static context blocks (system prompts, tool schemas, reference SOPs) at the very beginning of the prompt payload. Keep this prefix static across turns to maximize KV prompt caching. |
| **7** | **Structured Outputs & Schema Enforcement** | Never use custom string parsing or fragile regex to parse model responses or tool arguments. Define Pydantic models or JSON schemas to enforce structural validation at API boundaries. |
| **8** | **State Hydration and Resiliency** | Design long-running agents with external persistent state storage (`session_id`, checkpoints). Allow the agent control loop to resume cleanly from the last known checkpoint after a crash or restart. |
| **9** | **Structured Observability & Tracing** | Instrument agent execution with dual transcripts: a lightweight `transcript.jsonl` (truncated arguments for fast debugging) and `transcript_full.jsonl` (complete raw payloads for trajectory analysis). |
| **10** | **Declarative SOPs & Dynamic Injection** | Store specialized behaviors and workflows in declarative Markdown SOP files outside application code. Route and inject only the relevant SOP into the prompt based on user intent. |

### 1.1 New Agent Developer Readiness Audit

Use this quick verification checklist before deploying or running any new agent implementation:

- [ ] **Rule 1 (Loop Bounding)**: Is `max_loops` set to a hard threshold (10–15) in `agent.py`?
- [ ] **Rule 2 (Provider Agnosticism)**: Is `BaseLLMClient` used instead of calling model SDKs directly?
- [ ] **Rule 3 (Guardrail Toggle)**: Is `use_checklist` set to `false` by default for frontier models in `spec.yaml`?
- [ ] **Rule 4 (Execution Safety)**: Are subprocess executions configured with `timeout=30s`?
- [ ] **Rule 5 (Scope Control)**: Are missing/future features logged in `backlog.md` instead of implemented ad-hoc?
- [ ] **Rule 6 (Prompt Caching)**: Are static system prompts and tool schemas placed at the beginning of the prompt window?
- [ ] **Rule 7 (Structured Schemas)**: Are tool arguments defined using JSON Schema or Pydantic `BaseModel` classes?
- [ ] **Rule 8 (State Hydration)**: Are turn checkpoints serialized to disk/DB with a `session_id`?
- [ ] **Rule 9 (Dual Transcripts)**: Are both `transcript.jsonl` (short) and `transcript_full.jsonl` (full) being recorded?
- [ ] **Rule 10 (Declarative SOPs)**: Are domain procedures stored in external `/sops/*.md` files and injected dynamically?

---

## 🚦 2. Input & Task Complexity Taxonomy Matrix

Use this matrix to categorize incoming requests and determine the minimal necessary architecture.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          INPUT & TASK TAXONOMY                              │
│                                                                             │
│   Input Structure      Output Determinism     Sequence      Architecture    │
│   ────────────────    ────────────────────    ────────     ──────────────   │
│   Single-Step/Structured ──► Deterministic ──► Pre-Known ──► Direct Call / FSM │
│   Multi-Step/Unstructured ──► Open-Ended ────► Exploratory ─► ReAct / Multi-Agent│
└─────────────────────────────────────────────────────────────────────────────┘
```

| Complexity Level | Input Characteristic | Output Requirement | Tool Needs | Recommended Pattern | Avoid |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Level 0: Direct Call** | Single-shot text, JSON, or form input. | 100% structured (extract, classify, translate). | No tools needed. | **Single LLM API Call** (with Pydantic `response_format`) | Agent loops, state tracking, multi-turn prompts. |
| **Level 1: FSM / DAG** | Multi-step input, fixed workflow rules. | Deterministic sequence of transformations. | Fixed step execution (e.g. fetch DB, run rule, send email). | **Finite State Machine / DAG** (LangGraph, hardcoded step code) | Autonomous ReAct loops where the LLM decides the next step. |
| **Level 2: ReAct Agent** | Open-ended query, dynamic data files, research tasks. | Variable / exploratory answer backed by evidence. | Dynamic tool selection (SQL, Bash, Python, Web Search). | **Bounded ReAct Control Loop** (`max_loops` = 10–15) | Multi-agent coordination overhead if single agent context fits. |
| **Level 3: Multi-Agent** | Multi-domain scope, massive inputs, conflicting roles. | Comprehensive synthesis across specialized sub-domains. | Domain-isolated tool sets per agent. | **Hierarchical Multi-Agent** (Planner + Specialized Workers) | Single monolithic system prompt trying to do everything. |

---

## 🎨 3. Interactive Architectural & Safety Decision Trees

### 3.1 Architecture Pattern Selection Tree

```mermaid
flowchart TD
    classDef startNode fill:#1E293B,stroke:#64748B,stroke-width:2px,color:#F8FAFC
    classDef decision fill:#0F172A,stroke:#38BDF8,stroke-width:2px,color:#F8FAFC
    classDef react fill:#064E3B,stroke:#34D399,stroke-width:2px,color:#F8FAFC
    classDef direct fill:#1E1B4B,stroke:#818CF8,stroke-width:2px,color:#F8FAFC
    classDef fsm fill:#451A03,stroke:#FBBF24,stroke-width:2px,color:#F8FAFC
    classDef multi fill:#4C1D95,stroke:#C084FC,stroke-width:2px,color:#F8FAFC

    A["Start: Analyze Task & Input Requirements"] :::startNode --> B{"Is the workflow sequence 100% pre-determined?"}:::decision
    
    B -- Yes --> C{"Are tools or multi-step executions required?"}:::decision
    C -- No --> D["Single Structured LLM Call\n(Level 0: JSON Schema Output)"] :::direct
    C -- Yes --> E["FSM / DAG Workflow\n(Level 1: Fixed Graph Nodes)"] :::fsm

    B -- No --> F{"Does the task span multiple distinct expertise domains\nOR exceed single context limits?"}:::decision
    F -- No --> G["Single Bounded ReAct Agent\n(Level 2: Dynamic Tool Selection)"] :::react
    F -- Yes --> H["Hierarchical Multi-Agent System\n(Level 3: Orchestrator + Specialized Workers)"] :::multi
```

### 3.2 Tool Execution & Sandboxing Safety Tree

```mermaid
flowchart TD
    classDef decision fill:#0F172A,stroke:#38BDF8,stroke-width:2px,color:#F8FAFC
    classDef safe fill:#064E3B,stroke:#34D399,stroke-width:2px,color:#F8FAFC
    classDef warn fill:#451A03,stroke:#FBBF24,stroke-width:2px,color:#F8FAFC
    classDef danger fill:#7F1D1D,stroke:#F87171,stroke-width:2px,color:#F8FAFC

    A["Evaluate Proposed Tool Execution"] :::decision --> B{"Does tool run dynamic LLM-generated code\nor shell commands?"}:::decision
    
    B -- No (Read-only API/DB) --> C["Pure Python Handler\n(Enforce Schema & Read-Only Scopes)"] :::safe
    B -- Yes --> D{"Is execution running in multi-tenant\nor production environment?"}:::decision
    
    D -- Local Dev / Trusted Sandbox --> E["Subprocess Execution Wrapper\n(Strict Timeout = 30s, Process Killing)"] :::warn
    D -- Production / Multi-Tenant --> F["Isolated Container Sandbox\n(Docker / gVisor MicroVM + Network Block)"] :::danger
```

### 3.3 State Hydration & Memory Strategy Tree

```mermaid
flowchart TD
    classDef decision fill:#0F172A,stroke:#38BDF8,stroke-width:2px,color:#F8FAFC
    classDef option fill:#1E293B,stroke:#94A3B8,stroke-width:2px,color:#F8FAFC

    A["Determine State Management Strategy"] :::decision --> B{"Is session long-running or subject to network/server restarts?"}:::decision
    
    B -- Single HTTP Request (<30s) --> C["In-Memory Trajectory Buffer\n(Discard on completion)"] :::option
    B -- Multi-Turn or Async Workflow --> D{"Does context window grow near model limit (>70% tokens)?"}:::decision
    
    D -- No --> E["External JSON Checkpointing\n(Persist turn history per turn to SQLite/Redis)"] :::option
    D -- Yes --> F["Hydrated State + Dynamic Context Pruning\n(Persist full turn history, prune old tool outputs)"] :::option
```

### 3.4 Guardrail & Token Tax Configuration Tree

```mermaid
flowchart TD
    classDef decision fill:#0F172A,stroke:#38BDF8,stroke-width:2px,color:#F8FAFC
    classDef frontier fill:#064E3B,stroke:#34D399,stroke-width:2px,color:#F8FAFC
    classDef small fill:#451A03,stroke:#FBBF24,stroke-width:2px,color:#F8FAFC

    A["Configure State Guardrails (AGENTS.md Rule 3)"] :::decision --> B{"Which LLM class powers the Cognitive Engine?"}:::decision
    
    B -- "Frontier Model\n(Claude 3.5 Sonnet, Gemini 2.0 Flash/Pro, GPT-4o)" --> C["Set use_checklist: false by default\n(Use lightweight SOP injection, skip overhead)"] :::frontier
    B -- "Smaller / Open-Weight Model\n(Llama 3 8B, Qwen 7B, Mistral Small)" --> D["Set use_checklist: true\n(Inject explicit checklist tool and grounding state)"] :::small
```

---

## 📜 4. Spec-Driven Agent Development Framework

Spec-Driven Agent Development treats the agent specification (`spec.yaml`) as the single source of truth for runtime behavior, tool binding, SOP routing, and safety boundaries.

### Core Architecture of Spec-Driven Agent:

```
                          ┌──────────────────────────┐
                          │    agent_spec.yaml       │
                          └─────────────┬────────────┘
                                        │
                                        ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                           SPEC-DRIVEN AGENT ENGINE                            │
│                                                                               │
│  ┌───────────────────────┐  Hydrates  ┌────────────────────────────────────┐  │
│  │ BaseLLMClient         │───────────►│ System Prompt Generator            │  │
│  │ (Provider Agnostic)   │            │ [Static Prefix + Active SOP]       │  │
│  └───────────────────────┘            └─────────────────┬──────────────────┘  │
│                                                         │                     │
│  ┌───────────────────────┐  Enforces  ┌─────────────────▼──────────────────┐  │
│  │ Guardrail Config      │───────────►│ Bounded Control Loop               │  │
│  │ (max_loops, timeouts) │            │ (Max Iterations, Tool Dispatcher)  │  │
│  └───────────────────────┘            └────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────┘
```

### Spec Verification Matrix:
- [ ] **Identity & Role**: Clear, concise persona definition.
- [ ] **LLM Provider Mapping**: Primary model and fallback provider explicitly declared.
- [ ] **Tool Manifest**: All tools typed with JSON/Pydantic schemas and idempotency markers.
- [ ] **SOP Injection Map**: Mapping of intent triggers to external `.md` SOP files.
- [ ] **Safety & Limits**: `max_loops`, process `timeout_seconds`, and cost caps specified.

---

## 🔍 5. Design Review & QA Brainstorming Checklist (`/grill-me` Ready)

Use this checklist during architecture design reviews, team brainstorming, or interactive `/grill-me` alignment sessions before writing code.

### 🎯 5.1 Scope & Justification Audit
- [ ] **Agent Necessity**: Can this task be accomplished with a standard Python function or single LLM call? Why is an agent required?
- [ ] **Failure Cost**: What is the blast radius if the agent makes an incorrect decision or tool call? (e.g., corrupted DB, wrong financial report, leaked PII)
- [ ] **Human-in-the-Loop (HITL)**: Which high-risk tool calls (e.g. database mutations, payments, external emails) require explicit user confirmation before execution?
- [ ] **Success Criteria**: How do you objectively measure if the agent succeeded? Is there a verifiable output (file, metric, test result)?
- [ ] **Scope Boundary**: What does the agent explicitly *not* do? Are those exclusions documented?

### 🛡️ 5.2 Safety & Execution Probing
- [ ] **Loop Termination**: Is `max_loops` hardcoded and tested under failure conditions (not just happy path)?
- [ ] **Infinite Loop Detection**: Does the loop detect duplicate tool calls with identical arguments? (See `RepetitionDetector` in [core/utils.py](file:///home/navin/work/AI/projects/Agents/core/utils.py#L38-L67))
- [ ] **Tool Timeout**: Is every external process/tool wrapped with a timeout threshold? What happens when it fires? (graceful error message vs. crash?)
- [ ] **Prompt Injection Isolation**: Are user inputs sanitized before injection into tool commands or system prompt slots? (See [input_safety_and_payload_management.md](file:///home/navin/work/AI/projects/Agents/docs/input_safety_and_payload_management.md))
- [ ] **Hallucinated Tool Names**: What happens if the LLM invokes a tool name that doesn't exist in the manifest? Does the agent crash or return a structured error?
- [ ] **Malformed Tool Arguments**: What happens if the LLM returns invalid JSON in tool_calls? Is there a fallback parser? (See `JsonExtractor` in [core/utils.py](file:///home/navin/work/AI/projects/Agents/core/utils.py#L70-L123))
- [ ] **Destructive Operations**: Can the agent execute `rm -rf`, `DROP TABLE`, or `sudo` commands? Is there a blocklist or permission enforcer?

### 💰 5.3 Token & Cost Efficiency
- [ ] **Prompt Caching Layout**: Are static system instructions and tool schemas placed at the beginning of the prompt context? (Anthropic and Gemini cache the prefix)
- [ ] **Pruning Policy**: What happens when the context window reaches 80% capacity? Is `context_pruning` configured? (See [core/llm_clients.py](file:///home/navin/work/AI/projects/Agents/core/llm_clients.py#L18-L45))
- [ ] **Guardrail Toggle**: Is state guardrail overhead (`use_checklist`) disabled for frontier models unless explicitly requested?
- [ ] **Cost Ceiling**: What is the maximum acceptable cost for a single agent session? What happens when exceeded?
- [ ] **Token Budget per Turn**: Is there a `max_tokens` limit on each LLM response to prevent runaway generation?

### 🔄 5.4 Resilience & Recovery
- [ ] **Crash Recovery**: If the process crashes mid-loop, can the agent resume from the last checkpoint? Or does it restart from scratch?
- [ ] **External API Failure**: What happens if an external tool API (database, web service) is down for 5 minutes mid-session? Does the agent retry, abort, or escalate?
- [ ] **Rate Limiting**: Does the LLM client handle `429 Too Many Requests` with exponential backoff? Or does it crash?
- [ ] **Partial Results**: If the agent completes 4 of 5 sub-tasks and fails on the 5th, does it return partial results or nothing?

### 🔀 5.5 Provider Portability
- [ ] **Model Swap Test**: If you swap from Claude to Gemini (or Qwen), which components need changing? Only the `model` field in `spec.yaml`, or also tool schemas?
- [ ] **Tool Schema Format**: Are tool schemas defined in both Anthropic format (`input_schema`) and OpenAI format (`parameters`)? (See [data_analyst/tools.py](file:///home/navin/work/AI/projects/Agents/data_analyst/tools.py))
- [ ] **System Prompt Injection**: Does the LLM client handle system prompts differently per provider? (Anthropic uses `system` kwarg; OpenAI/HF prepend as a message)

### 🔐 5.6 Security & Data Governance
- [ ] **PII Exposure**: What data does the agent log in transcripts? Is any of it PII? Is there a redaction layer?
- [ ] **Secret Leakage**: Can the agent's tool output accidentally contain API keys, tokens, or credentials? Are secrets stripped from logs?
- [ ] **Multi-Tenant Isolation**: If multiple users share the agent, can one user's session data leak into another's context?
- [ ] **Prompt Regression**: How do you test prompt changes without breaking existing behavior? Is there a golden trajectory test suite?

---

## 📋 6. The 8-Phase Agent Audit Checklist

Complete this audit checklist phase-by-phase during agent implementation.

### Phase 1: Scope & Pattern Selection
- [ ] Classify task complexity (Level 0 to Level 3) using Section 2 Taxonomy.
- [ ] Confirm architecture pattern (Direct Call, FSM, ReAct, or Multi-Agent).
- [ ] Record non-essential feature requests as roadmap items in [backlog.md](file:///home/navin/work/AI/projects/Agents/docs/backlog.md) (`AGENTS.md` Rule 5).

### Phase 2: Provider Agnosticism & Cognitive Engine
- [ ] Abstract LLM interactions behind `BaseLLMClient` (`AGENTS.md` Rule 2).
- [ ] Implement exponential backoff retry logic inside the LLM client wrapper.
- [ ] Define fallback provider configuration for API rate limits or outages.
- [ ] Structure prompt payload so static prefix enables LLM prompt caching (`AGENTS.md` Rule 6).

### Phase 3: Structured Schemas & Tool Design
- [ ] Define all tool parameters using JSON Schema or Pydantic schemas (`AGENTS.md` Rule 7).
- [ ] Tag every tool with explicit `idempotent: true/false` metadata.
- [ ] Eliminate regex or custom string parsing for tool output extraction.
- [ ] Wrap code execution tools with subprocess timeouts or container sandboxes (`AGENTS.md` Rule 4).

### Phase 4: Control Loop & Bounded Safety
- [ ] Construct `while` loop with hard `max_loops` threshold (`AGENTS.md` Rule 1).
- [ ] Implement `RepetitionDetector` to halt repeating error sequences (3x consecutive threshold).
- [ ] Add cancellation token/signal checking at the top of each loop turn.
- [ ] Standardize final answer detection logic (no tool_calls = final answer).
- [ ] Handle unknown tool names gracefully (structured error, not crash).

### Phase 5: State, Memory & Hydration
- [ ] Implement external checkpoint persistence keyed by `session_id` (`AGENTS.md` Rule 8).
- [ ] Add session resume capability from the last saved turn checkpoint.
- [ ] Implement context window token counter and automatic context pruning.

### Phase 6: Guardrails & Token Economics
- [ ] Set `use_checklist: false` by default for frontier models (`AGENTS.md` Rule 3).
- [ ] Implement per-session token budget tracking and alerting.
- [ ] Implement circuit breaker to abort sessions exceeding cost boundaries.

### Phase 7: Declarative SOPs & Dynamic Injection
- [ ] Externalize domain workflows into Markdown files in `/sops/` (`AGENTS.md` Rule 10).
- [ ] Implement intent routing to dynamically select and append active SOPs.
- [ ] Keep core system prompt minimal and general-purpose.

### Phase 8: Observability, Tracing & Trajectory Evaluation
- [ ] Instrument dual-transcript logging (`transcript.jsonl` and `transcript_full.jsonl`) (`AGENTS.md` Rule 9).
- [ ] Create golden trajectory benchmarks for automated testing.
- [ ] Validate agent execution paths against regression test suites.

---

## 🔥 7. Failure Modes & Debugging Playbook

> [!IMPORTANT]
> These are the actual failure modes encountered when building and running agents. Each entry includes the symptom, root cause, and concrete fix with references to codebase files.

### 7.1 Infinite Error Loop (Token Burn)

**Symptom**: Agent generates code → gets an error → tries to fix it → generates the same broken code → repeats until `max_loops` is exhausted. Cost: $5–$15 wasted per session.

**Root Cause**: The LLM doesn't have enough context to fix the error (e.g., missing import, wrong column name) and hallucinates the same fix repeatedly.

**Diagnosis**: Check `transcript.jsonl` — look for identical STDERR output across consecutive turns.

**Fix**: Implement `RepetitionDetector` (already in [core/utils.py](file:///home/navin/work/AI/projects/Agents/core/utils.py#L38-L67)):
```python
error_detector = RepetitionDetector(threshold=3)
# In the loop, after receiving STDERR:
if error_detector.check(stderr):
    print("Same error repeated 3 times. Breaking loop.")
    break_agent_loop = True
    break
```

**Reference**: [lessons_learned.md §1-2](file:///home/navin/work/AI/projects/Agents/docs/lessons_learned.md)

---

### 7.2 Context Window Overflow

**Symptom**: LLM API returns a `400 Bad Request` or `context_length_exceeded` error after several loop iterations. The agent crashes instead of recovering.

**Root Cause**: Each loop appends full tool output (STDOUT/STDERR) to the message history. After 5–7 loops with verbose output, the context exceeds the model's limit.

**Diagnosis**: Add token counting before each API call:
```python
token_count = sum(len(str(m)) // 4 for m in self.messages)
print(f"Context size: ~{token_count} tokens")
```

**Fix**: Enable context pruning in `spec.yaml` and the LLM client:
```yaml
# In spec.yaml
context_pruning:
  enabled: true
  max_tokens: 4000
```
The `BaseLLMClient.prune_context()` method ([llm_clients.py L18-45](file:///home/navin/work/AI/projects/Agents/core/llm_clients.py#L18-L45)) automatically summarizes older turns and keeps only the last 2 assistant exchanges.

**Reference**: [lessons_learned.md §3](file:///home/navin/work/AI/projects/Agents/docs/lessons_learned.md)

---

### 7.3 LLM Returns Malformed Tool Calls

**Symptom**: The agent crashes with `KeyError: 'name'` or `json.JSONDecodeError` when parsing the LLM's tool_call response.

**Root Cause**: Smaller or open-weight models sometimes return tool calls wrapped in markdown code fences, or with slightly malformed JSON (trailing commas, missing quotes).

**Fix**: Use `JsonExtractor` from [core/utils.py](file:///home/navin/work/AI/projects/Agents/core/utils.py#L70-L123) which implements a 3-tier extraction pipeline:
1. Direct `json.loads()` attempt
2. Extract from markdown code fences (` ```json ... ``` `)
3. Regex extraction of outermost `{...}` or `[...]`

**Prevention**: Always validate parsed tool arguments against a schema using `SchemaValidator` ([core/utils.py L126-194](file:///home/navin/work/AI/projects/Agents/core/utils.py#L126-L194)) before dispatching.

---

### 7.4 Hallucinated Tool Names

**Symptom**: The LLM calls a tool like `search_web` or `read_file` that doesn't exist in the tool manifest. The agent returns `"Error: Unknown tool search_web"` — but the loop continues, wasting tokens.

**Root Cause**: The LLM generalizes from training data and invents plausible tool names.

**Fix**: Handle explicitly in the tool dispatch section (already in [agent.py L152-158](file:///home/navin/work/AI/projects/Agents/data_analyst/agent.py#L152-L158)):
```python
else:
    print(f"⚠️ Unknown tool requested: {tool_name}")
    self.llm.add_tool_result(
        tool_call_id=tc.get("id"),
        name=tool_name,
        result=f"Error: Unknown tool {tool_name}. Available tools: {[t['name'] for t in tools]}"
    )
```

**Key Insight**: Return the list of *available* tools in the error message so the LLM self-corrects on the next turn.

---

### 7.5 Agent Forgets Its Goal Mid-Session

**Symptom**: After 6+ loops of complex data manipulation, the agent starts performing unrelated analysis or repeats earlier steps as if it forgot what it already did.

**Root Cause**: LLMs have a finite attention span. In long sessions, the model's attention drifts away from the original goal buried in early context.

**Fix** (two strategies):
1. **For smaller models**: Enable `use_checklist: true` in `spec.yaml`. The checklist is injected into the system prompt on every turn, grounding the LLM's state. ([agent.py L26-42](file:///home/navin/work/AI/projects/Agents/data_analyst/agent.py#L26-L42))
2. **For frontier models**: Use declarative SOPs that break the task into numbered steps. The SOP acts as an implicit checklist without the token overhead of an explicit tool.

**Reference**: [lessons_learned.md §4](file:///home/navin/work/AI/projects/Agents/docs/lessons_learned.md)

---

### 7.6 Provider Fallback Failures

**Symptom**: Primary provider (e.g., Anthropic) is unavailable. Agent falls back to HuggingFace, but gets `401 Unauthorized` or `503 Service Unavailable` from the free inference endpoint.

**Root Cause**: Free/shared inference endpoints are rate-limited and unreliable. The fallback mechanism selects the provider at init time but doesn't retry on the alternate.

**Diagnosis**: Check environment variables — `ANTHROPIC_API_KEY` presence determines the provider at startup in [llm_clients.py L203-209](file:///home/navin/work/AI/projects/Agents/core/llm_clients.py#L203-L209).

**Fix**: Use dedicated paid API tiers for production. Track in [backlog.md](file:///home/navin/work/AI/projects/Agents/docs/backlog.md) as `ExponentialBackoffRetry` utility for graceful 429/5xx handling.

---

## 🏗️ 8. Worked Example: End-to-End Agent Build

> **Scenario**: *"Build a Data Analyst agent that loads a CSV dataset, explores it, answers a natural-language question with code and charts, and saves output."*

This is exactly what the existing [data_analyst/](file:///home/navin/work/AI/projects/Agents/data_analyst/) agent does. Here's how the checklist and decision trees drove each design decision.

### Step 1: Scope & Pattern Selection (Section 2 → Level 2)

| Decision Question | Answer | Implication |
|:---|:---|:---|
| Is the workflow 100% pre-determined? | **No** — user question is open-ended. | Rules out Level 0 and Level 1. |
| Does the agent need dynamic tool selection? | **Yes** — must write and execute arbitrary Python. | Confirms Level 2: ReAct Agent. |
| Does it span multiple expertise domains? | **No** — single data analysis domain. | Rules out Level 3: Multi-Agent. |

**Result**: Single Bounded ReAct Agent with `execute_python` tool.

### Step 2: Define the Spec ([data_analyst/spec.yaml](file:///home/navin/work/AI/projects/Agents/data_analyst/spec.yaml))

```yaml
name: Data analyst
description: Load, explore, and visualize data; build reports and answer questions from datasets.
model: claude-sonnet-4-6           # Primary frontier model
use_checklist: false                # Rule 3: Frontier model, skip overhead
system: |-
  You analyze data. Given a dataset (file path, URL, or query) and a question:
  1. Load the data and print its shape, column names, dtypes, and a small sample.
  2. Clean obvious issues — nulls, duplicates, type mismatches.
  3. Answer the question with code. Prefer pandas/polars for tabular work.
  4. Save any charts or derived tables to outputs/.
tools:
  - type: agent_toolset_20260401
context_pruning:
  enabled: true                    # Rule 8: Prevent context overflow
  max_tokens: 4000
```

### Step 3: Implement Tools ([data_analyst/tools.py](file:///home/navin/work/AI/projects/Agents/data_analyst/tools.py))

Two format functions were needed for provider agnosticism:
- `get_anthropic_tools()` — returns `input_schema` format
- `get_openai_tools()` — returns `parameters` format (used by HuggingFace)

Both conditionally include `manage_checklist` only when `use_checklist=True` (Rule 3).

### Step 4: Wire the Bounded Control Loop ([data_analyst/agent.py](file:///home/navin/work/AI/projects/Agents/data_analyst/agent.py))

Key safety patterns implemented:
- **`max_loops = 10`** (Rule 1)
- **`RepetitionDetector(threshold=3)`** — breaks on 3x consecutive identical STDERR
- **Dynamic system prompt** — updated each turn with latest checklist state
- **SOP routing** — `SOPRouter.route(question)` called before loop starts (Rule 10)

### Step 5: Set Up Subprocess Sandboxing ([data_analyst/executor.py](file:///home/navin/work/AI/projects/Agents/data_analyst/executor.py))

- `timeout=30` seconds (Rule 4)
- Writes code to temp file, runs via `subprocess.run()`, cleans up
- Intercepts `plt.show()` → saves to `outputs/plot.png` instead

### Step 6: Create SOPs ([data_analyst/sops/](file:///home/navin/work/AI/projects/Agents/data_analyst/sops/))

Three SOP files created:
- `default_analyst.md` — general analysis workflow
- `data_cleaning.md` — triggered by keywords like "clean", "null", "missing"
- `visualization.md` — triggered by "plot", "chart", "graph"

Routing is keyword-based via [sops.py](file:///home/navin/work/AI/projects/Agents/data_analyst/sops.py). (Backlog: upgrade to semantic vector search.)

### Step 7: Run & Verify

```bash
cd projects/Agents
python run_agent.py --agent data_analyst --data data_analyst/sample_data/sales.csv \
  --question "What are the top 3 products by total revenue?" --verbose
```

**Verification checklist**:
- [ ] Agent completed within `max_loops` (10)?
- [ ] Output chart saved to `data_analyst/outputs/`?
- [ ] No infinite error loop (check STDERR repetition)?
- [ ] Context pruning triggered if session exceeded 4000 tokens?
- [ ] Correct SOP routed (`default_analyst.md` for this query)?
