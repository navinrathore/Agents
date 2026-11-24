"""Unit and Integration tests for Phase 3: DatabaseAgent and ReAct loop."""

import pytest
from sqlalchemy import create_engine, text
from unittest.mock import MagicMock

from core.llm_clients import BaseLLMClient
from core.db import (
    DatabaseEngine,
    SqlSanitizer,
    DatabaseTools,
    DatabaseAgent,
    DatabaseAgentResponse,
    BaseDatabaseAgent,
)


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
            CREATE TABLE products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                price REAL NOT NULL
            );
            """
            )
        )
        conn.execute(
            text(
                """
            INSERT INTO products (title, category, price) VALUES
            ('Laptop Pro', 'Electronics', 1200.0),
            ('Wireless Mouse', 'Electronics', 25.0),
            ('Ergonomic Chair', 'Furniture', 350.0);
            """
            )
        )
    return engine


class MockLLMClient(BaseLLMClient):
    """Mock LLM client that yields predetermined responses."""

    def __init__(self, responses):
        super().__init__(model="mock-model")
        self.responses = list(responses)
        self.call_count = 0
        self.recorded_messages = []

    def generate(self, messages=None, **kwargs):
        self.call_count += 1
        self.recorded_messages.append(messages)
        if self.responses:
            return self.responses.pop(0)
        return "Default mock answer"



def test_database_tools_introspection_and_execution(test_db):
    engine = DatabaseEngine(test_db)
    tools = DatabaseTools(engine)

    # 1. list_tables
    tables = tools.list_tables()
    assert "products" in tables

    # 2. get_table_schema
    ddl = tools.get_table_schema("products")
    assert "CREATE TABLE products" in ddl
    assert "price REAL NOT NULL" in ddl

    # 3. execute_sql safe query
    res = tools.execute_sql("SELECT * FROM products WHERE price > 100")
    assert res["success"] is True
    assert res["row_count"] == 2
    assert "LIMIT" in res["sql"]


def test_database_agent_successful_single_turn(test_db):
    engine = DatabaseEngine(test_db)

    # First call generates SQL, second call generates final synthesis
    mock_llm = MockLLMClient(
        [
            "```sql\nSELECT title, price FROM products WHERE category = 'Electronics' ORDER BY price DESC\n```",
            "The electronics products are Laptop Pro ($1200.0) and Wireless Mouse ($25.0).",
        ]
    )

    agent = DatabaseAgent(
        engine=engine,
        llm_client=mock_llm,
        max_loops=3,
        default_limit=50,
    )

    resp: DatabaseAgentResponse = agent.run("Show me all electronics products sorted by price.")

    assert resp.success is True
    assert resp.loops_taken == 1
    assert "Laptop Pro" in resp.answer
    assert resp.query_result is not None
    assert resp.query_result.row_count == 2
    assert "LIMIT 50" in resp.sql


def test_database_agent_self_correction_loop_on_runtime_error(test_db):
    engine = DatabaseEngine(test_db)

    # Turn 1: LLM generates query with nonexistent column 'cost' -> raises DB error
    # Turn 2: LLM receives isolated error and corrects column to 'price'
    # Turn 3: LLM synthesizes final answer
    mock_llm = MockLLMClient(
        [
            "```sql\nSELECT title, cost FROM products\n```",
            "```sql\nSELECT title, price FROM products\n```",
            "There are 3 products in total.",
        ]
    )

    agent = DatabaseAgent(
        engine=engine,
        llm_client=mock_llm,
        max_loops=4,
    )

    resp = agent.run("List all products.")

    assert resp.success is True
    assert resp.loops_taken == 2
    assert "There are 3 products" in resp.answer
    assert resp.query_result.row_count == 3


def test_database_agent_self_correction_loop_on_sanitizer_error(test_db):
    engine = DatabaseEngine(test_db)

    # Turn 1: LLM generates forbidden DROP TABLE -> caught by SqlSanitizer
    # Turn 2: LLM corrects to safe SELECT
    # Turn 3: Final synthesis
    mock_llm = MockLLMClient(
        [
            "```sql\nDROP TABLE products\n```",
            "```sql\nSELECT COUNT(*) AS total FROM products\n```",
            "There are 3 products in the table.",
        ]
    )

    agent = DatabaseAgent(
        engine=engine,
        llm_client=mock_llm,
        max_loops=3,
    )

    resp = agent.run("Count the products.")

    assert resp.success is True
    assert resp.loops_taken == 2
    assert resp.query_result.row_count == 1


def test_database_agent_circuit_breaker_max_loops_exceeded(test_db):
    engine = DatabaseEngine(test_db)

    # LLM keeps generating invalid SQL on every turn
    mock_llm = MockLLMClient(
        [
            "```sql\nSELECT invalid_col_1 FROM products\n```",
            "```sql\nSELECT invalid_col_2 FROM products\n```",
            "```sql\nSELECT invalid_col_3 FROM products\n```",
        ]
    )

    agent = DatabaseAgent(
        engine=engine,
        llm_client=mock_llm,
        max_loops=2,  # Hard ceiling of 2
    )

    resp = agent.run("Show products.")

    assert resp.success is False
    assert resp.loops_taken == 2
    assert resp.metadata.get("max_loops_exceeded") is True
    assert "Database Runtime Error" in resp.error
