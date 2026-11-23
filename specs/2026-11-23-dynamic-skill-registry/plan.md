# Plan: Dynamic Skill / Tool Package Registry

## Proposed Architecture

```
                          User Query: "Run SQL analysis on users table"
                                              │
                                              ▼
                                    ┌───────────────────┐
                                    │    SkillRouter    │
                                    │ (Matches triggers)│
                                    └─────────┬─────────┘
                                              │ Matched: "sql_analyst"
                                              ▼
                                    ┌───────────────────┐
                                    │   SkillRegistry   │
                                    │ (Loads package)   │
                                    └─────────┬─────────┘
                                              │
                    ┌─────────────────────────┴─────────────────────────┐
                    ▼                                                   ▼
         Extract SOP Markdown                                 Mount Tools Dynamically
     (Appended to System Prompt)                        (Registered into AsyncToolDispatcher)
  "When analyzing tables, first run..."                      - query_table()
                                                             - describe_table()
                                                                        │
                                                                        ▼
                                                        Execute Tool Calls via Dispatcher
                                                                        │
                                                                        ▼
                                                            Unmount Tools (Optional/Reset)
```

---

## Phased Implementation Plan

### Phase 1: Skill Package Specification & Discovery (`projects/Agents/core/skills.py`)
1. **Data Models**:
   - `SkillMetadata`: Pydantic/dataclass schema representing YAML frontmatter (`name`, `description`, `version`, `triggers`, `tags`, `requires_approval`).
   - `SkillPackage`: Encapsulates `metadata`, `sop_content` (markdown), `tool_callables: Dict[str, Callable]`, `tool_schemas: List[Dict[str, Any]]`, and file paths.
2. **`SkillRegistry`**:
   - `__init__(search_paths: List[Union[str, Path]])`
   - `discover_skills() -> Dict[str, SkillPackage]`: Scans folders, parses `SKILL.md` frontmatter, dynamically imports `tools.py` if present, and extracts JSON tool schemas.
   - `get_skill(name: str) -> Optional[SkillPackage]`
   - `list_skills() -> List[SkillMetadata]`

### Phase 2: Intent Router & Dynamic Dispatcher Mounting
1. **`SkillRouter` (The Cascading Hybrid Router)**:
   - **Tier 1 (Fast Path)**: Rule-based keyword, trigger, and regex matching against `SkillMetadata.triggers` and `tags` ($0 token tax, < 1ms).
   - **Tier 2 (Fallback Path)**: Optional `llm_classifier: Optional[Callable[[str, List[SkillMetadata]], List[str]]]` or LLM client invocation when Tier 1 produces zero matches.
   - `route(query: str) -> List[str]`: Cascades through Tier 1 first, then Tier 2 if configured and needed.
2. **`SkillManager` (Supervisory Coordinator)**:
   - Manages active skills in the current agent session.
   - `activate_skills(skill_names: List[str], dispatcher: AsyncToolDispatcher)`: Dynamically registers tools into dispatcher.
   - `deactivate_skills(skill_names: List[str], dispatcher: AsyncToolDispatcher)`: Cleanly unregisters tools.
   - `build_system_prompt(base_prompt: str) -> str`: Appends active SOP markdown sections to the system prompt.

### Phase 3: Sample Skill Packages
1. Create a representative skill package under `projects/Agents/skills/data_analyst/`:
   - `SKILL.md`: Metadata and step-by-step SQL analysis instructions.
   - `tools.py`: Python tool functions (`query_table`, `describe_table`).
2. Create an admin / ops skill package under `projects/Agents/skills/system_ops/`:
   - `SKILL.md`: DevOps inspection guidelines.
   - `tools.py`: Sample ops utilities.

### Phase 4: Unit & Integration Verification (`projects/Agents/tests/test_skills.py`)
1. Verification of YAML frontmatter parsing and SOP extraction.
2. Automatic tool schema extraction from Python functions and type hints.
3. Query intent routing and trigger matching.
4. Dynamic mounting into `AsyncToolDispatcher` (verifying tools execute when mounted, and are unavailable when unmounted).
5. Ensuring baseline dispatcher and existing tools remain 100% unaffected.
