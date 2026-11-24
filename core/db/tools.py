"""Database Agent Tools compatible with ToolDispatcher and agent loops."""

from typing import Any, Dict, List, Optional
from .engine import DatabaseEngine, QueryResult
from .sanitizer import SqlSanitizer, SanitizedQuery


class DatabaseTools:
    """Standard database query and schema introspection tools for LLM agent loops."""

    def __init__(self, engine: DatabaseEngine, sanitizer: Optional[SqlSanitizer] = None):
        self.engine = engine
        self.sanitizer = sanitizer or SqlSanitizer()

    def list_tables(self) -> List[str]:
        """List all table names available in the database."""
        schema = self.engine.introspect_schema(sample_rows_count=0)
        return schema.get_table_names()

    def get_table_schema(self, table_name: str) -> str:
        """Get the detailed schema definition and sample rows for a specific table."""
        schema = self.engine.introspect_schema(
            included_tables=[table_name],
            sample_rows_count=2,
        )
        tbl = schema.get_table(table_name)
        if not tbl:
            return f"Table '{table_name}' does not exist in database."
        return tbl.to_ddl()

    def execute_sql(
        self,
        sql: str,
        default_limit: int = 100,
        max_limit: int = 1000,
    ) -> Dict[str, Any]:
        """Sanitizes, checks read-only safety, and executes an SQL query.
        Returns a dictionary with query columns, rows, and execution metadata.
        """
        # 1. AST Validation and Sanitization (Layer 2)
        sanitized: SanitizedQuery = self.sanitizer.sanitize(
            sql=sql,
            dialect=self.engine.dialect,
            default_limit=default_limit,
            max_limit=max_limit,
        )

        # 2. Database Execution (Layer 1)
        res: QueryResult = self.engine.execute_query(sql=sanitized.sql)

        return {
            "success": True,
            "sql": sanitized.sql,
            "row_count": res.row_count,
            "columns": res.columns,
            "rows": res.rows,
            "truncated": res.truncated,
        }
