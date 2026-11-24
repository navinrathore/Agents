"""Database module for NL-to-SQL agent."""

from .engine import (
    ColumnMetadata,
    ForeignKeyMetadata,
    TableMetadata,
    DatabaseSchema,
    QueryResult,
    DatabaseEngine,
)
from .sanitizer import (
    SqlSanitizationError,
    SqlSyntaxError,
    MultiStatementQueryError,
    UnsafeQueryError,
    SanitizedQuery,
    SqlSanitizer,
)

__all__ = [
    "ColumnMetadata",
    "ForeignKeyMetadata",
    "TableMetadata",
    "DatabaseSchema",
    "QueryResult",
    "DatabaseEngine",
    "SqlSanitizationError",
    "SqlSyntaxError",
    "MultiStatementQueryError",
    "UnsafeQueryError",
    "SanitizedQuery",
    "SqlSanitizer",
]

