import asyncio
import inspect
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Coroutine, Dict, List, Optional, Union


@dataclass
class ToolExecutionResult:
    """Represents the structured execution outcome of a single tool call."""
    tool_call_id: str
    name: str
    result: str
    success: bool = True
    error: Optional[str] = None
    duration: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def is_coroutine_callable(fn: Any) -> bool:
    """Checks whether a function or callable instance is an async coroutine function."""
    if inspect.iscoroutinefunction(fn):
        return True
    if hasattr(fn, "__call__") and inspect.iscoroutinefunction(fn.__call__):
        return True
    return False


def to_async_tool(sync_fn: Callable[..., Any]) -> Callable[..., Coroutine[Any, Any, Any]]:
    """
    Wraps a synchronous callable to execute non-blockingly in a separate worker thread
    via asyncio.to_thread.
    """
    async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(sync_fn, *args, **kwargs)

    return async_wrapper


class AsyncToolDispatcher:
    """
    Concurrent, fault-isolated tool dispatcher for agentic workflows.
    Executes multiple tool calls emitted in an LLM turn concurrently using asyncio,
    enforces per-tool execution timeouts, isolates failures, and preserves result order.
    """

    def __init__(self, default_timeout: float = 30.0):
        self.default_timeout = default_timeout
        self.tools: Dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {}

    def register_tool(
        self,
        name: str,
        fn: Callable[..., Any],
        is_async: Optional[bool] = None,
    ) -> None:
        """
        Registers a tool by name. If the tool is synchronous, it is automatically
        adapted to an async callable using asyncio.to_thread.
        """
        if is_async is None:
            is_async = is_coroutine_callable(fn)

        if is_async:
            self.tools[name] = fn
        else:
            self.tools[name] = to_async_tool(fn)

    def unregister_tool(self, name: str) -> None:
        """Removes a registered tool by name."""
        if name in self.tools:
            del self.tools[name]

    def has_tool(self, name: str) -> bool:
        """Returns True if the tool name is registered."""
        return name in self.tools

    async def _execute_single_tool(
        self,
        tool_call: Dict[str, Any],
        timeout: float,
    ) -> ToolExecutionResult:
        """
        Executes a single tool call with timeout enforcement and error shielding.
        """
        tool_id = tool_call.get("id", "")
        name = tool_call.get("name", "")
        inputs = tool_call.get("input", {}) or {}

        if not isinstance(inputs, dict):
            inputs = {"arg": inputs}

        start_time = time.perf_counter()

        if name not in self.tools:
            duration = time.perf_counter() - start_time
            err_msg = f"Error: Unknown or unregistered tool '{name}'."
            return ToolExecutionResult(
                tool_call_id=tool_id,
                name=name,
                result=err_msg,
                success=False,
                error=err_msg,
                duration=round(duration, 4),
            )

        tool_fn = self.tools[name]

        try:
            # Enforce per-tool timeout
            res = await asyncio.wait_for(tool_fn(**inputs), timeout=timeout)
            duration = time.perf_counter() - start_time
            result_str = str(res) if res is not None else ""
            return ToolExecutionResult(
                tool_call_id=tool_id,
                name=name,
                result=result_str,
                success=True,
                error=None,
                duration=round(duration, 4),
            )
        except asyncio.TimeoutError:
            duration = time.perf_counter() - start_time
            err_msg = f"Error: Tool execution timed out after {timeout}s."
            return ToolExecutionResult(
                tool_call_id=tool_id,
                name=name,
                result=err_msg,
                success=False,
                error=err_msg,
                duration=round(duration, 4),
            )
        except Exception as exc:
            duration = time.perf_counter() - start_time
            err_msg = f"Error: Tool '{name}' failed with {type(exc).__name__}: {str(exc)}"
            return ToolExecutionResult(
                tool_call_id=tool_id,
                name=name,
                result=err_msg,
                success=False,
                error=err_msg,
                duration=round(duration, 4),
            )

    async def dispatch(
        self,
        tool_calls: List[Dict[str, Any]],
        timeout: Optional[float] = None,
    ) -> List[ToolExecutionResult]:
        """
        Executes multiple tool calls concurrently in parallel.
        Guarantees:
        1. Non-blocking concurrent execution via asyncio.create_task + asyncio.gather.
        2. Per-tool timeout and error shielding (one failing tool never aborts siblings).
        3. Strict order preservation matching the input tool_calls sequence.
        """
        if not tool_calls:
            return []

        effective_timeout = timeout if timeout is not None else self.default_timeout

        tasks = [
            asyncio.create_task(self._execute_single_tool(tc, effective_timeout))
            for tc in tool_calls
        ]

        # asyncio.gather preserves the original order of the tasks list
        results: List[ToolExecutionResult] = await asyncio.gather(*tasks)
        return results
