# 🧠 Agentic AI Study Cheat Sheet: Keywords & Core Concepts

> **Format:** 2-Page Quick-Study Reference & Interview / Certification Prep  
> **Focus:** High-yield core concepts, essential terminology, memory hooks, and critical traps (skipping low-frequency edge cases).

---

## 1. Execution & Reasoning Loops

| Keyword | Core Concept (What is it?) | When to Use? | Golden Rule / Pitfall |
|:---|:---|:---|:---|
| **ReAct Loop** *(Reason → Act → Observe)* | Dynamic cycle where the model thinks, invokes a tool, observes the output, and decides the next step. | Open-ended exploration, debugging, dynamic data research. | **Token burn:** Sends entire past history every loop turn. |
| **Hard Loop Cap (`max_loops`)** | Hardcoded integer ceiling (e.g. 10–15) terminating the autonomous loop. | **Mandatory** on every autonomous agent loop. | **Never omit:** Prevents runaway API bills on errors/hallucinations. |
| **Prompt Chaining** | Fixed, sequential pipeline where Step A output directly feeds Step B. | Predictable, multi-stage tasks (e.g. Ingest → Extract → Summarize). | Prefer over ReAct when task steps are known in advance. |
| **Plan-and-Execute** | Model writes a complete step-by-step task DAG *before* executing any tool. | Complex or high-risk tasks requiring human review before action. | Decouples "planning thoughts" from "execution actions." |
| **Grounded Reflection** | Self-correction driven by *external execution signals* (compiler errors, test failures). | Coding, SQL query generation, data analysis agents. | Never rely on ungrounded introspection; model repeats mistakes. |
| **State Machine / Graph (LangGraph)** | Workflow modeled as explicit nodes (actions) and edges (conditional routing). | Enterprise workflows with strict branching, cycles, and termination gates. | Guarantees deterministic paths where pure LLM routing fails. |

---

## 2. Tools & System Integration

