"""Abstract base interface for Database Agents (Layer 3 Orchestration).

Provides an extensible contract so external frameworks (e.g. LangChain, Vanna) or custom
ReAct orchestrators can be plugged in interchangeably.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from .engine import QueryResult


@dataclass
class DatabaseAgentResponse:
    """Standardized response from a database agent execution."""
    answer: str
    sql: Optional[str] = None
    query_result: Optional[QueryResult] = None
    pointer_id: Optional[str] = None
    loops_taken: int = 1
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseDatabaseAgent(ABC):
    """Abstract Base Class for Database Query Agents."""

    @abstractmethod
    def run(self, user_query: str) -> DatabaseAgentResponse:
        """Execute a natural language query synchronously against the database."""
        pass

    @abstractmethod
    async def run_async(self, user_query: str) -> DatabaseAgentResponse:
        """Execute a natural language query asynchronously against the database."""
        pass
