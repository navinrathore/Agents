"""Unit tests for Phase 2: SqlSanitizer and AST Guardrails."""

import pytest
from core.db.sanitizer import (
    SqlSanitizer,
    SanitizedQuery,
    SqlSanitizationError,
    SqlSyntaxError,
    MultiStatementQueryError,
    UnsafeQueryError,
)


def test_clean_select_query_basic():
    raw_sql = "SELECT id, name FROM users WHERE active = 1"
    res = SqlSanitizer.sanitize(raw_sql, dialect="sqlite", default_limit=50)

    assert isinstance(res, SanitizedQuery)
    assert "LIMIT 50" in res.sql
    assert res.injected_limit == 50
    assert res.ast_expression_type == "Select"


def test_markdown_fence_and_conversational_stripping():
    payload = """
    Sure! Here is the SQL query you need:
    ```sql
    SELECT * FROM employees WHERE salary > 50000;
    ```
    Hope this helps!
    """
    res = SqlSanitizer.sanitize(payload, dialect="sqlite", default_limit=100)
    assert "LIMIT 100" in res.sql
    assert "Sure" not in res.sql
    assert "Hope this helps" not in res.sql


def test_limit_preservation_and_clamping():
    # Existing limit below max_limit is preserved
    sql1 = "SELECT * FROM orders LIMIT 25"
    res1 = SqlSanitizer.sanitize(sql1, default_limit=100, max_limit=1000)
    assert "LIMIT 25" in res1.sql
    assert res1.injected_limit == 25

    # Existing limit exceeding max_limit is clamped
    sql2 = "SELECT * FROM orders LIMIT 50000"
    res2 = SqlSanitizer.sanitize(sql2, default_limit=100, max_limit=500)
    assert "LIMIT 500" in res2.sql
    assert res2.injected_limit == 500


def test_complex_cte_with_clause_allowed():
    cte_sql = """
    WITH dept_avg AS (
        SELECT dept_id, AVG(salary) AS avg_sal
        FROM employees
        GROUP BY dept_id
    )
    SELECT e.first_name, e.salary, d.avg_sal
    FROM employees e
    JOIN dept_avg d ON e.dept_id = d.dept_id
    WHERE e.salary > d.avg_sal
    """
    res = SqlSanitizer.sanitize(cte_sql, dialect="postgres", default_limit=20)
    assert "LIMIT 20" in res.sql
    assert "WITH dept_avg AS" in res.sql
    assert res.ast_expression_type == "Select"
    assert res.injected_limit == 20



def test_multi_statement_rejection():
    dangerous_sql = "SELECT * FROM users; DROP TABLE users;"
    with pytest.raises(MultiStatementQueryError, match="Multi-statement queries are forbidden"):
        SqlSanitizer.sanitize(dangerous_sql, dialect="sqlite")


@pytest.mark.parametrize(
    "forbidden_sql",
    [
        "DROP TABLE users",
        "DELETE FROM users WHERE id = 1",
        "UPDATE employees SET salary = salary * 1.5",
        "INSERT INTO users (name) VALUES ('hacker')",
        "ALTER TABLE users ADD COLUMN is_admin INT",
        "TRUNCATE TABLE audit_log",
        "ATTACH DATABASE 'leak.db' AS leak",
    ],
)
def test_dml_and_ddl_rejection(forbidden_sql):
    with pytest.raises(UnsafeQueryError):
        SqlSanitizer.sanitize(forbidden_sql, dialect="sqlite")


def test_empty_or_invalid_syntax():
    with pytest.raises(SqlSyntaxError):
        SqlSanitizer.sanitize("", dialect="sqlite")

    with pytest.raises(SqlSyntaxError):
        SqlSanitizer.sanitize("SELECT FROM WHERE", dialect="sqlite")


def test_dialect_transpilation():
    # Postgres ILIKE transpiled to SQLite LIKE
    pg_sql = "SELECT name FROM users WHERE name ILIKE '%john%'"
    sqlite_sql = SqlSanitizer.transpile(pg_sql, from_dialect="postgres", to_dialect="sqlite")
    assert "LIKE" in sqlite_sql.upper()
