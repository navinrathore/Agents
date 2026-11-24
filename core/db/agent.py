"""Layer 3: Database Agent Implementation.

Token-efficient ReAct supervisory agent utilizing prompt-cached static DDL schemas,
isolated error recovery loops, and OutputGuard pointer offloading.
"""

from typing import Any, Dict, List, Optional
import json

from core.llm_clients import BaseLLMClient
from core.output_guard import OutputGuard
from core.hitl import HITLApprovalGate
from core.rules import RuleManager

from .base import BaseDatabaseAgent, DatabaseAgentResponse
from .engine import DatabaseEngine, DatabaseSchema, QueryResult
from .sanitizer import (
    SqlSanitizer,
    SanitizedQuery,
    SqlSanitizationError,
)


class DatabaseAgent(BaseDatabaseAgent):
    """Token-efficient, bounded ReAct Database Agent for SQLite & PostgreSQL."""

    def __init__(
        self,
        engine: DatabaseEngine,
        llm_client: BaseLLMClient,
        sanitizer: Optional[SqlSanitizer] = None,
        output_guard: Optional[OutputGuard] = None,
        hitl_manager: Optional[HITLApprovalGate] = None,
        max_loops: int = 4,
        default_limit: int = 100,
        max_limit: int = 1000,
        included_tables: Optional[List[str]] = None,
        excluded_tables: Optional[List[str]] = None,
        rule_manager: Optional[RuleManager] = None,
    ):
        self.engine = engine
        self.llm_client = llm_client
        self.sanitizer = sanitizer or SqlSanitizer()
        self.output_guard = output_guard
        self.hitl_manager = hitl_manager
        self.max_loops = max_loops
        self.default_limit = default_limit
        self.max_limit = max_limit
        self.rule_manager = rule_manager

        # Reflect database schema once to maintain a static, prompt-caching friendly prefix
        self.schema: DatabaseSchema = self.engine.introspect_schema(
            included_tables=included_tables,
            excluded_tables=excluded_tables,
            sample_rows_count=2,
        )

        self._static_system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """Constructs a deterministic, static system prompt with DDL schemas and rules."""
        if self.rule_manager:
            role = (
                "You are an expert Database and SQL Assistant.\n"
                f"Target Database Dialect: {self.engine.dialect.upper()}"
            )
            extra_context = [
                f"### DATABASE SCHEMA & SAMPLE DATA:\n{self.schema.generated_ddl}"
            ]
            compiled = self.rule_manager.compile_system_prefix(
                agent_role=role,
                scopes=["database", "sql"],
                extra_static_blocks=extra_context,
            )
            return compiled.system_prompt

        return (
            "You are an expert Database and SQL Assistant.\n"
            f"Target Database Dialect: {self.engine.dialect.upper()}\n\n"
            "### STRICT OPERATIONAL RULES:\n"
            "1. ONLY generate read-only queries (SELECT or WITH ... SELECT). Never generate DDL or DML.\n"
            "2. Always adhere to the schema provided below. Do not hallucinate columns or tables.\n"
            "3. Format your response clearly. When generating SQL, output it inside a ```sql ... ``` code block.\n"
            "4. Provide a concise explanation or answer synthesizing the query results.\n\n"
            "### DATABASE SCHEMA & SAMPLE DATA:\n"
            f"{self.schema.generated_ddl}\n"
        )

    def run(self, user_query: str) -> DatabaseAgentResponse:
        """Synchronously executes the NL-to-SQL ReAct loop with self-correction."""
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self._static_system_prompt},
            {
                "role": "user",
                "content": (
                    f"User Request: {user_query}\n\n"
                    "Please write an SQL query to answer this request."
                ),
            },
        ]

        loops_taken = 0
        last_sql: Optional[str] = None
        last_query_result: Optional[QueryResult] = None
        last_error: Optional[str] = None

        while loops_taken < self.max_loops:
            loops_taken += 1

            # 1. Generate SQL / response from LLM (using stateless generate API)
            raw_text = self.llm_client.generate(messages)
            if not isinstance(raw_text, str):
                raw_text = str(raw_text)

            # 2. Extract and sanitize SQL via Layer 2
            try:
                sanitized: SanitizedQuery = self.sanitizer.sanitize(
                    sql=raw_text,
                    dialect=self.engine.dialect,
                    default_limit=self.default_limit,
                    max_limit=self.max_limit,
                )
                last_sql = sanitized.sql
            except SqlSanitizationError as exc:
                last_error = f"SQL Sanitization Error ({exc.__class__.__name__}): {str(exc)}"
                # Pass isolated error diff into the next turn
                messages.append({"role": "assistant", "content": raw_text})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your generated SQL failed validation:\n{last_error}\n\n"
                            "Please correct the query syntax without modifying other requirements."
                        ),
                    }
                )
                continue

            # 3. Optional HITL checkpoint for restricted operations / tables
            if self.hitl_manager:
                pass

            # 4. Execute query via Layer 1
            try:
                query_result: QueryResult = self.engine.execute_query(sql=sanitized.sql)
                last_query_result = query_result
            except Exception as exc:
                last_error = f"Database Runtime Error: {str(exc)}"
                # Pass isolated error diff into the next turn (Rule 6: token efficiency)
                messages.append({"role": "assistant", "content": raw_text})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"The query failed database execution:\n"
                            f"Failed SQL: {sanitized.sql}\n"
                            f"Database Error: {str(exc)}\n\n"
                            "Please fix the SQL query to resolve this error."
                        ),
                    }
                )
                continue

            # 5. Process Result Set (OutputGuard / Pointer offloading if available)
            pointer_id = None
            rendered_rows = json.dumps(query_result.rows, indent=2, default=str)

            if self.output_guard and len(rendered_rows) > self.output_guard.threshold_chars:
                guard_res = self.output_guard.process(
                    output=rendered_rows,
                    tool_name="execute_sql",
                    custom_metadata={"dialect": self.engine.dialect, "sql": sanitized.sql},
                )
                rendered_rows = guard_res.content
                if guard_res.data_pointer:
                    pointer_id = guard_res.data_pointer.pointer_id

            # 6. Ask LLM to synthesize final natural language answer
            synth_messages: List[Dict[str, str]] = [
                {"role": "system", "content": self._static_system_prompt},
                {"role": "user", "content": user_query},
                {"role": "assistant", "content": f"```sql\n{sanitized.sql}\n```"},
                {
                    "role": "user",
                    "content": (
                        f"Query returned {query_result.row_count} row(s):\n"
                        f"{rendered_rows}\n\n"
                        "Please provide a clear and concise final answer based on these results."
                    ),
                },
            ]

            final_text = self.llm_client.generate(synth_messages)
            if not isinstance(final_text, str):
                final_text = str(final_text)

            return DatabaseAgentResponse(
                answer=final_text,
                sql=sanitized.sql,
                query_result=query_result,
                pointer_id=pointer_id,
                loops_taken=loops_taken,
                success=True,
                metadata={"dialect": self.engine.dialect},
            )

        # Loop threshold exceeded (Circuit breaker - Rule 1 of AGENTS.md)
        return DatabaseAgentResponse(
            answer="Failed to execute query within maximum attempt limit.",
            sql=last_sql,
            query_result=last_query_result,
            loops_taken=loops_taken,
            success=False,
            error=last_error,
            metadata={"max_loops_exceeded": True},
        )


    async def run_async(self, user_query: str) -> DatabaseAgentResponse:
        """Asynchronously executes the NL-to-SQL ReAct loop."""
        # Synchronous execution wrapper (or can call async engine if configured)
        return self.run(user_query)
