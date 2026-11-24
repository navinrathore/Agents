import asyncio
from enum import Enum
import importlib
import json
import logging
import os
import re
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Union
import yaml
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)


class OnErrorStrategy(str, Enum):
    HALT = "halt"                     # Stop entire pipeline immediately if any step fails
    SKIP_DEPENDENTS = "skip_dependents"  # Skip downstream dependents, but execute independent branches
    CONTINUE = "continue"             # Continue downstream passing raw error/None


class PipelineStep(BaseModel):
    id: str = Field(..., description="Unique step identifier within the pipeline")
    tool: str = Field(..., description="Name of the registered tool to execute")
    input: Dict[str, Any] = Field(default_factory=dict, description="Input arguments for the tool")
    depends_on: List[str] = Field(default_factory=list, description="IDs of steps that must succeed before this step runs")
    timeout: Optional[float] = Field(default=None, description="Optional per-step timeout override")

    @model_validator(mode="after")
    def validate_id_format(self) -> "PipelineStep":
        if not re.match(r"^[a-zA-Z0-9_\-]+$", self.id):
            raise ValueError(f"Step id '{self.id}' must be alphanumeric or contain hyphens/underscores.")
        return self


class PipelineSpec(BaseModel):
    steps: List[PipelineStep] = Field(..., description="Ordered or unordered list of pipeline steps")
    on_error: OnErrorStrategy = Field(default=OnErrorStrategy.HALT, description="Error handling strategy")
    timeout: Optional[float] = Field(default=None, description="Total pipeline timeout override")

    @model_validator(mode="after")
    def validate_step_ids_unique(self) -> "PipelineSpec":
        ids = [s.id for s in self.steps]
        if len(ids) != len(set(ids)):
            seen = set()
            duplicates = {x for x in ids if x in seen or seen.add(x)}
            raise ValueError(f"Duplicate step ids found in pipeline: {duplicates}")
        return self


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineStepResult(BaseModel):
    step_id: str
    tool: str
    status: StepStatus
    output: Any = None
    raw_result: Any = None
    error: Optional[str] = None
    duration: float = 0.0


class PipelineExecutionResult(BaseModel):
    success: bool
    step_results: Dict[str, PipelineStepResult] = Field(default_factory=dict)
    final_output: Any = None
    error: Optional[str] = None
    total_duration: float = 0.0

    def to_summary_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "error": self.error,
            "total_duration": self.total_duration,
            "final_output": self.final_output,
            "steps": {
                k: {
                    "tool": v.tool,
                    "status": v.status.value,
                    "error": v.error,
                    "output": str(v.output)[:500] if v.output is not None else None,
                    "duration": v.duration,
                }
                for k, v in self.step_results.items()
            },
        }


# Pattern matching expressions like {{steps.step_id.output}} or {{steps.step_id.output.key.sub}}
TEMPLATE_PATTERN = re.compile(r"\{\{\s*steps\.([a-zA-Z0-9_\-]+)\.output(?:\.([a-zA-Z0-9_\-\.]+))?\s*\}\}")
NESTED_TOOL_KEY = "$tool"
NESTED_INPUT_KEY = "$input"


def resolve_path_in_data(data: Any, path: Optional[str]) -> Any:
    """Traverses nested dicts, lists, or JSON strings using dot notation."""
    if path is None or path == "":
        return data

    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            # Not JSON parseable, cannot navigate deeper
            return data

    current = data
    parts = path.split(".")
    for part in parts:
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                return None
        elif isinstance(current, (list, tuple)):
            try:
                idx = int(part)
                current = current[idx]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def interpolate_templates(
    template_val: Any,
    completed_steps: Dict[str, PipelineStepResult],
) -> Any:
    """
    Recursively interpolates `{{steps.<step_id>.output.<path>}}` tokens
    within input arguments using the outputs of previously completed steps.
    """
    if isinstance(template_val, str):
        # Exact full match case: preserves native types (e.g. dicts, lists, ints)
        exact_match = re.fullmatch(r"\{\{\s*steps\.([a-zA-Z0-9_\-]+)\.output(?:\.([a-zA-Z0-9_\-\.]+))?\s*\}\}", template_val.strip())
        if exact_match:
            step_id, path = exact_match.group(1), exact_match.group(2)
            if step_id in completed_steps:
                val = completed_steps[step_id].output
                return resolve_path_in_data(val, path)
            return None

        # String substring interpolation case
        def _repl(match: re.Match) -> str:
            step_id = match.group(1)
            path = match.group(2)
            if step_id not in completed_steps:
                return f"[UNRESOLVED: {step_id}]"
            val = completed_steps[step_id].output
            extracted = resolve_path_in_data(val, path)
            if isinstance(extracted, (dict, list)):
                return json.dumps(extracted)
            return str(extracted) if extracted is not None else ""

        return TEMPLATE_PATTERN.sub(_repl, template_val)

    elif isinstance(template_val, dict):
        return {k: interpolate_templates(v, completed_steps) for k, v in template_val.items()}
    elif isinstance(template_val, list):
        return [interpolate_templates(item, completed_steps) for item in template_val]
    return template_val


