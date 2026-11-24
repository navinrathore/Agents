# Plan: NL-to-SQL / Database Agent

## Architecture & System Flow

```
                      User Natural Language Query
                                  │
                                  ▼
               ┌─────────────────────────────────────┐
               │  DatabaseAgent (BaseDatabaseAgent)  │
               └──────────────────┬──────────────────┘
                                  │
                   Builds Prompt with Cached Schema
                   (Tables, Columns, FKs, Sample Rows)
                                  │
                                  ▼
                        LLM Query Generation
                         (via BaseLLMClient)
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │  SqlSanitizer (sqlglot)   │
                    └─────────────┬─────────────┘
                                  │
               ┌──────────────────┴──────────────────┐
               │                                     │
        [Invalid / DML]                        [Valid SELECT]
               │                                     │
               ▼                                     ▼
      Isolated Error Diff                   HITL Security Policy
      (Loop < max_loops)                             │
               │                            ┌────────┴────────┐
               │                     [Sensitive]          [Standard]
               │                            │                 │
               │                            ▼                 │
               │                   HITLApprovalManager        │
               │                            │                 │
               │                            └────────┬────────┘
               │                                     │
               │                                     ▼
               │                            ┌─────────────────┐
               │                            │ DatabaseEngine  │
               │                            │  (SQLAlchemy)   │
               │                            └────────┬────────┘
               │                                     │
               │                                 Executes
               │                                     │
               ▼                                     ▼
         [Query Error]                      Raw Query Result
               │                                     │
               │                                     ▼
               │                           ┌───────────────────┐
               │                           │    OutputGuard    │
               │                           └─────────┬─────────┘
               │                                     │
               │                         Threshold Exceeded?
               │                             /         \
               │                          YES           NO
               │                           │             │
               │                           ▼             ▼
               │                      DataPointer    Direct In-Memory
               │                     (Offloaded)         Result
               │                           │             │
               │                           └──────┬──────┘
               │                                  │
               └──────────────────────────────────┴──────┐
                                                         ▼
                                                Natural Language
                                                Synthesis / Answer
```

---

## Phased Implementation Plan

### Phase 1: Layer 1 - Schema Introspection & DB Engine (`core/db/engine.py`)
1. **Data Models**:
   - `ColumnMetadata`: name, type, nullable, primary_key, default.
   - `ForeignKeyMetadata`: constrained_columns, referred_table, referred_columns.
   - `TableMetadata`: name, columns, foreign_keys, sample_rows.
   - `DatabaseSchema`: dialect, tables, generated_ddl.
2. **`DatabaseEngine` Class**:
   - Constructor accepting connection URL (SQLite or PostgreSQL) or existing SQLAlchemy `Engine`.
   - `introspect_schema(included_tables=None, excluded_tables=None, sample_rows=2) -> DatabaseSchema`:
     - Uses `sqlalchemy.inspect(engine)` to reflect tables, columns, foreign keys.
     - Queries top `sample_rows` rows safely using parameterized limits.
     - Formats clean, deterministic DDL string for LLM prompting.
   - `execute_query(sql: str, timeout_seconds: float = 30.0) -> QueryResult`:
     - Executes query in a scoped read-only transaction or connection.
     - Converts SQLAlchemy `CursorResult` to row dictionaries and column headers.
     - Enforces timeout using database-level or driver-level execution options.

### Phase 2: Layer 2 - SQL AST Validation & Sanitization (`core/db/sanitizer.py`)
1. **Custom Exceptions**:
   - `SqlSanitizationError` (base).
   - `UnsafeQueryError` (DML, DDL, or administrative command detected).
   - `MultiStatementQueryError` (multiple queries detected in single payload).
   - `SqlSyntaxError` (failed to parse AST).
