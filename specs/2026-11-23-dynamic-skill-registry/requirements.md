# Requirements: Dynamic Skill / Tool Package Registry

## Overview
As autonomous agents scale to enterprise capabilities, providing 50+ tools and thousands of lines of prompt instructions in every single LLM turn causes severe prompt bloat, high token costs, elevated latency, and catastrophic tool selection hallucinations.

The **Dynamic Skill / Tool Package Registry** provides an **optional**, pluggable package management and runtime mounting layer for `AsyncToolDispatcher`. It keeps the LLM context lean by:
1. Treating capabilities as modular, declarative packages on disk (a directory with `SKILL.md` + optional `tools.py`).
2. Keeping the agent's base prompt and tool schemas minimal.
3. Dynamically discovering, routing, and mounting tools into `AsyncToolDispatcher` **only when relevant** to the user's intent.
4. Dynamically injecting the skill's Standard Operating Procedure (SOP) instructions into the prompt on demand, and unmounting them when finished.

> [!IMPORTANT]
> **Optionality & Non-Breaking Invariance**:
> - Direct tool registration via `dispatcher.register_tool()`, MCP bridging, and OpenAPI ingestion must remain 100% functional without requiring skills.
> - Smaller agents or applications with 2–5 tools can completely bypass the `SkillRegistry` with zero overhead.

---

## 1. Scope

### In-Scope
- **Declarative Skill Package Specification**:
  - Standard directory layout:
    ```
    skills/<skill_name>/
    ├── SKILL.md                 # YAML frontmatter (metadata/triggers) + Markdown SOP
    ├── tools.py                 # (Optional) Python functions to execute
    └── templates/               # (Optional) Prompt templates, few-shot examples
    ```
  - YAML Frontmatter schema: `name`, `description`, `version`, `triggers` (keywords or intents), `requires_approval`, `tags`.
- **Core Registry Engine (`core/skills.py`)**:
  - `SkillPackage`: Encapsulates parsed frontmatter, SOP body, tool callables, and tool schemas.
  - `SkillRegistry`: Discovers skills across configured directories (e.g. `projects/Agents/skills/`, `~/.agents/skills/`), validates package structure, and caches metadata.
  - `SkillRouter`: Cascading Hybrid Router with:
    - *Tier 1 (Fast Deterministic Path)*: Instant sub-millisecond keyword, trigger, and regex matching against `SKILL.md` frontmatter ($0 token tax).
    - *Tier 2 (Semantic / LLM Fallback Path)*: Optional LLM-assisted or semantic intent classifier invoked only when Tier 1 produces zero matches.
- **Dynamic Mounting Lifecycle**:
  - `mount_skill(skill_name, dispatcher)`: Extracts tool callables from `tools.py` and registers them into `AsyncToolDispatcher`.
  - `unmount_skill(skill_name, dispatcher)`: Cleanly unregisters the skill's tools, restoring the dispatcher to its baseline.
  - `get_active_prompt_extensions()`: Aggregates active SOP instructions to append to the agent's system prompt.
- **Provider-Agnostic Schema Extraction**:
  - Automatically inspects Python function signatures and docstrings in `tools.py` to generate standard tool schemas (OpenAI/Anthropic compatible) without third-party dependencies.

### Out-of-Scope
- Downloading third-party untrusted code from remote internet registries (all skills must reside in local, trusted directories).
- Complex multi-agent distributed routing (this module focuses on in-process skill mounting for an agent loop).