class ToolPipelineEngine:
    """
    Dependency-aware DAG execution engine for chained & nested tool calling.
    - Validates DAG topology (rejects cycles via Kahn's algorithm).
    - Executes steps in parallel waves where dependencies are fulfilled.
    - Interpolates intermediate step outputs safely into downstream arguments.
    - Supports configurable failure modes (HALT, SKIP_DEPENDENTS, CONTINUE).
    """

    def __init__(
        self,
        executor_fn: Callable[[str, Dict[str, Any], Optional[float]], Coroutine[Any, Any, Any]],
        default_timeout: float = 30.0,
        max_concurrency: int = 5,
    ):
        """
        :param executor_fn: Async callable taking (tool_name, inputs_dict, timeout) -> result_obj
        """
        self.executor_fn = executor_fn
        self.default_timeout = default_timeout
        self.max_concurrency = max(1, max_concurrency)

    @staticmethod
    def build_dag_execution_waves(steps: List[PipelineStep]) -> List[List[PipelineStep]]:
        """
        Topological sorting using Kahn's algorithm, grouping independent steps
        into concurrent execution 'waves'. Raises ValueError if a cycle or missing dependency exists.
        """
        step_map = {s.id: s for s in steps}
        all_ids = set(step_map.keys())

        # Validate that all depends_on references exist
        for s in steps:
            for dep in s.depends_on:
                if dep not in all_ids:
                    raise ValueError(f"Step '{s.id}' references undefined dependency '{dep}'.")
                if dep == s.id:
                    raise ValueError(f"Step '{s.id}' cannot depend on itself.")

        # In-degree computation
        in_degree = {s.id: len(s.depends_on) for s in steps}
        # Adjacency list: step_id -> list of steps that depend on it
        adj: Dict[str, List[str]] = {s.id: [] for s in steps}
        for s in steps:
            for dep in s.depends_on:
                adj[dep].append(s.id)

        waves: List[List[PipelineStep]] = []
        # Find all nodes with in_degree == 0
        current_wave_ids = [sid for sid, deg in in_degree.items() if deg == 0]
        processed_count = 0

        while current_wave_ids:
            waves.append([step_map[sid] for sid in sorted(current_wave_ids)])
            processed_count += len(current_wave_ids)
            next_wave_ids: List[str] = []

            for sid in current_wave_ids:
                for child in adj[sid]:
                    in_degree[child] -= 1
                    if in_degree[child] == 0:
                        next_wave_ids.append(child)

            current_wave_ids = next_wave_ids

        if processed_count < len(steps):
            cycle_nodes = [sid for sid, deg in in_degree.items() if deg > 0]
            raise ValueError(f"Cyclic dependency detected involving steps: {cycle_nodes}")

        return waves

    async def execute_pipeline(self, spec: PipelineSpec) -> PipelineExecutionResult:
        """Executes a pipeline DAG according to the specification."""
        start_time = time.perf_counter()
        step_results: Dict[str, PipelineStepResult] = {}
        sem = asyncio.Semaphore(self.max_concurrency)

        try:
            waves = self.build_dag_execution_waves(spec.steps)
        except Exception as e:
            return PipelineExecutionResult(
                success=False,
                error=f"DAG Validation Error: {str(e)}",
                total_duration=round(time.perf_counter() - start_time, 4),
            )

        failed_step_ids: Set[str] = set()
        pipeline_aborted = False

        for wave_idx, wave in enumerate(waves):
            if pipeline_aborted:
                for step in wave:
                    step_results[step.id] = PipelineStepResult(
                        step_id=step.id,
                        tool=step.tool,
                        status=StepStatus.SKIPPED,
                        error="Pipeline aborted due to upstream failure.",
                    )
                continue

            async def _run_step(step: PipelineStep) -> PipelineStepResult:
                # Check if any dependency failed or was skipped
                active_failed_deps = [d for d in step.depends_on if d in failed_step_ids]
                if active_failed_deps:
                    return PipelineStepResult(
                        step_id=step.id,
                        tool=step.tool,
                        status=StepStatus.SKIPPED,
                        error=f"Skipped because upstream dependencies failed: {active_failed_deps}",
                    )

                # Resolve parameter templates
                try:
                    resolved_inputs = interpolate_templates(step.input, step_results)
                except Exception as ex:
                    return PipelineStepResult(
                        step_id=step.id,
                        tool=step.tool,
                        status=StepStatus.FAILED,
                        error=f"Failed to interpolate step arguments: {str(ex)}",
                    )

                step_timeout = step.timeout or self.default_timeout
                step_start = time.perf_counter()

                async with sem:
                    try:
                        res = await self.executor_fn(step.tool, resolved_inputs, step_timeout)
                        duration = round(time.perf_counter() - step_start, 4)

                        # Standardize result extraction
                        if hasattr(res, "success") and not res.success:
                            err_msg = getattr(res, "error", None) or getattr(res, "result", "Tool execution failed")
                            return PipelineStepResult(
                                step_id=step.id,
                                tool=step.tool,
                                status=StepStatus.FAILED,
                                output=getattr(res, "result", None),
                                raw_result=res,
                                error=str(err_msg),
                                duration=duration,
                            )

                        output_val = getattr(res, "raw_output", getattr(res, "result", res))
                        return PipelineStepResult(
                            step_id=step.id,
                            tool=step.tool,
                            status=StepStatus.COMPLETED,
                            output=output_val,
                            raw_result=res,
                            duration=duration,
                        )
                    except asyncio.TimeoutError:
                        duration = round(time.perf_counter() - step_start, 4)
                        return PipelineStepResult(
                            step_id=step.id,
                            tool=step.tool,
                            status=StepStatus.FAILED,
                            error=f"Step timed out after {step_timeout}s.",
                            duration=duration,
                        )
                    except Exception as exc:
                        duration = round(time.perf_counter() - step_start, 4)
                        return PipelineStepResult(
                            step_id=step.id,
                            tool=step.tool,
                            status=StepStatus.FAILED,
                            error=f"{type(exc).__name__}: {str(exc)}",
                            duration=duration,
                        )

            wave_tasks = [asyncio.create_task(_run_step(s)) for s in wave]
            wave_results = await asyncio.gather(*wave_tasks)

            for step_res in wave_results:
                step_results[step_res.step_id] = step_res
                if step_res.status in (StepStatus.FAILED, StepStatus.SKIPPED):
                    failed_step_ids.add(step_res.step_id)
                    if spec.on_error == OnErrorStrategy.HALT:
                        pipeline_aborted = True

        total_dur = round(time.perf_counter() - start_time, 4)
        overall_success = len(failed_step_ids) == 0

        # Determine final output: last step of last wave or explicitly configured
        final_output = None
        if waves and waves[-1]:
            last_step_id = waves[-1][-1].id
            if last_step_id in step_results:
                final_output = step_results[last_step_id].output

        error_summary = None
        if not overall_success:
            failed_msgs = [f"[{r.step_id}]: {r.error}" for r in step_results.values() if r.error]
            error_summary = "Pipeline completed with failures: " + "; ".join(failed_msgs)

        return PipelineExecutionResult(
            success=overall_success,
            step_results=step_results,
            final_output=final_output,
            error=error_summary,
            total_duration=total_dur,
        )