2. **`SqlSanitizer` Class**:
   - `parse_ast(sql: str, dialect: str) -> sqlglot.exp.Expression`:
     - Parses single statement with `sqlglot.parse_one`.
     - Validates that single statement constraint is satisfied.
   - `validate_read_only(ast: sqlglot.exp.Expression) -> bool`:
     - Verifies root AST node is `Select` or CTE (`Select` inside `With`).
     - Scans for forbidden AST expressions (`Insert`, `Update`, `Delete`, `Drop`, `Create`, `AlterTable`, `Command`).
   - `inject_or_clamp_limit(ast: sqlglot.exp.Expression, default_limit: int = 100, max_limit: int = 1000) -> sqlglot.exp.Expression`:
     - Injects `LIMIT default_limit` if absent.
     - Clamps existing limit if `limit_val > max_limit`.
   - `transpile(sql: str, from_dialect: str, to_dialect: str) -> str`:
     - Transpiles between dialects (e.g. Postgres to SQLite).
   - `sanitize(sql: str, dialect: str = "sqlite", default_limit: int = 100, max_limit: int = 1000) -> SanitizedQuery`:
     - Coordinates full pipeline: parse -> validate -> limit injection -> return clean SQL string and AST summary.

### Phase 3: Layer 3 - Agent Orchestration & ReAct Loop (`core/db/agent.py` & `core/db/tools.py`)
1. **Abstract Base Interface (`core/db/base.py`)**:
   - `BaseDatabaseAgent(ABC)`:
     - Method `run(query: str) -> DatabaseAgentResponse`
     - Method `run_async(query: str) -> DatabaseAgentResponse`
     - Provides abstraction for potential LangChain / Vanna / external agent drop-in.
2. **Database Tools (`core/db/tools.py`)**:
   - Tool functions conforming to `core/dispatcher.py` schemas:
     - `list_tables()`
     - `get_table_schema(table_name: str)`
     - `execute_query(sql: str)`
     - `explain_query(sql: str)`
3. **`DatabaseAgent` Implementation (`core/db/agent.py`)**:
   - Initializes with `DatabaseEngine`, `SqlSanitizer`, `BaseLLMClient`, `OutputGuard`, and optional `HITLApprovalManager`.
   - `max_loops: int = 4` hard cutoff.
   - Prompt caching layout:
     ```
     [STATIC PREFIX]
     - Agent Role & Rules
     - Database Dialect & Constraints
     - Full Database DDL Schema & FK Relationships
     - Sample Data Previews
     [DYNAMIC CONVERSATION]
     - User Request
     - ReAct History / Isolated Error Diffs
     ```
   - Isolated Error Recovery:
     - On syntax/AST error or runtime DB error, constructs minimal feedback:
       `"SQL Execution Error: {error_type}: {error_message}. Problematic Query: {query}."`
     - Omits redundant schema re-sending to conserve tokens and preserve prompt caching.
   - OutputGuard Payload Offloading:
     - Results exceeding threshold characters are stored via `OutputGuard.process_output()`, returning a `DataPointer`.
   - Response formatting:
     - Returns `DatabaseAgentResponse` containing answer, executed SQL, raw/pointer results, and loop metrics.

### Phase 4: Integration, Module Exports & Package Structure
1. Create `projects/Agents/core/db/` package with `__init__.py`:
   - Export `DatabaseEngine`, `DatabaseSchema`, `TableMetadata`.
   - Export `SqlSanitizer`, `SanitizedQuery`, `UnsafeQueryError`.
   - Export `BaseDatabaseAgent`, `DatabaseAgent`, `DatabaseAgentResponse`.
2. Add exports to top-level `projects/Agents/core/__init__.py`.

### Phase 5: Verification & Comprehensive Test Suite (`tests/test_database_agent.py`)
1. Unit tests for `DatabaseEngine` with SQLite in-memory and reflected schemas.
2. Unit tests for `SqlSanitizer` with all permutations of SELECT, DML, DDL, multi-statement, comments, and LIMIT clamping.
3. Unit tests for `DatabaseAgent` ReAct loop, verifying loop cutoff, isolated error retries, and `OutputGuard` offloading.
4. End-to-end integration test executing natural language questions against a multi-table SQLite relational database.
