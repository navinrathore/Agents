# Master Document: Agentic AI Design Patterns & Workflows

This document serves as a master reference guide for building, tuning, and deploying autonomous AI agents. It synthesizes industry-standard practices, critical DOs and DONTs, and a reflective critique of the local Data Analyst Agent framework we built.

---

## 1. Industry-Accepted Paradigms & Architectures

When building Agentic AI flows today, the industry relies on a few core patterns:

### A. The ReAct (Reasoning and Acting) Loop
The foundational engine for generalist agents. The agent is placed in a `while` loop where it:
1. **Reads** the conversation history and environment state.
2. **Reasons** about what to do next.
3. **Acts** by outputting a JSON tool call (e.g., `execute_python`).
4. **Observes** the `STDOUT`/`STDERR` injected back into the prompt, and repeats.
*Use Case*: Open-ended, exploratory tasks (like data analysis or coding).

### B. State Machines & DAGs (Directed Acyclic Graphs)
Frameworks like **LangGraph** or **AutoGen** replace the free-form `while` loop with rigid flowcharts. The LLM does not control the loop; the developer programs nodes (e.g., Node A writes code, Node B executes, Node C reviews).
*Use Case*: Highly deterministic, production-critical workflows where you cannot risk the LLM going off-script.

### C. The Model Context Protocol (MCP)
An emerging standard (spearheaded by Anthropic) to decouple tools from agents. Instead of hardcoding tools into the Python script, agents connect to lightweight MCP servers (like a Postgres MCP or an Amplitude MCP) to securely explore data without needing custom integration code.

---

## 2. Agent Design: DOs and DONTs

### The DOs ✅
- **DO "Look before you compute"**: Always instruct the agent to inspect data schemas (columns, shapes, tables) in an initial exploratory loop before attempting to write complex aggregation logic.
- **DO implement hard safety nets**: An agent left alone will happily burn $100 in API credits stuck in a syntax-error loop. Always implement a hard `max_loops` limit.
- **DO abstract the LLM Provider**: Never hardcode your logic to exclusively use OpenAI or Anthropic. Always use a unified interface (like our `BaseLLMClient`) so you can swap to open-source models (Llama-3, Qwen) when cost becomes a factor.
- **DO use Context Pruning**: As the agent loops, the conversation history grows massively. Production agents must summarize older loops to keep latency low and prevent context-window overflow.

### The DONTs ❌
- **DON'T fall for the "Token Tax" blindly**: Don't force smart frontier models (like Claude 3.5 Sonnet or OpenAI o1) to use explicit checklist tools if they don't need them. Use guardrails conditionally.
- **DON'T rely heavily on bloated frameworks**: Avoid relying entirely on heavy wrappers (like standard LangChain) for core execution logic if you don't understand what it's doing under the hood. Building the loop yourself ensures you control the exact tool schemas and system prompts.
- **DON'T grant unrestricted environment access**: Never let an agent run `subprocess` directly on your host machine in production. Use Docker, Firecracker microVMs, or E2B for secure sandboxing.

---

## 3. Critique & Analysis of Our Project

### What We Did Exceptionally Well
1. **Zero-Bloat Architecture**: We built a true, raw ReAct loop from scratch in pure Python. By skipping heavy abstraction libraries, we achieved a deep, fundamental understanding of how tool schemas (`get_anthropic_tools`, `get_openai_tools`) map to actual Python execution.
2. **Provider Agnosticism**: We successfully proved that a complex autonomous data analysis task could be completed by an open-weight model (`Qwen2.5-72B-Instruct`) via Hugging Face, completely sidestepping proprietary API lock-in.
3. **Adaptive Guardrails**: We recognized that the `manage_checklist` tool was an excellent safety feature for smaller models, but we architected it to be conditionally disabled (`use_checklist: false`) to save tokens for smarter models.

### Areas for Improvement
1. **Token Routing Fragility**: Relying on free/shared inference endpoints (like Hugging Face Inference API) introduced temporary 401 Unauthorized errors due to third-party routing. Production systems require dedicated infrastructure or paid API tiers to guarantee uptime.
2. **Sandboxing**: Our current `PythonExecutor` is acceptable for local, trusted data. However, if this agent were to be deployed as a web service, the subprocess execution would be a massive security vulnerability. Transitioning to a Docker-based executor is the immediate next priority.
3. **Error Escalation**: Currently, our agent loop silently consumes errors (`STDERR`) and tries to fix them autonomously. We need to implement a "Human in the Loop" (HITL) interrupt mechanism—if the agent fails 3 times, it should pause and ask the user for advice rather than hitting the `max_loops` limit.

---

## 4. Managing Agentic Rules and Prompt Directives

Because Agentic Rule files (like `AGENTS.md`) are ingested directly into the LLM's context window as raw text, there is no strict "compiler" that ignores comments like `//` in programming languages. However, because LLMs process semantics, you can effectively manage and disable rules using three core strategies:

1. **The Semantic Method (Recommended)**: Explicitly tag the rule with keywords like `[DISABLED]` or `[IGNORE]`. The LLM reads this tag and semantically understands it should temporarily ignore the instruction.
2. **The HTML Comment Method**: Wrapping a rule in standard Markdown HTML comments (`<!-- rule -->`). LLMs are generally trained to treat these as hidden developer metadata, though it is less foolproof than explicit semantic tagging.
3. **The "Cold Storage" Method (Foolproof)**: Physically cut the rule from the active `AGENTS.md` file and paste it into a backup file (e.g., `AGENTS_rules_backup.md`). Since the text is entirely removed from the active context window, it guarantees zero token consumption and zero chance of model confusion.
