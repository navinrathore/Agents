"""Layer 1: Database Connection & Schema Introspection Engine.

Uses SQLAlchemy for deterministic reflection, connection pooling, and scoped read-only execution.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Union
import re
from sqlalchemy import (
    create_engine,
    inspect,
    text,
    Engine,
    CursorResult,
)
from sqlalchemy.exc import SQLAlchemyError


@dataclass
class ColumnMetadata:
    """Metadata describing a database column."""
    name: str
    type: str
    nullable: bool = True
    primary_key: bool = False
    default: Optional[str] = None


@dataclass
class ForeignKeyMetadata:
    """Metadata describing a foreign key relationship."""
    constrained_columns: List[str]
    referred_table: str
    referred_columns: List[str]


@dataclass
class TableMetadata:
    """Metadata describing a database table."""
    name: str
    columns: List[ColumnMetadata] = field(default_factory=list)
    foreign_keys: List[ForeignKeyMetadata] = field(default_factory=list)
    sample_rows: List[Dict[str, Any]] = field(default_factory=list)

    def to_ddl(self) -> str:
        """Format column definitions and foreign keys into a clean CREATE TABLE statement."""
        col_defs = []
        for col in self.columns:
            parts = [f"  {col.name} {col.type}"]
            if col.primary_key:
                parts.append("PRIMARY KEY")
            elif not col.nullable:
                parts.append("NOT NULL")
            if col.default is not None:
                parts.append(f"DEFAULT {col.default}")
            col_defs.append(" ".join(parts))

        for fk in self.foreign_keys:
            cols = ", ".join(fk.constrained_columns)
            ref_cols = ", ".join(fk.referred_columns)
            col_defs.append(f"  FOREIGN KEY ({cols}) REFERENCES {fk.referred_table} ({ref_cols})")

        body = ",\n".join(col_defs)
        return f"CREATE TABLE {self.name} (\n{body}\n);"


@dataclass
class DatabaseSchema:
    """Full database schema reflection and prompt context."""
    dialect: str
    tables: Dict[str, TableMetadata] = field(default_factory=dict)
    generated_ddl: str = ""

    def get_table_names(self) -> List[str]:
        return list(self.tables.keys())

    def get_table(self, name: str) -> Optional[TableMetadata]:
        return self.tables.get(name)


@dataclass
class QueryResult:
    """Result of a query execution."""
    columns: List[str]
    rows: List[Dict[str, Any]]
    row_count: int
    truncated: bool = False
    raw_sql: str = ""


class DatabaseEngine:
    """Layer 1 Database Engine providing schema reflection and safe query execution."""

    def __init__(self, connection_url_or_engine: Union[str, Engine], echo: bool = False):
        if isinstance(connection_url_or_engine, Engine):
            self.engine = connection_url_or_engine
        else:
            self.engine = create_engine(connection_url_or_engine, echo=echo)

        self._dialect_name = self._normalize_dialect(self.engine.dialect.name)

    @property
    def dialect(self) -> str:
        """Normalized dialect name: 'sqlite', 'postgres', etc."""
        return self._dialect_name

    @staticmethod
    def _normalize_dialect(raw_dialect: str) -> str:
        dialect = raw_dialect.lower()
        if "sqlite" in dialect:
            return "sqlite"
        if "postgres" in dialect or "psycopg" in dialect:
            return "postgres"
        return dialect

    def introspect_schema(
        self,
        included_tables: Optional[Sequence[str]] = None,
        excluded_tables: Optional[Sequence[str]] = None,
        sample_rows_count: int = 2,
    ) -> DatabaseSchema:
        """Reflect database tables, columns, foreign keys, and optional sample rows."""
        inspector = inspect(self.engine)
        all_table_names = inspector.get_table_names()

        target_tables = []
        for tbl in all_table_names:
            if included_tables and tbl not in included_tables:
                continue
            if excluded_tables and tbl in excluded_tables:
                continue
            target_tables.append(tbl)

        tables_meta: Dict[str, TableMetadata] = {}
        ddl_parts: List[str] = []

        with self.engine.connect() as conn:
            for tbl in target_tables:
                # 1. Columns
                columns: List[ColumnMetadata] = []
                for col in inspector.get_columns(tbl):
                    columns.append(
                        ColumnMetadata(
                            name=col["name"],
                            type=str(col["type"]),
                            nullable=col.get("nullable", True),
                            primary_key=bool(col.get("primary_key", False)),
                            default=str(col.get("default")) if col.get("default") is not None else None,
                        )
                    )

                # 2. Foreign Keys
                fks: List[ForeignKeyMetadata] = []
                for fk in inspector.get_foreign_keys(tbl):
                    fks.append(
                        ForeignKeyMetadata(
                            constrained_columns=fk.get("constrained_columns", []),
                            referred_table=fk.get("referred_table", ""),
                            referred_columns=fk.get("referred_columns", []),
                        )
                    )

                # 3. Sample Rows (Bounded, parameterized / sanitized identifier)
                samples: List[Dict[str, Any]] = []
                if sample_rows_count > 0:
                    try:
                        # Clean table identifier to prevent injection
                        safe_tbl = self._quote_identifier(tbl)
                        sample_stmt = text(f"SELECT * FROM {safe_tbl} LIMIT :limit")
                        res = conn.execute(sample_stmt, {"limit": sample_rows_count})
                        for row in res.mappings():
                            samples.append(dict(row))
                    except Exception:
                        # Table might be empty or restricted, continue gracefully
                        samples = []

                meta = TableMetadata(
                    name=tbl,
                    columns=columns,
                    foreign_keys=fks,
                    sample_rows=samples,
                )
                tables_meta[tbl] = meta

                # Build DDL block
                ddl = meta.to_ddl()
                if samples:
                    ddl += f"\n-- Sample rows ({tbl}):\n"
                    for s in samples:
                        ddl += f"-- {s}\n"
                ddl_parts.append(ddl)

        generated_ddl = "\n\n".join(ddl_parts)
        return DatabaseSchema(
            dialect=self.dialect,
            tables=tables_meta,
            generated_ddl=generated_ddl,
        )

    def _quote_identifier(self, identifier: str) -> str:
        """Safely quotes an SQL identifier according to the dialect."""
        # Simple identifier validation: letters, digits, underscores
        if not re.match(r"^[A-Za-z0-9_]+$", identifier):
            raise ValueError(f"Unsafe table identifier: {identifier}")
        if self.dialect == "postgres":
            return f'"{identifier}"'
        elif self.dialect == "sqlite":
            return f'"{identifier}"'
        return f"`{identifier}`"

    def execute_query(
        self,
        sql: str,
        parameters: Optional[Dict[str, Any]] = None,
        max_rows: Optional[int] = None,
    ) -> QueryResult:
        """Executes a query and returns structured QueryResult."""
        parameters = parameters or {}
        try:
            with self.engine.connect() as conn:
                stmt = text(sql)
                result: CursorResult = conn.execute(stmt, parameters)

                if not result.returns_rows:
                    return QueryResult(
                        columns=[],
                        rows=[],
                        row_count=0,
                        truncated=False,
                        raw_sql=sql,
                    )

                columns = list(result.keys())
                rows: List[Dict[str, Any]] = []
                truncated = False

                for row in result.mappings():
                    if max_rows and len(rows) >= max_rows:
                        truncated = True
                        break
                    rows.append(dict(row))

                return QueryResult(
                    columns=columns,
                    rows=rows,
                    row_count=len(rows),
                    truncated=truncated,
                    raw_sql=sql,
                )
        except SQLAlchemyError as exc:
            # Re-raise clean exception for the agent error-recovery loop
            raise RuntimeError(f"Database query execution error: {str(exc)}") from exc
