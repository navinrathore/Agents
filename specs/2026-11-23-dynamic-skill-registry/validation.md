# Validation: Dynamic Skill / Tool Package Registry

## Test Matrix

| Test Case | Component | Verification Criteria |
| :--- | :--- | :--- |
| **Frontmatter & SOP Extraction** | `SkillRegistry` | Successfully extracts `name`, `description`, `triggers` from `SKILL.md` YAML header and separates the SOP body. |
| **Schema Generation from `tools.py`** | `SkillRegistry` | Automatically converts typed Python functions in `tools.py` into compliant OpenAI/Anthropic tool schemas. |
| **Query Routing** | `SkillRouter` | Matches query text to appropriate skills based on triggers, keyword matches, and tags. Returns empty list on irrelevant queries. |
| **Dynamic Tool Mounting** | `SkillManager` + `AsyncToolDispatcher` | When skill is activated, its tools become callable on the dispatcher; tool execution produces expected results. |
| **Dynamic Tool Unmounting** | `SkillManager` + `AsyncToolDispatcher` | When skill is deactivated, tools are removed from dispatcher (`unregister_tool`); subsequent calls to that tool return unknown tool error. |
| **Prompt SOP Injection** | `SkillManager` | `build_system_prompt()` cleanly injects active SOP markdown blocks without modifying base prompt when no skills are active. |
| **Existing Dispatcher Invariance** | `AsyncToolDispatcher` | Tools registered directly (e.g. `dispatcher.register_tool(...)`) work identically regardless of whether `SkillManager` is used. |
| **Full Regression Suite** | Full Test Harness | All existing 104 tests continue to pass with zero regressions. |
