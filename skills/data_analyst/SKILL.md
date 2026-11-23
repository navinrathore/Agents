---
name: data_analyst
description: Inspect database schemas, describe table structures, and run bounded analytical queries.
version: 1.0.0
triggers:
  - database
  - sql
  - query table
  - data analysis
tags:
  - analytics
  - sql
requires_approval: false
---

# SQL Data Analyst SOP

When assisting the user with database analysis:
1. Always start by checking available tables or describing schemas with `describe_table()`.
2. Formulate targeted, non-mutating queries.
3. Ensure all SQL queries include a safety `LIMIT` clause (default 50 rows).
4. Present findings clearly with column headers and statistical summaries.
