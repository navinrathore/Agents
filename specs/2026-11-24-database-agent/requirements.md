# Requirements: NL-to-SQL / Database Agent

## Overview
Natural Language to SQL (NL-to-SQL) is a critical capability for data exploration, reporting, and operational monitoring. However, unconstrained LLM database execution introduces major security, performance, and context management hazards:
1. **Destructive Operations & SQL Injection**: Hallucinated or malicious queries may alter state or destroy data (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE`).
2. **Context Window Exhaustion & Performance Degradation**: Unbounded queries (`SELECT * FROM table`) can retrieve millions of rows, blowing through context limits, triggering runaway token costs, or crashing LLM context windows.
3. **Dialect Mismatches & Syntax Failures**: LLMs frequently mix SQL dialects (e.g. Postgres `ILIKE` or `::text` casting in SQLite, or SQLite `PRAGMA` in Postgres).
4. **Token Inefficiency in ReAct Loops**: Blindly repeating the entire database DDL across turns wastes thousands of tokens, while full query error tracebacks clutter context and degrade model reasoning.

The **NL-to-SQL / Database Agent** provides a robust, multi-layer architecture designed according to Specification-Driven Development (SDD) and the core principles in `AGENTS.md`. It standardizes schema introspection, AST-based query sanitization, execution guardrails, isolated error diffs, and ReAct loop controls into an extensible, production-ready agent system.

---

## 1. Multi-Layer Architecture

The Database Agent is structured into three cleanly decoupled layers:

### Layer 1: Schema Introspection & DB Engine (Standard Library Reuse via `SQLAlchemy`)
- **Engine Abstraction**: Reuses `SQLAlchemy` (v2.0+) connection abstractions supporting SQLite (`sqlite:///...`) and PostgreSQL (`postgresql+psycopg2://...` or `postgresql://...`).
- **Automated Reflection**:
  - Dynamically reflects database catalog: tables, column names, data types, primary keys, and foreign key relationships via `sqlalchemy.inspect`.
  - Generates compact, LLM-optimized DDL representations suitable for static prompt prefixes.
  - Generates configurable sample row excerpts (e.g., top 2-3 rows per table) to provide semantic grounding for ambiguous column names.
- **Connection Isolation**:
  - Encapsulates execution inside scoped sessions with strict execution timeouts.
  - Sets connection-level read-only flags where supported by the underlying driver (e.g., Postgres `default_transaction_read_only = on` or SQLite URI `mode=ro`).

### Layer 2: SQL AST Validation & Sanitization (Standard Library Reuse via `sqlglot`)
- **AST Parsing & Statement Classification**:
  - Reuses `sqlglot` for deterministic, zero-regex SQL parsing and validation.
  - Classifies statements strictly: enforces an allowlist allowing **ONLY** `SELECT` and `WITH ... SELECT` (Common Table Expressions).
  - Explicitly detects and rejects all Data Manipulation Language (DML: `INSERT`, `UPDATE`, `DELETE`, `MERGE`), Data Definition Language (DDL: `CREATE`, `ALTER`, `DROP`, `TRUNCATE`), and Data Control / Administrative commands (`GRANT`, `REVOKE`, `PRAGMA`, `ATTACH`, `EXEC`, `VACUUM`).
- **AST Safety Transformations & Guardrails**:
  - Injects a mandatory default `LIMIT` clause (e.g., `LIMIT 100`) if the query does not specify one or if the user/LLM-specified `LIMIT` exceeds the system maximum (`max_limit=1000`).
  - Blocks dangerous multi-statement SQL script execution (e.g. `SELECT 1; DROP TABLE users;`) by enforcing single-AST verification.
- **Dialect Transpilation**:
  - Automatically transpiles queries between dialects (e.g., transpiling generic ANSI/Postgres SQL to SQLite syntax, or vice versa) using `sqlglot.transpile()`.

### Layer 3: Agent Orchestration & ReAct Loop (In-Core Custom Engine + Pluggable Interface)
- **Hard ReAct Loop Bounds**:
  - Enforces a strict maximum loop threshold (`max_loops=3` to `5`, default `4`) to prevent runaway token spend during query syntax errors or schema hallucination (Rule 1 of `AGENTS.md`).
- **Prompt Caching Friendliness**:
  - DDL schema and table definitions are placed at the very beginning of the prompt context in a static block to maximize prompt caching efficiency across turns (Rule 6 of `AGENTS.md`).
- **Isolated Error Diffs on Failure**:
  - When query execution or AST validation fails, the agent does NOT echo back the full schema or lengthy stack traces. It passes only a targeted, isolated error diff (the invalid query string, exact error location, and database error message) into the retry turn to conserve tokens.
- **OutputGuard & Pointer Offloading Integration**:
  - Integrates with `OutputGuard` / `DataPointer` (`core/output_guard.py`). If a query result set exceeds character or row thresholds (e.g., >8,000 characters or >50 rows), the full result is safely offloaded to disk, returning a structured head/tail excerpt and a `DataPointer` token to the LLM.
- **Human-in-the-Loop (HITL) Checkpoints**:
  - Built-in integration with `core/hitl.py`. If a query attempts non-read-only actions (if administrative bypass is configured) or queries designated sensitive/restricted tables (e.g. `users`, `audit_log`, `passwords`), the agent triggers a mandatory HITL approval checkpoint before execution.
- **Pluggable Base Architecture**:
  - Defines an abstract `BaseDatabaseAgent` interface, allowing projects to plug in external agent frameworks (such as LangChain SQLAgent or Vanna.ai) while standardizing Layer 1 and Layer 2 validation.

---

## 2. Scope

### In-Scope
- **`DatabaseEngine` (`core/db/engine.py`)**:
  - Connection management for SQLite and PostgreSQL via SQLAlchemy.
  - Automated reflection of schemas, tables, columns, data types, primary keys, and foreign keys.
  - Safe generation of sample row previews.
- **`SqlSanitizer` (`core/db/sanitizer.py`)**:
  - Deterministic AST validation using `sqlglot`.
  - Read-only AST classification (`SELECT`, `WITH ... SELECT`).
  - DML/DDL/Multi-statement blocking.
  - Default `LIMIT` injection and clamping.
  - Dialect transpilation (SQLite <-> Postgres <-> ANSI).
- **`BaseDatabaseAgent` & `DatabaseAgent` (`core/db/agent.py`)**:
  - Abstract base interface for database agents.
  - Custom in-core implementation utilizing `BaseLLMClient` (`core/llm_clients.py`).
  - ReAct loop with `max_loops=4` hard cutoff.
  - Prompt-caching optimized system prompts.
  - Isolated error correction loop.
  - Native integration with `OutputGuard` (`core/output_guard.py`) and `HITLApprovalManager` (`core/hitl.py`).
- **Database Tools (`core/db/tools.py`)**:
  - Standard agent tools: `list_tables`, `get_table_schema`, `execute_query`, `explain_query`.

### Out-of-Scope
- Direct connection drivers for NoSQL / Document databases (MongoDB, Redis, Elasticsearch); focused on relational SQL.
- Automatic vector embeddings of database rows (Text-to-Embeddings RAG is handled separately in RAG pipelines).
- Full database migration or backup management (this is a querying and analysis agent, not an administrative DBA automation tool).

---

## 3. Detailed Technical Requirements

### 3.1 Layer 1: Schema Introspection & DB Engine (`SQLAlchemy`)
1. **Supported Databases**:
   - SQLite (`sqlite:///:memory:`, `sqlite:///path/to/db.sqlite`).
   - PostgreSQL (`postgresql://user:pass@host:port/dbname`).
2. **Introspection Payload (`DatabaseSchema`)**:
   - `dialect: str` (e.g. `'sqlite'`, `'postgres'`).
   - `tables: Dict[str, TableMetadata]`.
   - Each `TableMetadata` includes:
     - `name: str`
     - `columns: List[ColumnMetadata]` (`name`, `type`, `nullable`, `primary_key`, `default`)
     - `foreign_keys: List[ForeignKeyMetadata]` (`constrained_columns`, `referred_table`, `referred_columns`)
     - `sample_rows: List[Dict[str, Any]]` (up to `sample_rows_count=3`)
3. **DDL Generation**:
   - Must produce clean, compact `CREATE TABLE (...)` DDL representations without proprietary engine metadata.
   - Must support filtering: allow introspecting only a specified subset of tables (`included_tables` / `excluded_tables`) to prevent context bloat on large enterprise schemas.

### 3.2 Layer 2: SQL AST Validation & Sanitization (`sqlglot`)
1. **Read-Only Verification**:
   - Parses incoming SQL strings into AST via `sqlglot.parse_one(sql, read=dialect)`.
   - Checks the root expression type: MUST be an instance of `sqlglot.exp.Select` or `sqlglot.exp.Union` or `sqlglot.exp.Expression` whose primary query statement is a `Select`.
   - Traverses all child nodes via `expression.find_all(...)`. If any child node is an instance of `sqlglot.exp.Insert`, `sqlglot.exp.Update`, `sqlglot.exp.Delete`, `sqlglot.exp.Drop`, `sqlglot.exp.Create`, `sqlglot.exp.AlterTable`, or `sqlglot.exp.Command`, validation MUST immediately raise `UnsafeQueryError`.
2. **Single-Statement Enforcement**:
   - `sqlglot.parse(sql, read=dialect)` must yield exactly one statement. If `len(statements) > 1`, raise `MultiStatementQueryError`.
3. **Limit Clause Injection**:
   - If `expression.find(sqlglot.exp.Limit)` is `None`, inject `LIMIT {default_limit}` (default 100).
   - If `LIMIT` is present and its integer expression value exceeds `max_limit` (default 1000), rewrite the node value to `max_limit`.
4. **Dialect Transpilation**:
   - Provide `transpile_query(sql: str, from_dialect: str, to_dialect: str) -> str`.

### 3.3 Layer 3: Agent Orchestration & ReAct Loop
1. **Interface Contract (`BaseDatabaseAgent`)**:
   - `run(user_query: str) -> DatabaseAgentResponse`
   - `run_async(user_query: str) -> DatabaseAgentResponse`
2. **ReAct Loop Execution (`DatabaseAgent`)**:
   - Initial state builds system prompt containing:
     - Role and instructions.
     - Static schema representation (DDL + foreign keys) placed strictly at the beginning for prompt caching.
   - Loop iteration (`while loop_count < max_loops`):
     - Generate SQL via LLM call (`BaseLLMClient`).
     - Sanitize and validate SQL with `SqlSanitizer`.
       - On validation failure: increment `loop_count`, append isolated validation error diff to messages, retry.
     - Evaluate HITL requirements:
       - If table is restricted, call `HITLApprovalManager.request_approval(...)`.
     - Execute query via `DatabaseEngine`.
       - On execution error: increment `loop_count`, append isolated DB error message, retry.
       - On execution success: pipe result through `OutputGuard`.
         - If result size > threshold, emit pointer notice.
     - Synthesize final natural language answer summarizing findings.
3. **Fallback & Max Loop Guard**:
   - If `loop_count >= max_loops`, terminate loop immediately and return `DatabaseAgentResponse` with `success=False`, `error="Max reasoning iterations reached without valid query execution"`, and the last generated query/error.

---

## 4. Non-Functional Requirements
- **Performance**: AST parsing and sanitization must complete in <10ms for typical queries.
- **Security**: Zero SQL injection vulnerabilities allowed; read-only guarantees must hold even if the LLM hallucinates comments (`--`, `/* */`), string escapes, or stacked queries.
- **Token Efficiency**: Schema representation must not exceed 20% of standard context; error diffs must be <300 tokens.
- **Maintainability**: Complete type annotations (`typing`), zero circular imports, and high cohesion between layers.
