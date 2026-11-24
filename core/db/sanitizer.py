"""Layer 2: SQL AST Parsing, Validation & Sanitization Engine.

Uses sqlglot for deterministic AST statement classification, strict read-only enforcement,
single-statement constraints, default LIMIT injection, and dialect transpilation.
"""

from dataclasses import dataclass
from typing import Any, List, Optional, Set, Tuple, Type
import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from core.sanitizer import CodeSanitizer, ExtractionStrategy


class SqlSanitizationError(Exception):
    """Base exception for SQL sanitization errors."""
    pass


class SqlSyntaxError(SqlSanitizationError):
    """Raised when the query string cannot be parsed into a valid SQL AST."""
    pass


class MultiStatementQueryError(SqlSanitizationError):
    """Raised when multiple SQL statements are detected in a single payload."""
    pass


class UnsafeQueryError(SqlSanitizationError):
    """Raised when a non-read-only or forbidden statement/clause is detected."""
    pass


@dataclass
class SanitizedQuery:
    """Outcome of the SQL sanitization process."""
    sql: str
    original_sql: str
    dialect: str
    is_modified: bool
    ast_expression_type: str
    injected_limit: Optional[int] = None


class SqlSanitizer:
    """Layer 2 SQL Sanitization and AST Guardrail Engine."""

    # Disallowed AST node types representing mutations, DDL, or administrative control
    FORBIDDEN_EXPRESSION_TYPES: Tuple[Type[exp.Expression], ...] = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Create,
        exp.Alter,
        exp.Command,
        exp.Commit,
        exp.Rollback,
        exp.TruncateTable,
        exp.Merge,
        exp.Transaction,
        exp.Set,
        exp.Pragma,
    )

    @classmethod
    def sanitize(
        cls,
        sql: str,
        dialect: str = "sqlite",
        default_limit: int = 100,
        max_limit: int = 1000,
        extract_code_blocks: bool = True,
    ) -> SanitizedQuery:
        """Complete sanitization pipeline:
        1. Extract raw SQL from markdown fences/conversational text (if present).
        2. Verify single statement constraint.
        3. Parse into dialect-aware AST.
        4. Validate read-only assertion (SELECT/CTE only; no DML/DDL).
        5. Inject or clamp LIMIT clause.
        6. Return clean SQL string and metadata.
        """
        normalized_dialect = cls._normalize_dialect(dialect)
        raw_input = sql

        # Step 1: Extract from fences/text using CodeSanitizer
        cleaned_sql = sql
        if extract_code_blocks:
            res = CodeSanitizer.sanitize(
                text=sql,
                language="sql",
                strategy=ExtractionStrategy.LONGEST,
                validate_syntax=False,
            )
            cleaned_sql = res.code.strip()

        if not cleaned_sql:
            raise SqlSyntaxError("Empty SQL query payload")

        # Step 2: Multi-statement check
        try:
            statements = sqlglot.parse(cleaned_sql, read=normalized_dialect)
        except ParseError as exc:
            raise SqlSyntaxError(f"SQL parsing syntax error: {str(exc)}") from exc

        # Filter out empty/None statements
        valid_statements = [stmt for stmt in statements if stmt is not None]
        if len(valid_statements) == 0:
            raise SqlSyntaxError("No valid SQL statements found in payload")
        if len(valid_statements) > 1:
            raise MultiStatementQueryError(
                f"Multi-statement queries are forbidden. Detected {len(valid_statements)} statements."
            )

        ast = valid_statements[0]

        # Step 3: Validate read-only nature
        cls.validate_read_only(ast)

        # Step 4: Inject or clamp LIMIT
        ast, injected_limit = cls.inject_or_clamp_limit(
            ast=ast,
            default_limit=default_limit,
            max_limit=max_limit,
        )

        final_sql = ast.sql(dialect=normalized_dialect)
        is_modified = (final_sql != raw_input.strip())

        return SanitizedQuery(
            sql=final_sql,
            original_sql=raw_input,
            dialect=normalized_dialect,
            is_modified=is_modified,
            ast_expression_type=ast.__class__.__name__,
            injected_limit=injected_limit,
        )

    @classmethod
    def validate_read_only(cls, ast: exp.Expression) -> None:
        """Validates that the AST represents strictly a read-only query (SELECT or WITH ... SELECT).
        Raises UnsafeQueryError if any mutation, DDL, or administrative node is present.
        """
        # 1. The top-level query must be Select or With or Union
        if isinstance(ast, exp.With):
            # Check the body of the CTE
            body = ast.this
            if not isinstance(body, (exp.Select, exp.Union)):
                raise UnsafeQueryError(
                    f"CTE root body must be a SELECT or UNION query, got {body.__class__.__name__}"
                )
        elif isinstance(ast, (exp.Select, exp.Union)):
            pass
        else:
            raise UnsafeQueryError(
                f"Only SELECT or WITH queries are permitted. Detected root operation: {ast.__class__.__name__}"
            )

        # 2. Walk AST to detect any nested mutations (e.g. subquery mutations or data modifications)
        for node in ast.walk():
            if isinstance(node, cls.FORBIDDEN_EXPRESSION_TYPES):
                raise UnsafeQueryError(
                    f"Forbidden statement or clause detected in query: {node.__class__.__name__}"
                )

    @classmethod
    def inject_or_clamp_limit(
        cls,
        ast: exp.Expression,
        default_limit: int = 100,
        max_limit: int = 1000,
    ) -> Tuple[exp.Expression, Optional[int]]:
        """Ensures a LIMIT clause exists on the query and does not exceed max_limit.
        Returns (transformed_ast, limit_value_applied).
        """
        # Find target expression that supports limit (Select or With)
        target: Optional[exp.Expression] = None
        if isinstance(ast, (exp.Select, exp.With, exp.Union)):
            target = ast

        if target is None:
            return ast, None

        limit_node = target.args.get("limit")
        if limit_node is None:
            # Inject default limit using native sqlglot limit method
            transformed = target.limit(default_limit)
            return transformed, default_limit
        else:
            # Limit exists: check and clamp if necessary
            try:
                current_limit_val = int(str(limit_node.expression).strip())
                if current_limit_val > max_limit or current_limit_val < 0:
                    transformed = target.limit(max_limit)
                    return transformed, max_limit
                return target, current_limit_val
            except (ValueError, TypeError, AttributeError):
                transformed = target.limit(default_limit)
                return transformed, default_limit


    @classmethod
    def transpile(cls, sql: str, from_dialect: str, to_dialect: str) -> str:
        """Transpiles SQL query between dialects using sqlglot."""
        from_d = cls._normalize_dialect(from_dialect)
        to_d = cls._normalize_dialect(to_dialect)
        try:
            transpiled = sqlglot.transpile(sql, read=from_d, write=to_d)
            if not transpiled:
                return sql
            return transpiled[0]
        except Exception as exc:
            raise SqlSyntaxError(f"Transpilation failed from {from_d} to {to_d}: {str(exc)}") from exc

    @staticmethod
    def _normalize_dialect(dialect: str) -> str:
        d = dialect.lower()
        if "sqlite" in d:
            return "sqlite"
        if "postgres" in d or "psycopg" in d:
            return "postgres"
        return d