def unroll_nested_dict_calls(input_data: Any) -> Any:
    """
    Recursively scans input data for nested functional expressions of the format:
    {"$tool": "tool_name", "$input": {...}}
    and converts them into a synthesizable PipelineSpec if detected.
    """
    # Helper to check if a dict matches the nested tool signature
    def _is_nested_tool(d: Any) -> bool:
        return isinstance(d, dict) and NESTED_TOOL_KEY in d

    if not isinstance(input_data, dict):
        return input_data

    # Detect if any parameter contains a nested tool invocation
    has_nested = any(_is_nested_tool(v) for v in input_data.values())
    if not has_nested:
        return input_data

    # Generate sequential pipeline steps
    steps: List[PipelineStep] = []
    resolved_parent_input: Dict[str, Any] = {}
    step_counter = 1

    for key, val in input_data.items():
        if _is_nested_tool(val):
            sub_tool = val[NESTED_TOOL_KEY]
            sub_input = val.get(NESTED_INPUT_KEY, {})
            step_id = f"nested_step_{step_counter}_{sub_tool}"
            step_counter += 1

            steps.append(PipelineStep(
                id=step_id,
                tool=sub_tool,
                input=sub_input,
                depends_on=[],
            ))
            resolved_parent_input[key] = f"{{{{steps.{step_id}.output}}}}"
        else:
            resolved_parent_input[key] = val

    return {
        "pipeline_steps": steps,
        "resolved_input": resolved_parent_input,
    }


def expand_env_vars_safe(text: str) -> str:
    """
    Expands environment variables of format ${VAR} or ${VAR:-default}
    safely according to workspace rules.
    """
    pattern = re.compile(r"\$\{([A-Za-z0-9_]+)(?::-([^}]*))?\}")

    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        default_val = match.group(2) if match.group(2) is not None else ""
        return os.environ.get(var_name, default_val)

    return pattern.sub(_replace, text)


class ConfigurablePipelineRunner:
    """
    Universal, standalone pipeline runner usable by any project via YAML/JSON configuration.
    
    Can load pipelines from declarative spec files, bind tools dynamically from:
    1. Python callable instances or functions passed in code.
    2. Dynamic import strings in config ('module.path:function_name').
    3. An existing AsyncToolDispatcher instance.
    """

    def __init__(
        self,
        tools: Optional[Dict[str, Callable[..., Any]]] = None,
        dispatcher: Optional[Any] = None,
        default_timeout: float = 30.0,
        max_concurrency: int = 5,
    ):
        from core.dispatcher import to_async_tool, is_coroutine_callable

        self.tools: Dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {}
        self.default_timeout = default_timeout
        self.max_concurrency = max_concurrency
        self.dispatcher = dispatcher

        # Register direct tools
        if tools:
            for name, fn in tools.items():
                if is_coroutine_callable(fn):
                    self.tools[name] = fn
                else:
                    self.tools[name] = to_async_tool(fn)

    @classmethod
    def load_spec_from_file(cls, file_path: str) -> PipelineSpec:
        """Loads and parses a PipelineSpec from a YAML or JSON file with safe env expansion."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Pipeline config file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        expanded_text = expand_env_vars_safe(raw_text)
        data = yaml.safe_load(expanded_text)
        if not isinstance(data, dict):
            raise ValueError(f"Config file must contain a dictionary/mapping: {file_path}")

        # Support root level {pipeline: {...}} or flat {...}
        spec_dict = data.get("pipeline", data)
        return PipelineSpec(**spec_dict)

    def register_tool(self, name: str, fn: Callable[..., Any]) -> None:
        """Register a tool callable."""
        from core.dispatcher import to_async_tool, is_coroutine_callable
        if is_coroutine_callable(fn):
            self.tools[name] = fn
        else:
            self.tools[name] = to_async_tool(fn)

    def import_and_register_tool(self, name: str, import_path: str) -> None:
        """
        Dynamically imports a tool from a Python path string, e.g. 'my_pkg.module:my_function'.
        """
        if ":" not in import_path:
            raise ValueError(f"Import path must be in format 'module.submodule:callable_name', got '{import_path}'")
        mod_name, func_name = import_path.split(":", 1)
        mod = importlib.import_module(mod_name)
        fn = getattr(mod, func_name)
        self.register_tool(name, fn)

    async def run(
        self,
        config_path_or_spec: Union[str, PipelineSpec, Dict[str, Any]],
        initial_params: Optional[Dict[str, Any]] = None,
    ) -> PipelineExecutionResult:
        """
        Executes a pipeline defined by a file path (YAML/JSON), dict, or PipelineSpec.
        Optional initial_params will be interpolated into the pipeline definition.
        """
        if isinstance(config_path_or_spec, str):
            spec = self.load_spec_from_file(config_path_or_spec)
        elif isinstance(config_path_or_spec, dict):
            spec_dict = config_path_or_spec.get("pipeline", config_path_or_spec)
            spec = PipelineSpec(**spec_dict)
        elif isinstance(config_path_or_spec, PipelineSpec):
            spec = config_path_or_spec
        else:
            raise TypeError(f"Invalid spec type: {type(config_path_or_spec)}")

        # If initial_params provided, inject them as a synthetic pseudo-step 'params'
        step_dict = {s.id: s for s in spec.steps}
        if initial_params:
            for s in spec.steps:
                # Replace {{params.xyz}} references if any
                s.input = interpolate_templates(s.input, {
                    "params": type("ParamRes", (), {"output": initial_params})()
                })

        async def _executor(tool_name: str, inputs: Dict[str, Any], step_timeout: Optional[float]) -> Any:
            effective_timeout = step_timeout or self.default_timeout

            # Priority 1: Check tools registered on this runner
            if tool_name in self.tools:
                fn = self.tools[tool_name]
                return await asyncio.wait_for(fn(**inputs), timeout=effective_timeout)

            # Priority 2: Check attached dispatcher
            if self.dispatcher is not None:
                call_id = f"step_{int(time.perf_counter()*1000)}"
                tc = {"id": call_id, "name": tool_name, "input": inputs}
                res = await self.dispatcher._execute_single_tool(tc, timeout=effective_timeout)
                if not res.success:
                    raise RuntimeError(res.error or f"Tool '{tool_name}' failed")
                return res.raw_output if res.raw_output is not None else res.result

            raise ValueError(f"Tool '{tool_name}' is not registered on runner or attached dispatcher.")

        engine = ToolPipelineEngine(
            executor_fn=_executor,
            default_timeout=self.default_timeout,
            max_concurrency=self.max_concurrency,
        )
        return await engine.execute_pipeline(spec)
