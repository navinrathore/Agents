# Agents Project Roadmap

## Phase 1 — Parallel Tool Calling & Async Dispatcher
- [x] Implement `AsyncToolDispatcher` with bounded concurrency (`asyncio.Semaphore`) #architecture #concurrency
- [x] Implement sequential-only tool isolation for mutating operations #safety
- [x] Per-tool timeout enforcement and error shielding #resilience
- [x] Comprehensive test suite in `tests/test_tool_dispatcher.py` #testing

## Phase 2 — Payload Offloading & Content-Addressed Storage
- [x] Implement `OutputGuard` with smart head/tail truncation #performance
- [x] Implement SHA-256 content-addressable `LocalDiskPayloadStore` (`vault/pointers/`) #storage
- [x] Create pointer inspection micro-tools (`read_pointer_slice`, `query_pointer_json`, `grep_pointer`) #tools
- [x] Comprehensive verification in `tests/test_output_guard.py` and `tests/test_pointer_tools.py` #testing

## Phase 3 — Human-In-The-Loop (HITL) Approval Checkpoints
- [x] Implement `HITLApprovalGate` state machine with tokenized reviews #hitl #safety
- [x] Multi-channel notification dispatchers (Telegram, Webhook, Console, Mock) #notifications
- [x] Asynchronous two-way webhook acknowledgment & feedback injection #hitl
- [x] Full test suite in `tests/test_hitl.py` and `tests/test_notifications.py` #testing

## Phase 4 — Dynamic Skill Packages & Progressive Disclosure
- [x] Implement `SkillRegistry` with YAML frontmatter discovery #skills #architecture
- [x] Implement `SkillRouter` with Tier 1 deterministic trigger matching #performance
- [x] Implement `SkillManager` for dynamic tool mounting and SOP prompt augmentation #skills
- [x] Create reference `skills/data_analyst/` package #skills
- [x] Comprehensive test suite in `tests/test_skills.py` #testing

## Phase 5 — Code Sanitizer Subsystem
- [x] Multi-strategy markdown code fence extraction (`LONGEST`, `FIRST`, `LAST`, `ALL`) #sanitizer
- [x] Conversational opener and sign-off stripping #sanitizer
- [x] Heredoc, python -c, and Jupyter magic command stripping #sanitizer
- [x] Indentation normalization and optional `ast.parse` Python syntax verification #sanitizer
- [x] Comprehensive test suite in `tests/test_sanitizer.py` #testing

## Phase 6 — Sub-Agent Execution Engine & Context Sandboxing
- [x] Implement `SkillSubAgent` with isolated ReAct child loops #subagents #architecture
- [x] Dynamic parent-dispatcher tool bridging (`delegate_to_<skill>`) #tools
- [x] Hard loop ceilings (`max_loops=15`) and timeout protection #safety
- [x] Non-consecutive cyclic repetition detection in `core/utils.py` #resilience
- [x] Comprehensive test suite in `tests/test_subagent.py` #testing

## Phase 7 — Nested Tool Calling & In-Process DAG Execution Engine
- [x] Implement `ToolPipelineEngine` with Kahn's topological cycle rejection #architecture #pipeline
- [x] Topological wave concurrency execution via `asyncio.gather` + Semaphore #concurrency
- [x] Dynamic parameter interpolation (`{{steps.<id>.output.<path>}}`) #dx
- [x] Standalone `ConfigurablePipelineRunner` with safe env var expansion #portability
- [x] Comprehensive test suite in `tests/test_tool_chain.py` #testing

## Phase 8 — NL-to-SQL / Database Agent
- [x] Layer 1: Schema introspection & DB engine via SQLAlchemy (`core/db/engine.py`) #database
- [x] Layer 2: AST query validation & read-only enforcement via sqlglot (`core/db/sanitizer.py`) #security #database
- [x] Layer 3: ReAct DatabaseAgent with static DDL prompt caching & isolated error diffs (`core/db/agent.py`) #architecture
- [x] DatabaseTools adapter (`core/db/tools.py`) and pluggable `BaseDatabaseAgent` interface #dx
- [x] Reusable skill package `skills/database_agent/` #skills
- [x] Full test suite (27 tests) in `tests/test_database_*.py` #testing

## Phase 9 — Universal Application Rules Engine (`RuleManager`)
- [x] Implement declarative rule discovery (`rules/*.md`) in `core/rules.py` #architecture #rules
- [x] Implement 3-tier precedence resolution (Immutable Invariants $\to$ Defaults $\to$ Contextual Overrides) #security #rules
- [x] Implement deterministic KV cache prompt compilation for BaseLLMClient #performance #rules
- [x] Create standard rule files (`00_global_invariants.md`, `10_security_guardrails.md`, `20_sql_invariants.md`) #rules
- [x] Implement `RuleLinter` & standalone CLI (`python -m core.rules lint`) #dx #tooling
- [x] Comprehensive test suite (16 rule tests + `DatabaseAgent` integration) in `tests/test_rules.py` #testing
