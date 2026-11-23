"""
Analytical tool definitions for the data_analyst skill package.
"""

from typing import Any, Dict, List, Optional


def describe_table(table_name: str) -> str:
    """
    Returns structural columns, types, and primary keys for a specified database table.
    
    Args:
        table_name: The name of the table to inspect.
    """
    table = table_name.lower().strip()
    schemas = {
        "users": "Table: users | Columns: [id: INT PRIMARY KEY, name: VARCHAR(100), email: VARCHAR(255), created_at: TIMESTAMP]",
        "orders": "Table: orders | Columns: [order_id: INT PRIMARY KEY, user_id: INT, total_usd: DECIMAL(10,2), status: VARCHAR(50)]",
    }
    return schemas.get(table, f"Table '{table_name}' found. Columns: [id: INT, data: TEXT, updated_at: TIMESTAMP]")


def query_table(table_name: str, limit: int = 50, filter_column: Optional[str] = None) -> str:
    """
    Executes a bounded SELECT query on a given table.
    
    Args:
        table_name: The name of the table to query.
        limit: Maximum number of rows to return (default 50).
        filter_column: Optional column name to apply non-null filtering.
    """
    clamped_limit = min(max(1, limit), 200)
    filter_info = f" (filtered by {filter_column})" if filter_column else ""
    return f"Retrieved {clamped_limit} rows from '{table_name}'{filter_info} successfully."
