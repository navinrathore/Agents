"""Database module for NL-to-SQL agent."""

from .engine import (
    ColumnMetadata,
    ForeignKeyMetadata,
    TableMetadata,
    DatabaseSchema,
    QueryResult,
    DatabaseEngine,
)

__all__ = [
    "ColumnMetadata",
    "ForeignKeyMetadata",
    "TableMetadata",
    "DatabaseSchema",
    "QueryResult",
    "DatabaseEngine",
]