| Keyword | Core Concept (What is it?) | When to Use? | Golden Rule / Pitfall |
|:---|:---|:---|:---|
| **MCP (Model Context Protocol)** | Open standard (Anthropic/open source) for connecting agents to external Tools, Resources (URIs), and Prompts. | Connecting agents to databases, file systems, Git, or SaaS tools without custom wrappers. | Resources = read-only data; Tools = executable actions with side-effects. |
| **Async Tool Dispatcher** | Concurrency engine executing independent tool calls in parallel with rate limits & timeouts. | Multi-tool calls, parallel web searches, scraping multiple endpoints. | Always enforce per-tool timeouts (`asyncio.wait_for`). |
| **Output Offloading (`DataPointer`)** | Truncating oversized tool responses in prompt context while storing raw payload to disk/DB. | Large SQL queries, API dumps, log file inspection (>4KB). | Prevents context window saturation while preserving data access. |
| **Code Sanitizer** | Utility stripping markdown fences (\`\`\`python) and conversational banter from LLM code. | Code execution agents feeding generated text to `exec()` or subshell. | AST-validate before running to catch syntax errors early. |

---

## 3. The 4 Tiers of Agent Memory

```
┌────────────────────────────────────────────────────────────────────────┐
│                        AGENT MEMORY HIERARCHY                          │
├──────────────────┬───────────────────────┬─────────────────────────────┤
│ 1. Working       │ In-Context Window     │ Active scratchpad & turns   │
│ 2. Procedural    │ SOPs / System Prompts │ "How-to" rules & workflows  │
│ 3. Semantic      │ Knowledge Base / RAG  │ Enterprise facts & policies │
│ 4. Episodic      │ Vector Log of Runs    │ Past cross-session history  │
└──────────────────┴───────────────────────┴─────────────────────────────┘
```

* **Working Memory (In-Context):** The immediate conversation window. Degrades as tokens rise (*Needle-in-a-Haystack* issue).
* **Context Pruning (*Summarize-and-Forget*):** As tokens near limit, compress older turns into an executive summary. **Why:** Keeps latency low and attention sharp.
* **Procedural Memory (SOPs):** External Standard Operating Procedures loaded on-demand. **Why:** Eliminates monolithic system prompts.
* **Semantic Memory (Knowledge):** Long-term facts, product specs, manuals (stored in Vector DBs or Knowledge Graphs).
* **Episodic Memory (Experience):** Searchable diary of past agent executions. **Why:** Allows an agent to remember user quirks or prior bugs across different days.

---

## 4. Determinism, Schemas & Reliability

| Keyword | Core Concept (What is it?) | When to Use? | Golden Rule / Pitfall |
|:---|:---|:---|:---|
| **Structured Output** | Enforcing strict JSON Schemas (Pydantic) via provider engines or constrained decoding. | Parsing tool calls, classification tags, database insertion payloads. | **Zero regex:** Never parse JSON with regex; enforce schema at API boundary. |
| **Repetition Detection** | Hash-based sliding window tracking consecutive or alternating errors (A → B → A). | Running inside the main ReAct loop. | Aborts early (turn 2–3) rather than waiting for `max_loops`. |
| **Exponential Backoff + Jitter** | Retrying failed API requests with randomized increasing delays. | Handling HTTP 429 (Rate Limits) and network hiccups. | Jitter prevents "thundering herd" spikes on LLM provider gateways. |
| **MicroVM Sandboxing** | Executing LLM-generated code in isolated environments (Docker / Firecracker / gVisor). | Any agent running bash, Python, or shell scripts. | Running `subprocess.run` on host OS is an immediate critical RCE vulnerability. |

---

## 5. Human-in-the-Loop (HITL) & Multi-Agent Systems

* **Stateful Pause-Resume Checkpoint:** Agent halts execution before executing high-risk tools (e.g. `execute_payment`, `drop_table`), serializes state to DB, and awaits signed human webhook approval.
* **Two-Way UI Acknowledgment:** When human clicks Telegram/Slack `[Approve]`, webhook handler immediately returns `answerCallbackQuery` (clearing client spinner) while execution resumes in background.
* **Safe Callback Hashing:** Telegram limits callback payloads to 64 bytes. Hash payload IDs (`h:<hash16>:<action>`) to guarantee the verb (`approve`/`reject`) is never truncated.
* **Supervisor Architecture:** Hierarchical pattern where 1 Manager agent breaks down user intent, delegates sub-tasks to specialized Worker agents, and synthesizes answers.
* **Agent-as-Tool:** Wrapping an entire sub-agent loop inside a standard callable function exposed to a parent agent (clean encapsulation).
* **A2A Protocol & Agent Cards:** Open standard for cross-vendor agent discovery. An **Agent Card** is a machine-readable JSON manifest publishing agent capabilities, auth requirements, and skills.

---

## 6. Security, Identity & Production Ops

| Keyword | Core Concept (What is it?) | Why It Matters? |
|:---|:---|:---|
| **Indirect Prompt Injection** | Attackers hide malicious instructions inside retrieved web pages, PDFs, or emails. | Quarantining untrusted data in `<untrusted_context>` tags neutralizes attacks. |
| **Non-Human Identity (NHI)** | Treating agents as governed enterprise identities under IAM (OAuth 2.1, PKCE). | Eliminates dangerous static master API keys in agent config files. |
| **Ephemeral Credentials** | Short-lived, JIT tokens generated dynamically for specific tool runs. | Limits blast radius if an agent session is compromised. |
| **Prompt Caching** | Placing large, static text (system prompts, tool definitions) at prompt prefix. | Slashes input token costs and latency by **70–90%**. |
| **Dual-Transcript Logging** | `transcript.jsonl` (compact/truncated) + `transcript_full.jsonl` (complete payloads). | Fast daily operational debugging without losing deep forensic traces. |
| **Cost-per-Outcome (RoAI)** | Measuring financial cost per completed business goal (not raw tokens). | A cheap model taking 10 loops is more expensive than a smart model taking 1. |

---

## 7. The 5 Core Mental Models of Agent Engineering

1. **The Simplicity Rule (Anthropic):** Start with basic prompt chaining; only escalate to an autonomous ReAct loop when the execution path cannot be predicted.
2. **Deterministic Core, Supervisory AI:** Keep domain logic and mathematical calculations 100% deterministic code. Use the LLM only as a reasoning supervisor.
3. **The Token Tax:** Smart models don't need heavy micro-management prompts. Make tool guardrails and validation steps configurable to save latency and tokens.
4. **The Grounding Imperative:** An LLM cannot grade its own homework without external tools (tests, linters, schemas, or secondary judge models).
5. **Truthiness Trap:** In config loaders, unexpanded env vars (`"${TOKEN}"`) evaluate as truthy non-empty strings in Python, bypassing fallback logic. Always expand before parsing.
