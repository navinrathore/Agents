---
name: database_agent
description: Introspect database schemas, formulate safe read-only SQL, and execute analytical queries with automatic error recovery and AST sanitization.
version: 1.0.0
triggers:
  - database agent
  - query database
  - relational schema
  - introspect schema
  - ast query
tags:
  - database-management
  - db-agent
requires_approval: false
---

# Database Agent SOP (Standard Operating Procedure)

When assisting the user with database queries and relational data analysis:

1. **Schema Discovery First**:
   - Begin by listing available tables using `list_tables()` or checking specific definitions with `get_table_schema(table_name)`.
   - Never guess column names or data types; strictly rely on the reflected DDL.

2. **Formulate Safe Queries**:
   - Write clean, ANSI/dialect-appropriate SQL queries.
   - Use `execute_sql(sql)` to run queries.
   - All queries are automatically validated via AST parsing:
     - Only `SELECT` and `WITH ... SELECT` queries are permitted.
     - DDL (`DROP`, `ALTER`, `TRUNCATE`) and DML (`DELETE`, `UPDATE`, `INSERT`) will be blocked.
     - Semicolon query-chaining is strictly forbidden.
     - A safety `LIMIT` is automatically injected if omitted.

3. **Iterative Self-Correction**:
   - If `execute_sql` returns an error (syntax error, missing column, ambiguous join), read the error message carefully.
   - Correct the specific column or join reference without repeating the mistake.

4. **Answer Synthesis & Output Offloading**:
   - Summarize the query results clearly in natural language with markdown tables when helpful.
   - If results are large, they will be preserved via a `DataPointer`; summarize the key patterns and provide totals.
