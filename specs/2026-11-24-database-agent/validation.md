# Validation: NL-to-SQL / Database Agent

## Test Matrix & Verification Criteria

| Test Suite / Category | Target Component | Input / Scenario | Expected Behavior & Verification Criteria |
| :--- | :--- | :--- | :--- |
| **Layer 1: Schema Introspection** | `DatabaseEngine.introspect_schema()` | In-memory SQLite with tables, PKs, FKs, and data. | Returns `DatabaseSchema` containing tables, columns, foreign key links, and sample rows. DDL string is clean and deterministic. |
| **Layer 1: Table Filtering** | `DatabaseEngine.introspect_schema()` | Schema with 5 tables, `included_tables=['users']`. | Only `users` table metadata is reflected and included in generated DDL. |
| **Layer 1: Scoped Execution** | `DatabaseEngine.execute_query()` | Valid `SELECT * FROM users` query. | Returns `QueryResult` with list of row dicts, column names, and row count. |
| **Layer 2: Valid Query Pass** | `SqlSanitizer.sanitize()` | Simple `SELECT name FROM users WHERE id = 1`. | Validates successfully; emits clean SQL string with `LIMIT 100` injected. |
| **Layer 2: Complex CTE Pass** | `SqlSanitizer.sanitize()` | `WITH dept_count AS (SELECT d_id, count(*) FROM emp GROUP BY d_id) SELECT * FROM dept_count`. | AST classified as valid read-only `Select`; parses and allows execution. |
| **Layer 2: Strict DML Rejection** | `SqlSanitizer.sanitize()` | `INSERT INTO users (name) VALUES ('hacker')`, `UPDATE users SET admin=1`, `DELETE FROM users`. | Raises `UnsafeQueryError` with explicit indication of forbidden DML operation. |
| **Layer 2: Strict DDL Rejection** | `SqlSanitizer.sanitize()` | `DROP TABLE users`, `ALTER TABLE users ADD COLUMN pwd`, `TRUNCATE TABLE logs`. | Raises `UnsafeQueryError` on DDL detection. |
| **Layer 2: Admin Command Rejection** | `SqlSanitizer.sanitize()` | `PRAGMA table_info(users)`, `ATTACH DATABASE`, `GRANT ALL`. | Raises `UnsafeQueryError` on administrative commands. |
| **Layer 2: Multi-Statement Blocking** | `SqlSanitizer.sanitize()` | `SELECT 1; DROP TABLE users;` or `SELECT 1; SELECT 2;`. | Raises `MultiStatementQueryError`; strictly rejects execution. |
| **Layer 2: Limit Injection & Clamping** | `SqlSanitizer.sanitize()` | 1. Query without `LIMIT`.<br>2. Query with `LIMIT 5000` (where `max_limit=1000`). | 1. Injects `LIMIT 100`.<br>2. Clamps limit to `LIMIT 1000`. |
| **Layer 2: Dialect Transpilation** | `SqlSanitizer.transpile()` | Postgres query with `ILIKE` or `::text` syntax to SQLite. | Transpiles to equivalent SQLite expression without syntax error. |
| **Layer 3: ReAct Loop Limit Cutoff** | `DatabaseAgent.run()` | Repeated syntax error or hallucinated columns with mocked failing LLM. | Loop terminates strictly at `max_loops` (e.g. 4 loops); returns graceful failure response without hanging. |
| **Layer 3: Isolated Error Diff** | `DatabaseAgent.run()` | First turn generates invalid SQL; second turn receives error feedback. | Message sent back to LLM contains only the minimal error diff (<300 tokens) rather than duplicating the full schema. |
| **Layer 3: OutputGuard Pointer Offload** | `DatabaseAgent.run()` | Query returning 1,000 rows (>8,000 characters). | Piped into `OutputGuard`; full results stored to disk; agent response includes `DataPointer` snippet and file URI. |
| **Layer 3: HITL Approval Trigger** | `DatabaseAgent.run()` | Query accessing sensitive table `user_credentials` when configured for HITL. | Calls `HITLApprovalManager`; pauses or prompts for approval before executing. |
| **Layer 3: Pluggable Base Interface** | `BaseDatabaseAgent` | Mocked custom agent subclassing `BaseDatabaseAgent`. | Adheres to abstract methods `run()` and `run_async()`, allowing framework swapping. |
| **Full Regression Suite** | Full Test Harness | Entire test harness (`pytest projects/Agents/tests`). | All existing test suites pass with zero regressions. |
