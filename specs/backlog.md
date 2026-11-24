# Agents Project Backlog

Categorized inventory of planned capabilities, optimizations, and technical debt for `projects/Agents`.

---

## 1. Core Architecture & Engines
- [ ] 🔴 P0 **Universal Application Rules Engine (`RuleManager`)**: Declarative rules discovery (`rules/*.md`), 3-tier precedence (Immutable Invariants $\to$ Defaults $\to$ Contextual Overrides), and static KV prompt caching compilation. #architecture #performance #security
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
- [ ] 🟢 P2 **Automated Ragas Triad Evaluation**: Integrate Ragas evaluation (`faithfulness`, `answer_relevance`, `context_recall`) into testing workflows. #evals #rag
