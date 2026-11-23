"""
Dynamic Skill / Tool Package Registry & Progressive Disclosure Subsystem.

Provides modular, declarative skill package discovery, automatic tool schema reflection,
and lightweight context catalog management. Enables agents to discover and mount domain-specific
tools and Standard Operating Procedures (SOPs) on demand without prompt bloat.
"""

from dataclasses import dataclass, field
import importlib.util
import inspect
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union, get_args, get_origin
import yaml

try:
    from pydantic import BaseModel, Field
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False


if PYDANTIC_AVAILABLE:
    class SkillMetadata(BaseModel):
        """Metadata extracted from SKILL.md YAML frontmatter."""
        name: str
        description: str
        version: str = "1.0.0"
        triggers: List[str] = Field(default_factory=list)
        tags: List[str] = Field(default_factory=list)
        requires_approval: bool = False
else:
    @dataclass
    class SkillMetadata:
        name: str
        description: str
        version: str = "1.0.0"
        triggers: List[str] = field(default_factory=list)
        tags: List[str] = field(default_factory=list)
        requires_approval: bool = False

        def model_dump(self) -> Dict[str, Any]:
            from dataclasses import asdict
            return asdict(self)


class SkillPackage:
    """Represents a fully loaded skill package on disk."""

    def __init__(
        self,
        metadata: SkillMetadata,
        sop_content: str,
        package_dir: Path,
        tool_callables: Optional[Dict[str, Callable[..., Any]]] = None,
        tool_schemas: Optional[List[Dict[str, Any]]] = None,
    ):
        self.metadata = metadata
        self.sop_content = sop_content
        self.package_dir = package_dir
        self.tool_callables = tool_callables or {}
        self.tool_schemas = tool_schemas or []

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def description(self) -> str:
        return self.metadata.description

    @property
    def tool_names(self) -> List[str]:
        return list(self.tool_callables.keys())

    def to_summary_line(self) -> str:
        """Returns a 1-line summary (~20 tokens) suitable for initial prompt catalogs."""
        triggers_str = f" [triggers: {', '.join(self.metadata.triggers[:3])}]" if self.metadata.triggers else ""
        return f"- {self.name}: {self.description}{triggers_str}"


