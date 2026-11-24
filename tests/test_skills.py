from pathlib import Path
import shutil
import sys
import tempfile
import pytest

AGENTS_ROOT = str(Path(__file__).resolve().parent.parent)
if AGENTS_ROOT not in sys.path:
    sys.path.insert(0, AGENTS_ROOT)

from core.skills import (
    SkillManager,
    SkillMetadata,
    SkillPackage,
    SkillRegistry,
    SkillRouter,
    generate_tool_schema,
    parse_skill_md,
)


@pytest.fixture
def temp_skills_dir():
    temp_dir = tempfile.mkdtemp(prefix="test_skills_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


# ==============================================================================
# 1. Frontmatter Parsing Tests
# ==============================================================================

def test_parse_skill_md_valid(temp_skills_dir):
    skill_file = temp_skills_dir / "SKILL.md"
    skill_file.write_text(
        "---\n"
        "name: test_skill\n"
        "description: A test skill for unit testing.\n"
        "version: 2.1.0\n"
        "triggers:\n"
        "  - unit test\n"
        "  - testing\n"
        "tags:\n"
        "  - dev\n"
        "requires_approval: true\n"
        "---\n"
        "\n"
        "# Standard Operating Procedure\n"
        "Step 1. Run unit test.\n",
        encoding="utf-8",
    )

    metadata, sop = parse_skill_md(skill_file)
    assert metadata.name == "test_skill"
    assert metadata.description == "A test skill for unit testing."
    assert metadata.version == "2.1.0"
    assert metadata.triggers == ["unit test", "testing"]
    assert metadata.tags == ["dev"]
    assert metadata.requires_approval is True
    assert "# Standard Operating Procedure" in sop
    assert "Step 1. Run unit test." in sop


def test_parse_skill_md_missing_boundaries(temp_skills_dir):
    skill_file = temp_skills_dir / "SKILL.md"
    skill_file.write_text("Just raw markdown without frontmatter", encoding="utf-8")

    with pytest.raises(ValueError, match="Missing '---' YAML frontmatter boundaries"):
        parse_skill_md(skill_file)


def test_parse_skill_md_missing_required_keys(temp_skills_dir):
    skill_file = temp_skills_dir / "SKILL.md"
    skill_file.write_text(
        "---\n"
        "version: 1.0.0\n"
        "---\n"
        "# Body\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Both 'name' and 'description' are required"):
        parse_skill_md(skill_file)


# ==============================================================================
# 2. Tool Schema Reflection Tests
# ==============================================================================

def test_generate_tool_schema():
    def sample_tool(query: str, limit: int = 10, verbose: bool = False) -> str:
        """
        Executes a sample search query.
        
        Args:
            query: The search term to query.
            limit: Maximum count of results.
            verbose: Enable debug log output.
        """
        return f"Results for {query}"

    schema = generate_tool_schema(sample_tool)

    assert schema["type"] == "function"
    fn = schema["function"]
    assert fn["name"] == "sample_tool"
    assert "sample search query" in fn["description"]
    assert fn["parameters"]["type"] == "object"

    props = fn["parameters"]["properties"]
    assert props["query"]["type"] == "string"
    assert "search term" in props["query"]["description"]

    assert props["limit"]["type"] == "integer"
    assert props["limit"]["default"] == 10

    assert props["verbose"]["type"] == "boolean"
    assert props["verbose"]["default"] is False

    assert fn["parameters"]["required"] == ["query"]


# ==============================================================================
# 3. SkillRegistry Discovery Tests
# ==============================================================================

def test_registry_discovery_on_reference_skill():
    # Use workspace projects/Agents/skills
    skills_root = Path(AGENTS_ROOT) / "skills"
    registry = SkillRegistry(search_paths=[skills_root])

    skills = registry.discover_skills()
    assert "data_analyst" in skills

    pkg = registry.get_skill("data_analyst")
    assert pkg is not None
    assert pkg.name == "data_analyst"
    assert "bounded analytical queries" in pkg.description
    assert "describe_table" in pkg.tool_names
    assert "query_table" in pkg.tool_names

    # Check schemas generated
    schema_names = {s["function"]["name"] for s in pkg.tool_schemas}
    assert schema_names == {"describe_table", "query_table"}

    # Test direct callable execution
    describe_fn = pkg.tool_callables["describe_table"]
    res = describe_fn("users")
    assert "Table: users" in res


def test_registry_catalog_summary(temp_skills_dir):
    # Create two temporary skills
    pkg_a = temp_skills_dir / "skill_alpha"
    pkg_a.mkdir()
    (pkg_a / "SKILL.md").write_text(
        "---\nname: alpha\ndescription: Alpha skill capability.\ntriggers: [run alpha]\n---\n# SOP\n",
        encoding="utf-8",
    )

    pkg_b = temp_skills_dir / "skill_beta"
    pkg_b.mkdir()
    (pkg_b / "SKILL.md").write_text(
        "---\nname: beta\ndescription: Beta skill capability.\n---\n# SOP\n",
        encoding="utf-8",
    )

    registry = SkillRegistry(search_paths=[temp_skills_dir])
    summary = registry.get_catalog_summary()

    assert "Available skills (activate on demand):" in summary
    assert "- alpha: Alpha skill capability. [triggers: run alpha]" in summary
    assert "- beta: Beta skill capability." in summary


# ==============================================================================
# 4. Cascading Hybrid Router Tests (Tier 1 & Tier 2)
# ==============================================================================

def test_skill_router_tier1_keyword_match():
    skills_root = Path(AGENTS_ROOT) / "skills"
    registry = SkillRegistry(search_paths=[skills_root])
    router = SkillRouter(registry=registry)

    # 1. Matches trigger keyword 'sql'
    matches = router.route("Can you run some sql queries on the users table?")
    assert matches == ["data_analyst"]

    # 2. Matches tag 'analytics'
    matches_tag = router.route("I need advanced analytics on recent orders")
    assert matches_tag == ["data_analyst"]

    # 3. Unrelated query returns empty
    matches_none = router.route("Write a haiku about rain")
    assert matches_none == []


def test_skill_router_tier2_fallback():
    skills_root = Path(AGENTS_ROOT) / "skills"
    registry = SkillRegistry(search_paths=[skills_root])

    # Mock LLM classifier for Tier 2 fallback
    def mock_llm_classifier(query: str, available_skills: list) -> list:
        if "client records" in query.lower():
            return ["data_analyst"]
        return []

    router = SkillRouter(registry=registry, llm_classifier=mock_llm_classifier)

    # Obscure phrasing that doesn't trigger Tier 1 keywords
    ambiguous_query = "Please examine our active client records"
    assert router.route_tier1(ambiguous_query) == []

    # Cascades to Tier 2
    routed = router.route(ambiguous_query)
    assert routed == ["data_analyst"]


# ==============================================================================
# 5. SkillManager Lifecycle & Dynamic Tool Mounting Tests
# ==============================================================================

@pytest.mark.anyio
async def test_skill_manager_dynamic_mounting_and_execution():
    from core.dispatcher import AsyncToolDispatcher

    skills_root = Path(AGENTS_ROOT) / "skills"
    registry = SkillRegistry(search_paths=[skills_root])
    manager = SkillManager(registry=registry)
    dispatcher = AsyncToolDispatcher()

    # Initial state: dispatcher has 0 tools
    assert not dispatcher.has_tool("describe_table")
    assert not dispatcher.has_tool("query_table")

    # 1. Route and dynamically mount tools
    matched = manager.route_and_activate("Please run a sql analysis on users", dispatcher=dispatcher)
    assert matched == ["data_analyst"]
    assert manager.is_active("data_analyst")

    # Dispatcher now has tools mounted!
    assert dispatcher.has_tool("describe_table")
    assert dispatcher.has_tool("query_table")

    # Execute mounted tool through dispatcher
    results = await dispatcher.dispatch([
        {"id": "call_1", "name": "describe_table", "input": {"table_name": "users"}}
    ])
    assert len(results) == 1
    assert results[0].success is True
    assert "Table: users" in results[0].result

    # 2. Check dynamic SOP prompt injection
    base_prompt = "You are an autonomous assistant."
    augmented_prompt = manager.build_system_prompt(base_prompt)
    assert "ACTIVE SPECIALIZED SKILL GUIDELINES" in augmented_prompt
    assert "SQL Data Analyst SOP" in augmented_prompt

    # 3. Unmount skill cleanly
    deactivated = manager.deactivate_skills(["data_analyst"], dispatcher=dispatcher)
    assert deactivated == ["data_analyst"]
    assert not manager.is_active("data_analyst")

    # Tools are unmounted from dispatcher
    assert not dispatcher.has_tool("describe_table")
    assert not dispatcher.has_tool("query_table")

    # Prompt reverts back to pristine base prompt
    clean_prompt = manager.build_system_prompt(base_prompt)
    assert clean_prompt == base_prompt


@pytest.mark.anyio
async def test_database_agent_skill_discovery_and_execution():
    from core.dispatcher import AsyncToolDispatcher
    from core.db import DatabaseEngine
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import StaticPool

    # Set up in-memory DB with StaticPool so worker threads share the exact same in-memory DB
    db = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    with db.begin() as conn:
        conn.execute(text("CREATE TABLE customers (id INT PRIMARY KEY, name TEXT, balance REAL)"))
        conn.execute(text("INSERT INTO customers VALUES (1, 'Alice Corp', 5000.0), (2, 'Bob Ltd', 1200.0)"))

    engine = DatabaseEngine(db)

    # Configure skill
    skills_dir = Path(__file__).resolve().parent.parent / "skills"
    registry = SkillRegistry(search_paths=[skills_dir])
    discovered = registry.discover_skills()
    assert "database_agent" in discovered

    # Inject active engine into the skill's loaded callables
    skill_pkg = discovered["database_agent"]
    list_tables_fn = skill_pkg.tool_callables["list_tables"]
    list_tables_fn.__globals__["set_database_engine"](engine)

    manager = SkillManager(registry=registry)
    dispatcher = AsyncToolDispatcher()
    activated = manager.activate_skills(["database_agent"], dispatcher=dispatcher)
    assert "database_agent" in activated

    # 1. Test tool discovery on dispatcher
    assert dispatcher.has_tool("list_tables")
    assert dispatcher.has_tool("get_table_schema")
    assert dispatcher.has_tool("execute_sql")

    # 2. Execute list_tables via dispatcher
    res_tables = await dispatcher.dispatch([{"id": "c1", "name": "list_tables", "input": {}}])
    assert res_tables[0].success is True
    assert "customers" in str(res_tables[0].result)

    # 3. Execute safe query via dispatcher
    res_query = await dispatcher.dispatch([
        {"id": "c2", "name": "execute_sql", "input": {"sql": "SELECT name, balance FROM customers WHERE balance > 2000"}}
    ])
    assert res_query[0].success is True
    assert "Alice Corp" in str(res_query[0].result)

    # 4. Verify AST sanitization blocks DDL via skill
    res_drop = await dispatcher.dispatch([
        {"id": "c3", "name": "execute_sql", "input": {"sql": "DROP TABLE customers"}}
    ])
    assert res_drop[0].success is True
    assert "'success': False" in str(res_drop[0].result)
    assert "Only SELECT or WITH queries are permitted" in str(res_drop[0].result)

    # 5. Verify SOP prompt injection
    base = "Base system prompt."
    sop_prompt = manager.build_system_prompt(base)
    assert "Database Agent SOP" in sop_prompt
    assert "Schema Discovery First" in sop_prompt


