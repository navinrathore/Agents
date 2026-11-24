# Requirements: Universal Application Rules Engine (`RuleManager`)

## 1. Executive Summary & Problem Definition
In enterprise agentic systems (e.g. Google Antigravity, Claude Code, Cursor, LangGraph, and financial/legal autonomous applications), LLMs require strict operational boundaries:
- Negative constraints ("Never modify records without approval", "Never output markdown fences in structured mode").
- Format contracts (JSON schema, SQL dialect specifics).
- Safety boundaries (HITL gates, read-only guarantees).

Currently, in many ad-hoc agent implementations, developers hardcode prompt strings directly inside Python classes (e.g. `agent.py::_build_system_prompt()`). This causes several critical enterprise defects:
1. **The Dynamic Invalidation Trap**: Developers inject dynamic timestamps, request IDs, or volatile variables at the top of the system prompt, causing a **0% KV cache hit rate** on frontier providers (Anthropic, OpenAI, Gemini), increasing input token costs by 5x–10x and degrading latency (TTFT).
2. **Coupling & Brittleness**: Non-engineering compliance, security, or domain teams cannot update system rules without editing and redeploying Python application code.
3. **Monolithic Bloat**: Trying to cram every domain rule into one giant prompt violates context limits and degrades model instruction-following.

`RuleManager` is an in-core, declarative rule discovery, compilation, and prompt-caching engine that loads generic and domain-scoped rule files (`rules/*.md`) and produces an immutable, deterministic static KV prefix.

---

## 2. Industry Benchmark & Comparative Analysis

| Platform / Framework | Rule Convention & Storage | Discovery & Scoping Mechanism | Caching Strategy |
| :--- | :--- | :--- | :--- |
| **Cursor** | `.cursor/rules/*.mdc` | Glob pattern matching (`globs: ["*.sql", "src/**/*.py"]`) | Attached to context when active editor buffer matches glob. |
| **Claude Code (Anthropic)** | `CLAUDE.md` (Hierarchical root $\to$ subfolders) | Directory tree traversal; nearest `CLAUDE.md` loaded into context | Explicit cache breakpoint marker (`cache_control={"type": "ephemeral"}`). |
| **Google Antigravity** | `.agents/rules/*.md` and `~/.gemini/antigravity/rules/` | YAML frontmatter triggers and global priority sorting | Static `<system_instruction>` block at turn 0 ahead of conversational turns. |
| **Enterprise LangGraph / CrewAI** | Declarative YAML / Pydantic config | State machine node preambles bound to specific agent roles | Left-to-right longest-prefix matching on static configuration prefixes. |

---

## 3. Scope & Capabilities

### In-Scope:
- **Declarative Rule Discovery**:
  - Scans designated rule directories (`rules/`, `.agents/rules/`, `config/rules/`).
  - Supports Markdown files (`.md`) with optional YAML frontmatter (`name`, `priority`, `scope`, `tags`, `enabled`).
- **Generic & Domain-Scoped Rules**:
  - **Global Invariants (`scope: ["*"]` or generic files like `global.md`)**: Always included across all agents.
  - **Scoped Rules (`scope: ["database", "sql"]`)**: Included only when an agent declares matching scopes or triggers.
- **Deterministic Prompt Compilation (The "Invariant-to-Variant" Rule)**:
  - Supports the **Three-Tier Rule Precedence Model**:
    - *Tier 1 (Immutable Invariants)*: Non-overridable security constraints (`priority < 20` or `immutable: true`). Placed at position 0. Any attempt to override a Tier 1 rule by name or path raises an `ImmutableRuleOverrideError`.
    - *Tier 2 (Default Policies)*: Framework standard guidelines (priority 20–49). Overridable by downstream configs.
    - *Tier 3 (Contextual Overrides)*: Project- or skill-specific adjustments (priority 50+ or rules defined in downstream `config/rules/`). Replaces matching Tier 2 rules by identifier (`name`), but strictly forbidden from altering Tier 1 invariants.
  - **Deduplication Precedence Rule**: When multiple candidate rules share the same `name`, the rule discovered from the higher-precedence `search_path` (earlier in configured search path list: e.g. `config/rules/` > `.agents/rules/` > `rules/`) wins, provided the target is not a Tier 1 invariant (which raises `ImmutableRuleOverrideError`). If both are Tier 2, the downstream path wins.
  - Sorts rules deterministically: `Tier 1 Invariants (Priority 0-19)` $\to$ `Tier 2 Framework Guidelines (Priority 20-49)` $\to$ `Tier 3 Contextual Overrides (Priority 50+)`, with a strict tie-breaker tuple: `(priority ASC, name ASC, file_path ASC)`.
  - Guarantees exact byte-for-byte reproducibility across turns via Unicode NFKC normalization, BOM stripping, LF newline conversion (`\r\n` $\to$ `\n`), and stripped trailing whitespace.
- **Provider-Aware Cache Breakpoints & Token Thresholds**:
  - Documents provider-specific caching thresholds: Anthropic and OpenAI require $\ge 1,024$ tokens to activate prefix caching (compounded with static agent context/schema DDL), while Gemini Context Caching requires $\ge 32,768$ tokens.
  - Formats output as Anthropic-compatible message blocks with `cache_control: {"type": "ephemeral"}` in the `system` parameter block or standard OpenAI/Gemini system prompt strings.
- **Rule Verification, Linting & Contamination Guard**:
  - Compile-time regex checks to reject volatile dynamic variables:
    - ISO-8601 datetimes: `\b\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])(?:T|\s)\d{2}:\d{2}` (avoiding false positives on python versions like `3.11-slim`).
    - Standard UUID4: `\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b`.
    - Unrendered template placeholders: `\{\{.*?\}\}` or `\$\{.*?\}`.
  - Raises `VolatilePromptPrefixError` if detected in static prefix blocks.

### Out-of-Scope:
- Interactive user chat moderation (that is handled by OutputGuard / input filters).
- Dynamic database schema introspection (handled by Layer 1 `DatabaseEngine`).

---

## 4. Data Contract & Schema Specifications

### Rule File Format (`rules/<rule_name>.md`)
```markdown
---
name: sql_safety_invariants
description: Mandatory read-only safety rules for relational database agents
scope:
  - database
  - sql
  - analytics
priority: 20
enabled: true
---

# SQL Operational Invariants
1. ONLY generate read-only queries (SELECT or WITH ... SELECT).
2. Never execute DDL (DROP, CREATE, ALTER) or DML (DELETE, UPDATE, INSERT).
3. Always verify join columns against the reflected database foreign key graph.
```

### Core Data Models
- `RuleMetadata`:
  - `name: str`
  - `description: str`
  - `scope: List[str]`
  - `priority: int`
  - `immutable: bool = False` (If True, cannot be overridden by project/skill configs)
  - `enabled: bool = True`
  - `file_path: Path`
- `RulePackage`: `metadata: RuleMetadata`, `content: str` (raw markdown body).
- `CompiledPromptPrefix`:
  - `system_prompt: str` (deterministic compiled text).
  - `cached_token_estimate: int`.
  - `active_rule_names: List[str]`.
  - `cache_control_blocks: Optional[List[Dict[str, Any]]]`.

