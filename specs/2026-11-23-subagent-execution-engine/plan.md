# Plan: Sub-Agent Skill Execution Engine

## Proposed Architecture

```
                       PARENT AGENT LOOP
                              │
                  LLM decides to delegate:
                  delegate_data_analyst(task="Analyze churn")
                              │
                              ▼
        ┌──────────────────────────────────────────────┐
        │       SubAgentEngine Tool Wrapper            │
        │        (core/subagent.py)                    │
        └─────────────────────┬────────────────────────┘
                              │ Spawns child agent
                              ▼
        ┌──────────────────────────────────────────────┐
        │               SkillSubAgent                  │
        │                                              │
        │  • Isolated BaseLLMClient                    │
        │  • System Prompt: data_analyst/SKILL.md SOP  │
        │  • Dispatcher: describe_table, query_table   │
        │  • Safety: max_loops=10, timeout=60s         │
        │                                              │
        │       Autonomous Child ReAct Loop:           │
        │       1. Observe Task                        │
        │       2. Think (LLM generation)              │
        │       3. Act (execute skill tools)           │
        │       4. Repeat until complete or max_loops  │
        └─────────────────────┬────────────────────────┘
                              │
                              ▼ Returns SubAgentExecutionResult
        Consolidated Summary: "Churn rate is 18%, driven by month-to-month contracts."
                              │
                              ▼
            Tool Result Injected into Parent Loop
            (Parent context receives 1 turn, not 10!)
```

---

## Phased Implementation Plan

### Phase 1: Core Engine (`projects/Agents/core/subagent.py`)
1. Data Models:
   - `SubAgentConfig`: Model configuration, loop thresholds, timeouts, and verbosity.
   - `SubAgentExecutionResult`: Consolidated final response, duration, loop count, status, and error details.
2. `SkillSubAgent`:
   - Sets up isolated `BaseLLMClient`, `AsyncToolDispatcher`, and `RepetitionDetector`.
   - `run(task: str) -> SubAgentExecutionResult`: Executes bounded ReAct loop.
3. `SubAgentEngine`:
   - Bridges `SkillRegistry` and parent agents.
   - `spawn_subagent(skill_name: str, config: Optional[SubAgentConfig]) -> SkillSubAgent`
   - `create_tool(skill_name: str) -> Callable`: Produces a standard async callable for registration with `AsyncToolDispatcher`.

### Phase 2: Integration & Public Exports
1. Export symbols in `core/__init__.py`.
2. Support registering sub-agents into `AsyncToolDispatcher` directly via `engine.register_skill_as_tool(dispatcher, skill_name)`.

### Phase 3: Unit & Multi-Agent Test Suite (`projects/Agents/tests/test_subagent.py`)
1. Unit tests for `SkillSubAgent` loop bounds (`max_loops` termination).
2. Timeout enforcement test.
3. Repetition loop breaking test.
4. Tool bridging test: Parent `AsyncToolDispatcher` calling `delegate_data_analyst` which drives the child loop and returns the consolidated answer.
5. Context isolation verification: Child intermediate tool outputs do not leak into parent.