def parse_skill_md(file_path: Union[str, Path]) -> Tuple[SkillMetadata, str]:
    """
    Parses a SKILL.md file, extracting YAML frontmatter and Markdown SOP body.
    Expects standard format:
    ---
    name: ...
    description: ...
    ---
    # Markdown SOP Body
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"SKILL.md file not found at: {path}")

    raw_text = path.read_text(encoding="utf-8")
    frontmatter_pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
    match = frontmatter_pattern.match(raw_text.strip())

    if not match:
        raise ValueError(
            f"Invalid SKILL.md format in {path}: Missing '---' YAML frontmatter boundaries."
        )

    yaml_block = match.group(1)
    body_markdown = match.group(2).strip()

    parsed_yaml = yaml.safe_load(yaml_block) or {}
    if not isinstance(parsed_yaml, dict):
        raise ValueError(f"Invalid YAML frontmatter in {path}: Must be a key-value mapping.")

    if "name" not in parsed_yaml or "description" not in parsed_yaml:
        raise ValueError(
            f"Invalid frontmatter in {path}: Both 'name' and 'description' are required."
        )

    metadata = SkillMetadata(
        name=str(parsed_yaml["name"]).strip(),
        description=str(parsed_yaml["description"]).strip(),
        version=str(parsed_yaml.get("version", "1.0.0")),
        triggers=[str(t).strip() for t in parsed_yaml.get("triggers", []) if t],
        tags=[str(t).strip() for t in parsed_yaml.get("tags", []) if t],
        requires_approval=bool(parsed_yaml.get("requires_approval", False)),
    )

    return metadata, body_markdown


def python_type_to_json_type(py_type: Any) -> str:
    """Maps Python types and typing constructs to standard JSON Schema types."""
    origin = get_origin(py_type)
    if origin is not None:
        if origin is Union:
            args = [a for a in get_args(py_type) if a is not type(None)]
            if args:
                return python_type_to_json_type(args[0])
            return "string"
        if origin in (list, List, set, Set, tuple):
            return "array"
        if origin in (dict, Dict):
            return "object"

    if py_type in (str,):
        return "string"
    if py_type in (int,):
        return "integer"
    if py_type in (float,):
        return "number"
    if py_type in (bool,):
        return "boolean"
    if py_type in (list,):
        return "array"
    if py_type in (dict,):
        return "object"

    return "string"


def generate_tool_schema(fn: Callable[..., Any]) -> Dict[str, Any]:
    """
    Reflects over a Python function's signature and docstring to generate
    an OpenAI/Anthropic compatible JSON Schema tool definition.
    """
    fn_name = fn.__name__
    raw_doc = inspect.getdoc(fn) or ""
    
    # Split docstring into summary description and parameter descriptions
    doc_lines = raw_doc.strip().splitlines()
    fn_desc = doc_lines[0] if doc_lines else f"Tool {fn_name}"

    param_docs: Dict[str, str] = {}
    param_doc_regex = re.compile(r"^\s*(?:Args:\s*)?([A-Za-z0-9_]+)\s*:\s*(.*)$")
    for line in doc_lines[1:]:
        m = param_doc_regex.match(line)
        if m:
            param_docs[m.group(1)] = m.group(2).strip()

    sig = inspect.signature(fn)
    try:
        type_hints = inspect.get_annotations(fn)
    except Exception:
        type_hints = getattr(fn, "__annotations__", {})

    properties: Dict[str, Any] = {}
    required: List[str] = []

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue

        param_type = type_hints.get(param_name, str)
        json_type = python_type_to_json_type(param_type)

        prop_def: Dict[str, Any] = {"type": json_type}
        if param_name in param_docs:
            prop_def["description"] = param_docs[param_name]

        if param.default is inspect.Parameter.empty:
            required.append(param_name)
        else:
            if param.default is not None:
                prop_def["default"] = param.default

        properties[param_name] = prop_def

    return {
        "type": "function",
        "function": {
            "name": fn_name,
            "description": fn_desc,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def import_tools_from_file(tools_path: Path) -> Dict[str, Callable[..., Any]]:
    """Dynamically imports callables from a tools.py file."""
    if not tools_path.is_file():
        return {}

    module_name = f"skill_tools_{tools_path.parent.name}_{tools_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, tools_path)
    if spec is None or spec.loader is None:
        return {}

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    callables: Dict[str, Callable[..., Any]] = {}
    for name, obj in inspect.getmembers(module):
        if inspect.isfunction(obj) and not name.startswith("_"):
            # Ensure the function was defined in this module
            if obj.__module__ == module_name:
                callables[name] = obj

    return callables


class SkillRegistry:
    """
    Discovers, indexes, and manages declarative skill packages across search directories.
    Provides progressive disclosure catalog summaries for agent prompts.
    """

    def __init__(self, search_paths: Optional[List[Union[str, Path]]] = None):
        self.search_paths: List[Path] = [
            Path(p).resolve() for p in (search_paths or ["skills", ".agents/skills"])
        ]
        self._skills: Dict[str, SkillPackage] = {}

    def add_search_path(self, path: Union[str, Path]) -> None:
        p = Path(path).resolve()
        if p not in self.search_paths:
            self.search_paths.append(p)

    def discover_skills(self) -> Dict[str, SkillPackage]:
        """
        Scans all configured search paths for folders containing a valid SKILL.md.
        Loads metadata, SOP instructions, and callables from tools.py if present.
        """
        discovered: Dict[str, SkillPackage] = {}

        for search_dir in self.search_paths:
            if not search_dir.is_dir():
                continue

            # Look for subdirectories or direct SKILL.md files
            for skill_file in search_dir.glob("**/SKILL.md"):
                package_dir = skill_file.parent
                try:
                    metadata, sop_content = parse_skill_md(skill_file)
                    tools_file = package_dir / "tools.py"
                    tool_callables = import_tools_from_file(tools_file) if tools_file.exists() else {}

                    tool_schemas = [
                        generate_tool_schema(fn) for fn in tool_callables.values()
                    ]

                    pkg = SkillPackage(
                        metadata=metadata,
                        sop_content=sop_content,
                        package_dir=package_dir,
                        tool_callables=tool_callables,
                        tool_schemas=tool_schemas,
                    )
                    discovered[pkg.name] = pkg
                except Exception as exc:
                    # Log or record parse error without crashing discovery of sibling skills
                    continue

        self._skills = discovered
        return self._skills

    def get_skill(self, name: str) -> Optional[SkillPackage]:
        """Returns the loaded SkillPackage by name (discovers if not yet indexed)."""
        if not self._skills:
            self.discover_skills()
        return self._skills.get(name)

    def list_skills(self) -> List[SkillMetadata]:
        """Returns metadata for all discovered skills."""
        if not self._skills:
            self.discover_skills()
        return [pkg.metadata for pkg in self._skills.values()]

    def get_catalog_summary(self) -> str:
        """
        Emits a lightweight, one-line-per-skill index.
        Designed for injection into the base prompt under Progressive Disclosure Tier 1.
        """
        if not self._skills:
            self.discover_skills()

        if not self._skills:
            return "No specialized skills loaded."

        lines = ["Available skills (activate on demand):"]
        for pkg in sorted(self._skills.values(), key=lambda p: p.name):
            lines.append(pkg.to_summary_line())

        return "\n".join(lines)
