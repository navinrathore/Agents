import json
from pathlib import Path
import pytest
import sys

AGENTS_ROOT = str(Path(__file__).resolve().parent.parent)
if AGENTS_ROOT not in sys.path:
    sys.path.insert(0, AGENTS_ROOT)

from core.dispatcher import AsyncToolDispatcher
from core.openapi_loader import OpenAPIToolLoader


SAMPLE_PETSTORE_SPEC = """
openapi: "3.0.0"
info:
  title: "Petstore Demo"
  version: "1.0.0"
servers:
  - url: "https://api.petstore.test/v1"
paths:
  /pets:
    get:
      operationId: "list_pets"
      summary: "List all pets"
      tags: ["pets", "query"]
      parameters:
        - name: "limit"
          in: "query"
          required: false
          schema:
            type: "integer"
    post:
      operationId: "create_pet"
      summary: "Create a new pet"
      tags: ["pets", "mutation"]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: "object"
              required: ["name"]
              properties:
                name:
                  type: "string"
                  description: "Name of pet"
                category:
                  type: "string"
  /pets/{pet_id}:
    get:
      operationId: "get_pet_by_id"
      summary: "Get pet by ID"
      tags: ["pets"]
      parameters:
        - name: "pet_id"
          in: "path"
          required: true
          schema:
            type: "string"
    delete:
      operationId: "delete_pet"
      summary: "Delete pet"
      tags: ["pets", "mutation"]
      parameters:
        - name: "pet_id"
          in: "path"
          required: true
          schema:
            type: "string"
"""


def test_openapi_loader_direct_strategy():
    """Verify Strategy 1: Direct 1:1 mapping of endpoints to distinct tools."""
    loader = OpenAPIToolLoader.from_text(SAMPLE_PETSTORE_SPEC)
    assert len(loader.operations) == 4

    # 1. OpenAI Format
    openai_tools = loader.generate_tools(strategy="direct", tool_format="openai")
    assert len(openai_tools) == 4
    tool_names = [t["function"]["name"] for t in openai_tools]
    assert "list_pets" in tool_names
    assert "create_pet" in tool_names
    assert "get_pet_by_id" in tool_names
    assert "delete_pet" in tool_names

    # Verify parameter schemas
    get_pet_tool = next(t for t in openai_tools if t["function"]["name"] == "get_pet_by_id")
    params = get_pet_tool["function"]["parameters"]
    assert "pet_id" in params["properties"]
    assert "pet_id" in params["required"]

    create_tool = next(t for t in openai_tools if t["function"]["name"] == "create_pet")
    body_params = create_tool["function"]["parameters"]
    assert "name" in body_params["properties"]
    assert "name" in body_params["required"]

    # 2. Anthropic Format
    anthropic_tools = loader.generate_tools(strategy="direct", tool_format="anthropic")
    assert len(anthropic_tools) == 4
    assert anthropic_tools[0]["name"] == "list_pets"
    assert "input_schema" in anthropic_tools[0]


def test_openapi_loader_generic_runner_strategy():
    """Verify Strategy 2: Single compact meta-tool (call_api) to minimize prompt token cost."""
    loader = OpenAPIToolLoader.from_text(SAMPLE_PETSTORE_SPEC)
    generic_tools = loader.generate_tools(strategy="generic", tool_format="openai")

    assert len(generic_tools) == 1
    meta_tool = generic_tools[0]["function"]
    assert meta_tool["name"] == "call_api"
    assert "Available Routes:" in meta_tool["description"]
    assert "GET /pets" in meta_tool["description"]
    assert "POST /pets" in meta_tool["description"]
    assert "path" in meta_tool["parameters"]["required"]
    assert "method" in meta_tool["parameters"]["required"]


def test_openapi_loader_read_only_filtering():
    """Verify safety guardrail: read_only=True drops all mutating operations (POST, DELETE)."""
    loader = OpenAPIToolLoader.from_text(SAMPLE_PETSTORE_SPEC)
    read_only_tools = loader.generate_tools(strategy="direct", read_only=True)

    assert len(read_only_tools) == 2
    tool_names = [t["function"]["name"] for t in read_only_tools]
    assert "list_pets" in tool_names
    assert "get_pet_by_id" in tool_names
    assert "create_pet" not in tool_names
    assert "delete_pet" not in tool_names


def test_openapi_loader_tag_filtering():
    """Verify filtering endpoints by OpenAPI tags."""
    loader = OpenAPIToolLoader.from_text(SAMPLE_PETSTORE_SPEC)
    query_tools = loader.generate_tools(strategy="direct", tag_filter=["query"])

    assert len(query_tools) == 1
    assert query_tools[0]["function"]["name"] == "list_pets"


def test_openapi_prepare_request_path_interpolation():
    """Verify that path placeholders like {pet_id} are properly substituted."""
    loader = OpenAPIToolLoader.from_text(SAMPLE_PETSTORE_SPEC)

    req = loader.prepare_request(
        operation_id="get_pet_by_id",
        pet_id="pet_999",
        verbose_flag="true",
    )

    assert req["method"] == "GET"
    assert req["url"] == "https://api.petstore.test/v1/pets/pet_999"
    assert req["query_params"] == {"verbose_flag": "true"}


@pytest.mark.anyio
async def test_openapi_integration_with_async_tool_dispatcher():
    """
    Verify that generated OpenAPI tools register into AsyncToolDispatcher and execute dry runs.
    """
    loader = OpenAPIToolLoader.from_text(SAMPLE_PETSTORE_SPEC)
    dispatcher = AsyncToolDispatcher(parallel_execution=True)

    # Register direct tools into dispatcher
    registered_names = loader.register_into_dispatcher(
        dispatcher=dispatcher,
        strategy="direct",
        read_only=True,
        dry_run=True,
    )

    assert "get_pet_by_id" in registered_names
    assert "list_pets" in registered_names
    assert len(registered_names) == 2

    # Dispatch tool call through AsyncToolDispatcher
    tool_calls = [
        {"id": "tc_pet_1", "name": "get_pet_by_id", "input": {"pet_id": "pet_123"}},
        {"id": "tc_pet_list", "name": "list_pets", "input": {"limit": 10}},
    ]

    results = await dispatcher.dispatch(tool_calls)
    assert len(results) == 2
    assert results[0].success is True
    assert results[1].success is True

    # Parse dry run output
    payload_0 = json.loads(results[0].result)
    assert payload_0["status"] == "dry_run_success"
    assert payload_0["simulated_request"]["url"] == "https://api.petstore.test/v1/pets/pet_123"

    payload_1 = json.loads(results[1].result)
    assert payload_1["status"] == "dry_run_success"
    assert payload_1["simulated_request"]["query_params"]["limit"] == 10
