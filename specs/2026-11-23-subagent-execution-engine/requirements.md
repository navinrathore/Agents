# Requirements: Sub-Agent Skill Execution Engine

## Overview
Complex multi-step domain workflows (e.g., database schema discovery + multi-table SQL queries + aggregation, or security code audit across a repository) degrade parent agent performance when inlined into a single ReAct loop:
1. **Context Pollution**: Trial-and-error reasoning, intermediate error messages, and raw debug payloads flood the parent context window.
2. **Loop Exhaustion**: Sub-task troubleshooting rapidly exhausts the parent's `max_loops` threshold (Rule 1).
3. **Cognitive Distraction**: The parent agent loses track of its high-level strategic roadmap.

The **Sub-Agent Skill Execution Engine (`core/subagent.py`)** provides a framework for spawning **isolated child ReAct agents** dedicated to a specific `SkillPackage`. The sub-agent executes in its own sandboxed context, drives its private ReAct loop using the skill's tools and SOP, and returns a concise, consolidated result back to the parent agent.

---

## 1. Scope

### In-Scope
- **Isolated Execution Boundary (`SkillSubAgent`)**:
  - Independent `BaseLLMClient` instance with empty conversation history.
  - Dedicated system prompt hydrated with the skill's Standard Operating Procedure (`SKILL.md` SOP).
  - Dedicated `AsyncToolDispatcher` equipped with only the tools defined in the skill (`tools.py`).
  - Output protection via `OutputGuard` and input cleaning via `CodeSanitizer`.
- **Strict Bounded Execution (Safety Guardrails)**:
  - Configurable `max_loops` (default: 10, hard limit per Rule 1).
  - Configurable `timeout_seconds` (default: 60s per Rule 4).
  - Repetition detection via `RepetitionDetector` to prevent child agents from looping indefinitely on errors.
- **Parent-Child Tool Bridge (`SubAgentEngine`)**:
  - Automatically wraps a `SkillSubAgent` into a callable tool on the parent agent's `AsyncToolDispatcher`:
    `delegate_<skill_name>(task: str) -> str`.
  - The parent agent can delegate complex tasks using native tool-calling syntax without needing custom multi-agent orchestration logic.
- **Structured Observability & Logging**:
  - Detailed logging (`logger.info`, `logger.debug`, `logger.warning`) tracking child loop iterations, tool call counts, duration, and token containment.
  - Clear in-code comments explaining architectural patterns, context isolation, and error shielding.

### Out-of-Scope
- Distributed multi-process Celery or Redis queues (this engine operates in-process via `asyncio`).
- Peer-to-peer unstructured agent chatter (delegation is strictly hierarchical: Parent -> Child -> Parent).
