import asyncio
import inspect
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Union

from core.output_guard import OutputGuard, OutputGuardMode


@dataclass
class ToolExecutionResult:
    """Represents the structured execution outcome of a single tool call."""
    tool_call_id: str
    name: str
    result: str
    success: bool = True
    error: Optional[str] = None
    duration: float = 0.0
    data_pointer: Optional[Dict[str, Any]] = None
    is_offloaded: bool = False
    is_truncated: bool = False

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
    Configurable, fault-isolated tool dispatcher for agentic workflows.
    Capabilities:
    - Conditional parallel vs. sequential execution toggle.
    - Bounded concurrency with asyncio.Semaphore (prevents thread/memory exhaustion).
    - Tool-level metadata (sequential_only for mutating/side-effect tools).
    - Per-tool timeout enforcement and error shielding.
    - Deterministic order preservation matching LLM request order.
    """

    def __init__(
        self,
        default_timeout: float = 30.0,
        parallel_execution: bool = True,
        max_concurrency: int = 5,
        output_guard: Optional[OutputGuard] = None,
        auto_offload: bool = True,
    ):
        self.default_timeout = default_timeout
        self.parallel_execution = parallel_execution
        self.max_concurrency = max(1, max_concurrency)
        self._semaphore: Optional[asyncio.Semaphore] = None
        self.tools: Dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {}
        self.sequential_tools: Set[str] = set()

        if output_guard is not None:
            self.output_guard: Optional[OutputGuard] = output_guard
        elif auto_offload:
            self.output_guard = OutputGuard(mode=OutputGuardMode.OFFLOAD_AND_TRUNCATE)
        else:
            self.output_guard = None

    @property
    def semaphore(self) -> asyncio.Semaphore:
        """Lazy-loaded semaphore attached to the running event loop."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrency)
        return self._semaphore

    def register_tool(
        self,
        name: str,
        fn: Callable[..., Any],
        is_async: Optional[bool] = None,
        sequential_only: bool = False,
    ) -> None:
        """
        Registers a tool by name.
        - sequential_only: if True, this tool will never be executed concurrently
          with other tools (e.g. for disk writes, table creation, mutations).
        """
        if is_async is None:
            is_async = is_coroutine_callable(fn)

        if is_async:
            self.tools[name] = fn
        else:
            self.tools[name] = to_async_tool(fn)

        if sequential_only:
            self.sequential_tools.add(name)
        elif name in self.sequential_tools:
            self.sequential_tools.remove(name)

    def register_mcp_tool(
        self,
        tool_name: str,
        conn_or_manager: Any,
        server_name: Optional[str] = None,
        sequential_only: bool = False,
    ) -> None:
        """
        Registers an MCP tool directly into the dispatcher.
        Automatically adapts CallToolResult content blocks into text strings for the agent.
        """
        async def _mcp_wrapper(**kwargs: Any) -> str:
            if hasattr(conn_or_manager, "call_tool"):
                if server_name:
                    res = await conn_or_manager.call_tool(server_name, tool_name, arguments=kwargs)
                else:
                    res = await conn_or_manager.call_tool(tool_name, arguments=kwargs)

                if hasattr(res, "content"):
                    parts = [c.text if hasattr(c, "text") else str(c) for c in res.content]
                    return "\n".join(parts)
                return str(res)
            raise ValueError(f"Target {conn_or_manager} does not implement call_tool.")

        self.register_tool(
            tool_name,
            _mcp_wrapper,
            is_async=True,
            sequential_only=sequential_only,
        )

    def unregister_tool(self, name: str) -> None:
        """Removes a registered tool by name."""
        if name in self.tools:
            del self.tools[name]
        self.sequential_tools.discard(name)

    def has_tool(self, name: str) -> bool:
        """Returns True if the tool name is registered."""
        return name in self.tools

    def is_sequential(self, name: str) -> bool:
        """Returns True if the tool is flagged as sequential_only."""
        return name in self.sequential_tools

    async def _execute_single_tool(
        self,
        tool_call: Dict[str, Any],
        timeout: float,
    ) -> ToolExecutionResult:
        """Executes a single tool call with timeout enforcement and error shielding."""
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
            res = await asyncio.wait_for(tool_fn(**inputs), timeout=timeout)
            duration = time.perf_counter() - start_time
            result_str = str(res) if res is not None else ""

            data_pointer = None
            is_offloaded = False
            is_truncated = False

            if self.output_guard is not None:
                guard_res = self.output_guard.process(
                    output=result_str,
                    tool_name=name,
                    tool_call_id=tool_id,
                )
                result_str = guard_res.content
                if guard_res.data_pointer is not None:
                    if hasattr(guard_res.data_pointer, "model_dump"):
                        data_pointer = guard_res.data_pointer.model_dump()
                    elif hasattr(guard_res.data_pointer, "dict"):
                        data_pointer = guard_res.data_pointer.dict()
                    elif isinstance(guard_res.data_pointer, dict):
                        data_pointer = guard_res.data_pointer
                is_offloaded = guard_res.is_offloaded
                is_truncated = guard_res.is_truncated

            return ToolExecutionResult(
                tool_call_id=tool_id,
                name=name,
                result=result_str,
                success=True,
                error=None,
                duration=round(duration, 4),
                data_pointer=data_pointer,
                is_offloaded=is_offloaded,
                is_truncated=is_truncated,
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
        parallel: Optional[bool] = None,
    ) -> List[ToolExecutionResult]:
        """
        Dispatches tool calls with configurable concurrency and order preservation:
        1. If parallel (or self.parallel_execution) is False: executes sequentially one-by-one.
        2. If parallel is True: executes concurrently, bounded by self.semaphore (max_concurrency).
        3. If any tool is marked sequential_only: isolates sequential tools to avoid race conditions.
        4. Guarantees 100% order preservation matching the input tool_calls sequence.
        """
        if not tool_calls:
            return []

        effective_timeout = timeout if timeout is not None else self.default_timeout
        is_parallel = parallel if parallel is not None else self.parallel_execution

        # Mode A: Pure sequential execution
        if not is_parallel or len(tool_calls) == 1:
            results: List[ToolExecutionResult] = []
            for tc in tool_calls:
                res = await self._execute_single_tool(tc, effective_timeout)
                results.append(res)
            return results

        # Mode B: Check for sequential_only tools in the batch
        has_sequential = any(tc.get("name") in self.sequential_tools for tc in tool_calls)
        if has_sequential:
            # When batch contains sequential_only mutating tools, fall back to sequential safety
            results = []
            for tc in tool_calls:
                res = await self._execute_single_tool(tc, effective_timeout)
                results.append(res)
            return results

        # Mode C: Throttled parallel execution bounded by semaphore
        async def _throttled_exec(tc: Dict[str, Any]) -> ToolExecutionResult:
            async with self.semaphore:
                return await self._execute_single_tool(tc, effective_timeout)

        tasks = [asyncio.create_task(_throttled_exec(tc)) for tc in tool_calls]
        results = await asyncio.gather(*tasks)
        return list(results)
