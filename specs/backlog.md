# Agents Project Backlog

Categorized inventory of planned capabilities, optimizations, and technical debt for `projects/Agents`.

---

## 1. Core Architecture & Engines
- [x] **[2026-11-24]** Universal Application Rules Engine (`RuleManager`) & Linter CLI (`python -m core.rules lint`): Declarative rules discovery (`rules/*.md`), 3-tier precedence (Immutable Invariants $\to$ Defaults $\to$ Contextual Overrides), static KV prompt caching compilation, and standalone linter CLI delivered in `core/rules.py`. #architecture #performance #security
- [ ] 🔴 P0 **Rules Engine Fail-Closed Discovery & Tier 1 Precedence Hardening (`core/rules.py`)**: Stop silently swallowing `(RuleParseError, OSError)` in `RuleRegistry.discover_rules()` (fail closed on corrupted/Tier 1 rule files), check Tier 1 name collisions across all discovered rules before `scope`/`enabled` filtering to block disjoint-scope bypasses, allow `enabled: false` to disable Tier 2 defaults, use `setdefault` for duplicate `search_paths`, and break same-directory Tier 2/3 collisions by priority (findings from `docs/reviews/2026-11-25_rules_engine_critique_report.md`). #security #reliability #rules
- [ ] 🟡 P1 **Rules Engine Cache Freshness, Immutability & Empty-Block Fix (`core/rules.py`)**: Track a `RuleRegistry` generation/epoch counter so `RuleManager.compile_system_prefix()` invalidates `_memoized_prefixes` when existing files change, return a deep copy in `format_for_provider()`, and omit empty `text` blocks when no rules match. #performance #reliability #rules
- [ ] 🟡 P1 **Rules Frontmatter Parser, YAML Coercion & Regex ReDoS Hardening (`core/rules.py`)**: Fix `_FRONTMATTER_PATTERN` for markdown `---` horizontal rules and empty `---\n---` blocks, reject `bool` priorities (`priority: false`), fix `"false"` truthiness on `enabled`, stop promoting `scope: []` to `["*"]`, reject whitespace-only `name`, replace $O(N^2)$ `_VOLATILE_TEMPLATE_PATTERN` backtracking with `[^}\n]*`, and fix ISO `t`/underscore-prefix volatile detection bypasses. #security #reliability #dx
- [ ] 🟡 P1 **End-to-End Provider `cache_control` Wiring (`DatabaseAgent` & `BaseLLMClient`)**: Wire `RuleManager.format_for_provider()` in `DatabaseAgent._build_system_prompt()`, flatten structured `List[Dict]` system blocks for OpenAI/HuggingFace/Mock clients, and emit diagnostic logs in `compile_system_prefix()` when prefix < 1,024 tokens. #performance #architecture
- [ ] 🟡 P1 **Cross-File Validation in `RuleLinter`, CLI Default Path & Module Exports**: Add `RuleRegistry`-level checks in `RuleLinter.lint_all()` for Tier 1 `ImmutableRuleOverrideError` collisions, duplicate rule names, combined prefix token budgets (`>= 1,024`), fix dead `RuleLinter.lint_file()` checks (`scope: []`, `priority < 20` + `immutable: false`) by inspecting raw YAML, align `run_cli()` default path with `RuleLinter.__init__`, resolve `runpy` import warning, export `core.rules` symbols in `core/__init__.__all__`, and sync `specs/2026-11-24-application-rules-engine/validation.md`. #dx #tooling #security
- [ ] 🟡 P1 **New-File Detection & Hot-Reload Invalidation in `RuleRegistry` (`mtime`)**: Track directory `mtime`s alongside file `mtime`s in `discover_rules()` so newly added `.md` files are detected automatically and invalidate `RuleManager._memoized_prefixes`. #performance #reliability
- [ ] 🟡 P1 **Rules Engine Rollout to `SubAgent` & `SkillManager`**: Integrate `RuleManager` into `core/subagent.py` and `run_agent.py` so all agents share the immutable Tier 1 prefix, appending dynamic `SkillPackage` SOPs after the cached prefix. #architecture #performance
- [ ] 🟢 P2 **Rule-Set Hash Drift Detection for Crash Recovery (Rule 8)**: Persist `compiled.sha256_hash` and `active_rule_names` alongside `CheckpointManager` session state so resumed/HITL-paused workflows detect disk rule changes across restarts. #resilience #security
- [ ] 🟡 P1 **Unified Language Sanitizer Factory (`LanguageSanitizerFactory`)**: Unify Python (`ast.parse`), SQL (`sqlglot`), JSON (`repair/loads`), and Bash validators behind a single `BaseLanguageSanitizer` registry to eliminate repetitive procedural branching. #architecture #dx
- [ ] 🔴 P0 **Agent CheckpointManager / StateSerializer**: Serialize and hydrate agent loop state (messages, active SOPs, tool outputs) to SQLite/JSON for cross-session crash recovery and resumption. #resilience #storage
- [ ] 🔴 P0 **Robust MicroVM / Container Sandboxing**: Transition from local `subprocess` execution in `PythonExecutor` to containerized Docker or Firecracker microVM execution for safe untrusted code runs. #security #sandboxing

---

## 2. Database & Data Capabilities
- [ ] 🟡 P1 **Native Async SQLAlchemy Engine (`create_async_engine`)**: Implement optional async driver support (`aiosqlite` / `asyncpg`) within `DatabaseEngine` for high-concurrency microservices. #performance #database
- [ ] 🟢 P2 **Multi-Tenant Database Context Resolver**: Support dynamic runtime database connection switching in `DatabaseTools` based on user/tenant headers. #database #multitenancy
- [ ] 🟢 P2 **SQL Query Plan & Cost Explainer**: Implement `explain_query()` analysis comparing estimated table scan costs before execution. #performance #database

---

## 3. Tooling & MCP Integration
- [ ] 🟡 P1 **FastMCP Inbound Server Wrapper**: Expose `DatabaseTools`, `PointerTools`, and `Dispatcher` as a standardized FastMCP server for consumption by external IDEs and agents. #mcp #dx
- [ ] 🟢 P2 **Dynamic OpenAPI Schema Generation**: Automatically synthesize and export OpenAPI 3.0 schemas for all active dispatcher tools. #openapi #tooling

---

## 4. Testing & Evaluation
- [ ] 🟡 P1 **Trajectory & Multi-Turn Benchmark Suite**: Automated evaluation harness measuring turn count, tool error rates, and token efficiency across multi-turn problem sets. #testing #evals
- [ ] 🟢 P2 **Rules Engine Negative, Edge-Case, Concurrency & Domain Rule Expansion**: Add domain rules (`subagent`, `code_execution`, `hitl_email`), `config/rules/` override fixtures, multi-threaded `RuleRegistry.discover_rules()` race tests, symlink-loop traversal tests, and regression tests for Tier 1 scope bypass, YAML coercion, markdown `---` frontmatter, cache invalidation on edits, ReDoS bounds, and default `run_cli()` execution. #testing #security
- [ ] 🟢 P2 **Automated Ragas Triad Evaluation**: Integrate Ragas evaluation (`faithfulness`, `answer_relevance`, `context_recall`) into testing workflows. #evals #rag
