"""Tool functions for database_agent skill package.

Provides high-level tools backed by core.db DatabaseEngine and SqlSanitizer.
Configurable via environment variable DATABASE_URL or defaults to sqlite:///:memory:.
"""

import os
from typing import Any, Dict, List, Optional
from core.db import DatabaseEngine, DatabaseTools

# Global engine/tools instance cached per process
_engine: Optional[DatabaseEngine] = None
_tools: Optional[DatabaseTools] = None


def _get_tools() -> DatabaseTools:
    global _engine, _tools
    if _tools is None:
        db_url = os.getenv("DATABASE_URL", "sqlite:///:memory:")
        _engine = DatabaseEngine(db_url)
        _tools = DatabaseTools(_engine)
    return _tools


def set_database_engine(engine: DatabaseEngine) -> None:
    """Allows programmatically configuring the active DatabaseEngine for this skill."""
    global _engine, _tools
    _engine = engine
    _tools = DatabaseTools(engine)


def list_tables() -> List[str]:
    """List all table names available in the active database.
    
    Returns:
        List of table names.
    """
    return _get_tools().list_tables()


def get_table_schema(table_name: str) -> str:
    """Get the detailed schema definition (CREATE TABLE DDL) and sample rows for a table.
    
    Args:
        table_name: The name of the table to inspect.
    """
    return _get_tools().get_table_schema(table_name)


def execute_sql(sql: str, limit: int = 100) -> Dict[str, Any]:
    """Sanitizes, AST-validates, and executes a read-only SQL query against the database.
    
    Args:
        sql: The SQL query to execute (SELECT or WITH ... SELECT).
        limit: Max rows to return (default 100).
    """
    try:
        return _get_tools().execute_sql(sql=sql, default_limit=limit)
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }
