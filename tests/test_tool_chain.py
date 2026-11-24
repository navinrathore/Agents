import asyncio
import json
from pathlib import Path
import sys
import pytest

AGENTS_ROOT = str(Path(__file__).resolve().parent.parent)
if AGENTS_ROOT not in sys.path:
    sys.path.insert(0, AGENTS_ROOT)

from core.chain import (
    OnErrorStrategy,
    PipelineExecutionResult,
    PipelineSpec,
    PipelineStep,
    StepStatus,
    ToolPipelineEngine,
    interpolate_templates,
    resolve_path_in_data,
    unroll_nested_dict_calls,
)
from core.dispatcher import AsyncToolDispatcher


def test_template_interpolation():
    completed = {
        "step_1": type("MockRes", (), {"output": {"user": {"id": 42, "name": "Alice"}}})(),
        "step_2": type("MockRes", (), {"output": "summary_text"})(),
        "step_3": type("MockRes", (), {"output": [10, 20, 30]})(),
    }

    # Direct native extraction
    val = interpolate_templates("{{steps.step_1.output.user.id}}", completed)
    assert val == 42

    val_sub = interpolate_templates("{{steps.step_3.output.1}}", completed)
    assert val_sub == 20

    # String embedded interpolation
    text = interpolate_templates("Hello {{steps.step_1.output.user.name}}, info: {{steps.step_2.output}}", completed)
    assert text == "Hello Alice, info: summary_text"

    # Nested dict interpolation
    d = interpolate_templates({"target_id": "{{steps.step_1.output.user.id}}", "static": True}, completed)
    assert d == {"target_id": 42, "static": True}


def test_kahn_cycle_detection():
    # A -> B -> C -> A
    steps = [
        PipelineStep(id="A", tool="t1", depends_on=["C"]),
        PipelineStep(id="B", tool="t1", depends_on=["A"]),
        PipelineStep(id="C", tool="t1", depends_on=["B"]),
    ]
    with pytest.raises(ValueError, match="Cyclic dependency detected"):
        ToolPipelineEngine.build_dag_execution_waves(steps)

    # Self dependency
    with pytest.raises(ValueError, match="cannot depend on itself"):
        ToolPipelineEngine.build_dag_execution_waves([
            PipelineStep(id="A", tool="t1", depends_on=["A"])
        ])

    # Undefined dependency
    with pytest.raises(ValueError, match="references undefined dependency"):
        ToolPipelineEngine.build_dag_execution_waves([
            PipelineStep(id="A", tool="t1", depends_on=["NON_EXISTENT"])
        ])


def test_dag_waves_topological():
    # Diamond DAG:
    #      start
    #     /     \
    # branch_a  branch_b
    #     \     /
    #      join
    steps = [
        PipelineStep(id="start", tool="t1"),
        PipelineStep(id="branch_a", tool="t2", depends_on=["start"]),
        PipelineStep(id="branch_b", tool="t3", depends_on=["start"]),
        PipelineStep(id="join", tool="t4", depends_on=["branch_a", "branch_b"]),
    ]

    waves = ToolPipelineEngine.build_dag_execution_waves(steps)
    assert len(waves) == 3
    assert [s.id for s in waves[0]] == ["start"]
    assert sorted([s.id for s in waves[1]]) == ["branch_a", "branch_b"]
    assert [s.id for s in waves[2]] == ["join"]


@pytest.mark.anyio
async def test_linear_pipeline_execution():
    dispatcher = AsyncToolDispatcher()

    dispatcher.register_tool("get_user", lambda uid: {"id": uid, "email": "alice@example.com"})
    dispatcher.register_tool("fetch_orders", lambda email: [{"order_id": 101, "total": 55.0}])
    dispatcher.register_tool("calculate_total", lambda orders: f"Total: {sum(o['total'] for o in orders)}")

    pipeline_input = {
        "steps": [
            {"id": "step_user", "tool": "get_user", "input": {"uid": 123}},
            {"id": "step_orders", "tool": "fetch_orders", "depends_on": ["step_user"], "input": {"email": "{{steps.step_user.output.email}}"}},
            {"id": "step_total", "tool": "calculate_total", "depends_on": ["step_orders"], "input": {"orders": "{{steps.step_orders.output}}"}},
        ],
        "on_error": "halt",
    }

    # Execute via dispatcher meta-tool
    call = [{"id": "pipe_1", "name": "execute_tool_pipeline", "input": pipeline_input}]
    res = await dispatcher.dispatch(call)

    assert len(res) == 1
    assert res[0].success is True
    summary = json.loads(res[0].result)
    assert summary["success"] is True
    assert summary["final_output"] == "Total: 55.0"
    assert summary["steps"]["step_user"]["status"] == "completed"
    assert summary["steps"]["step_orders"]["status"] == "completed"
    assert summary["steps"]["step_total"]["status"] == "completed"


@pytest.mark.anyio
async def test_error_handling_halt_vs_skip():
    dispatcher = AsyncToolDispatcher()

    dispatcher.register_tool("step_ok", lambda: "ok")
    def _fail():
        raise RuntimeError("Failure in tool")
    dispatcher.register_tool("step_bad", _fail)
    dispatcher.register_tool("step_child", lambda val: f"child_{val}")
    dispatcher.register_tool("step_sibling", lambda: "sibling_ok")

    # Mode 1: HALT - should abort sibling & child
    pipe_halt = {
        "steps": [
            {"id": "bad", "tool": "step_bad", "input": {}},
            {"id": "child", "tool": "step_child", "depends_on": ["bad"], "input": {"val": "{{steps.bad.output}}"}},
            {"id": "sibling", "tool": "step_sibling", "depends_on": [], "input": {}},
        ],
        "on_error": "halt",
    }

    res_halt = await dispatcher.dispatch([{"id": "p_halt", "name": "execute_tool_pipeline", "input": pipe_halt}])
    summary_halt = json.loads(res_halt[0].result)
    assert summary_halt["success"] is False
    assert summary_halt["steps"]["bad"]["status"] == "failed"
    assert summary_halt["steps"]["child"]["status"] == "skipped"

    # Mode 2: SKIP_DEPENDENTS - child is skipped, but independent sibling completes!
    pipe_skip = {
        "steps": [
            {"id": "bad", "tool": "step_bad", "input": {}},
            {"id": "child", "tool": "step_child", "depends_on": ["bad"], "input": {"val": "{{steps.bad.output}}"}},
            {"id": "sibling", "tool": "step_sibling", "depends_on": [], "input": {}},
        ],
        "on_error": "skip_dependents",
    }
    res_skip = await dispatcher.dispatch([{"id": "p_skip", "name": "execute_tool_pipeline", "input": pipe_skip}])
    summary_skip = json.loads(res_skip[0].result)
    assert summary_skip["success"] is False
    assert summary_skip["steps"]["bad"]["status"] == "failed"
    assert summary_skip["steps"]["child"]["status"] == "skipped"
    assert summary_skip["steps"]["sibling"]["status"] == "completed"


@pytest.mark.anyio
async def test_nested_tool_dict_unrolling():
    """
    Verify that nested {"$tool": ..., "$input": ...} dictionary inputs
    are automatically unrolled and executed sequentially into the parent tool.
    """
    dispatcher = AsyncToolDispatcher()

    dispatcher.register_tool("fetch_price", lambda item: 25.0)
    dispatcher.register_tool("apply_discount", lambda price, discount: price * (1.0 - discount))

    # Calling apply_discount where price is generated from fetch_price
    nested_call = [{
        "id": "c1",
        "name": "apply_discount",
        "input": {
            "price": {"$tool": "fetch_price", "$input": {"item": "shoes"}},
            "discount": 0.20,
        }
    }]

    results = await dispatcher.dispatch(nested_call)
    assert len(results) == 1
    assert results[0].success is True
    # 25.0 * 0.8 = 20.0
    assert float(results[0].result) == 20.0


@pytest.mark.anyio
async def test_configurable_pipeline_runner_from_yaml(tmp_path):
    """
    Verify that ConfigurablePipelineRunner can load and execute a pipeline
    from a YAML file, resolving tools dynamically and interpolating variables.
    """
    from core.chain import ConfigurablePipelineRunner

    yaml_content = """
pipeline:
  on_error: halt
  steps:
    - id: fetch_weather
      tool: get_weather
      input:
        city: "Zurich"
    - id: recommend_activity
      tool: make_recommendation
      depends_on: ["fetch_weather"]
      input:
        temp: "{{steps.fetch_weather.output.temp}}"
        condition: "{{steps.fetch_weather.output.condition}}"
"""
    config_file = tmp_path / "pipeline.yaml"
    config_file.write_text(yaml_content, encoding="utf-8")

    runner = ConfigurablePipelineRunner()
    runner.register_tool("get_weather", lambda city: {"temp": 22, "condition": "sunny", "city": city})
    runner.register_tool("make_recommendation", lambda temp, condition: f"Enjoy the {condition} weather at {temp}°C!")

    result = await runner.run(str(config_file))

    assert result.success is True
    assert result.final_output == "Enjoy the sunny weather at 22°C!"
    assert result.step_results["fetch_weather"].status == StepStatus.COMPLETED
    assert result.step_results["recommend_activity"].status == StepStatus.COMPLETED

