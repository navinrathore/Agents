from pathlib import Path
import shutil
import sys
import tempfile
import pytest

AGENTS_ROOT = str(Path(__file__).resolve().parent.parent)
if AGENTS_ROOT not in sys.path:
    sys.path.insert(0, AGENTS_ROOT)

from core.skills import (
    SkillMetadata,
    SkillPackage,
    SkillRegistry,
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
