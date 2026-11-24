---
name: sql_operational_invariants
description: Relational database safety boundaries and read-only invariants
scope:
  - database
  - sql
  - analytics
priority: 25
immutable: false
enabled: true
---

# Relational Database Invariants
1. **Read-Only Guarantees**: ONLY execute read-only queries (SELECT or WITH ... SELECT). DDL and DML statements are strictly forbidden.
2. **Schema Verification**: Always verify column and table names against the reflected database schema graph before generating queries.
3. **Explicit Row Limits**: Always append bounded limits to result sets to avoid memory exhaustion.
