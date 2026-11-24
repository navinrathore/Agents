"""Unit tests for Phase 1: DatabaseEngine and Schema Introspection."""

import pytest
from sqlalchemy import create_engine, text
from core.db.engine import (
    DatabaseEngine,
    TableMetadata,
    ColumnMetadata,
    ForeignKeyMetadata,
    DatabaseSchema,
    QueryResult,
)


@pytest.fixture
def memory_db():
    """Create an in-memory SQLite database populated with test schema and data."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
            CREATE TABLE departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                budget REAL DEFAULT 10000.0
            );
            """
            )
        )
        conn.execute(
            text(
                """
            CREATE TABLE employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT UNIQUE,
                dept_id INTEGER,
                salary REAL,
                FOREIGN KEY (dept_id) REFERENCES departments(id)
            );
            """
            )
        )
        # Seed sample rows
        conn.execute(
            text(
                """
            INSERT INTO departments (name, budget) VALUES
            ('Engineering', 500000.0),
            ('Marketing', 150000.0);
            """
            )
        )
        conn.execute(
            text(
                """
            INSERT INTO employees (first_name, last_name, email, dept_id, salary) VALUES
            ('Alice', 'Smith', 'alice@example.com', 1, 120000.0),
            ('Bob', 'Jones', 'bob@example.com', 1, 110000.0),
            ('Charlie', 'Brown', 'charlie@example.com', 2, 85000.0);
            """
            )
        )
    return engine


def test_database_engine_dialect_normalization(memory_db):
    db_engine = DatabaseEngine(memory_db)
    assert db_engine.dialect == "sqlite"


def test_schema_introspection_tables_and_columns(memory_db):
    db_engine = DatabaseEngine(memory_db)
    schema = db_engine.introspect_schema(sample_rows_count=2)

    assert isinstance(schema, DatabaseSchema)
    assert schema.dialect == "sqlite"
    assert set(schema.get_table_names()) == {"departments", "employees"}

    # Test departments table metadata
    dept_table = schema.get_table("departments")
    assert dept_table is not None
    assert dept_table.name == "departments"
    col_names = [col.name for col in dept_table.columns]
    assert col_names == ["id", "name", "budget"]

    # Verify primary key and nullability
    id_col = next(c for c in dept_table.columns if c.name == "id")
    assert id_col.primary_key is True

    # Test foreign keys on employees
    emp_table = schema.get_table("employees")
    assert emp_table is not None
    assert len(emp_table.foreign_keys) == 1
    fk = emp_table.foreign_keys[0]
    assert fk.referred_table == "departments"
    assert fk.constrained_columns == ["dept_id"]


def test_schema_introspection_sample_rows_and_ddl(memory_db):
    db_engine = DatabaseEngine(memory_db)
    schema = db_engine.introspect_schema(sample_rows_count=2)

    dept_table = schema.get_table("departments")
    assert len(dept_table.sample_rows) == 2
    assert dept_table.sample_rows[0]["name"] == "Engineering"

    # DDL generation
    ddl = schema.generated_ddl
    assert "CREATE TABLE departments" in ddl
    assert "CREATE TABLE employees" in ddl
    assert "FOREIGN KEY (dept_id) REFERENCES departments" in ddl
    assert "-- Sample rows (departments):" in ddl


def test_schema_introspection_filtering(memory_db):
    db_engine = DatabaseEngine(memory_db)

    # Included tables only
    schema = db_engine.introspect_schema(included_tables=["departments"])
    assert schema.get_table_names() == ["departments"]
    assert "CREATE TABLE employees" not in schema.generated_ddl

    # Excluded tables
    schema2 = db_engine.introspect_schema(excluded_tables=["departments"])
    assert schema2.get_table_names() == ["employees"]


def test_query_execution_success(memory_db):
    db_engine = DatabaseEngine(memory_db)
    result = db_engine.execute_query(
        "SELECT id, first_name, salary FROM employees WHERE salary > :min_sal ORDER BY salary DESC",
        parameters={"min_sal": 100000.0},
    )

    assert isinstance(result, QueryResult)
    assert result.columns == ["id", "first_name", "salary"]
    assert result.row_count == 2
    assert result.rows[0]["first_name"] == "Alice"
    assert result.rows[1]["first_name"] == "Bob"
    assert result.truncated is False


def test_query_execution_with_max_rows_truncation(memory_db):
    db_engine = DatabaseEngine(memory_db)
    result = db_engine.execute_query("SELECT * FROM employees", max_rows=1)
    assert result.row_count == 1
    assert result.truncated is True


def test_query_execution_error_handling(memory_db):
    db_engine = DatabaseEngine(memory_db)
    with pytest.raises(RuntimeError) as exc_info:
        db_engine.execute_query("SELECT * FROM non_existent_table")
    assert "Database query execution error" in str(exc_info.value)


def test_quote_identifier_safety(memory_db):
    db_engine = DatabaseEngine(memory_db)
    assert db_engine._quote_identifier("valid_table") == '"valid_table"'
    with pytest.raises(ValueError, match="Unsafe table identifier"):
        db_engine._quote_identifier("table_name; DROP TABLE users;")
