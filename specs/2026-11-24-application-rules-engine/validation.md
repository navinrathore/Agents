# Validation: Universal Application Rules Engine (`RuleManager`)

## Test Matrix & Verification Criteria

| Test Category | Target Component | Input / Scenario | Expected Outcome & Assertion Criteria |
| :--- | :--- | :--- | :--- |
| **Frontmatter Parsing** | `parse_rule_file()` | Markdown file with YAML frontmatter (`name`, `priority`, `scope`). | Correctly populates `RuleMetadata` fields via `yaml.safe_load`; separates YAML header from Markdown body. |
| **Malformed Frontmatter** | `parse_rule_file()` | Corrupted YAML frontmatter syntax. | Raises `RuleParseError` with clear diagnostic file path and syntax error details. |
| **No-Frontmatter Fallback** | `parse_rule_file()` | Plain markdown file without YAML frontmatter. | Derives name from filename, sets default priority=50 (Tier 3), scope=`["*"]` (global), enabled=True. |
| **Directory Discovery & Precedence** | `RuleRegistry.discover_rules()` | Multi-directory structure (`config/rules/`, `rules/`) with duplicate names. | Discovers all `.md` files; respects directory search precedence and caches in-memory under `threading.RLock`. |
| **Scope Filtering & Fallback** | `RuleRegistry.get_rules_for_scope()` | Rules with `scope: ["*"]`, `scope: ["database"]`, and `scope: ["email"]`. Requested scope: `["database"]` and `[]`. | Returns global rule + database rule; strictly excludes email rule. When scope is empty, returns global rules only. |
| **Tier 1 Invariant Override Rejection** | `RuleRegistry.get_rules_for_scope()` | Downstream rule attempts to override a rule with `immutable: true` or `priority < 20`. | Raises `ImmutableRuleOverrideError`; protects safety invariants from being altered. |
| **Deterministic Sorting** | `RuleManager.compile_system_prefix()` | Multiple rules with priorities 50, 10, 20 and identical priorities with different names. | Output text places Priority 10 first, Priority 20 second, Priority 50 third. Tie-breakers use `(priority, name, file_path)`. |
| **Cache Byte Invariance & CRLF/BOM Normalization** | `RuleManager.compile_system_prefix()` | Multiple calls across different runs, with CRLF vs LF line endings and UTF-8 BOM. | SHA-256 byte hash (`sha256(compiled_text)`) is strictly identical across invocations after newline & Unicode NFKC normalization. |
| **Volatile Token Contamination Guard** | `RuleManager.compile_system_prefix()` | Rule or static block contains ISO timestamp, UUID, or unrendered `${...}` template. Does not false-positive on version strings like `3.11-slim`. | Raises `VolatilePromptPrefixError` before compiling prompt, preventing cache invalidation. |
| **Anthropic Cache Breakpoint** | `RuleManager.format_for_anthropic()` | Multi-rule compilation with cache control enabled. | Injects `cache_control: {"type": "ephemeral"}` on the final static block of the system prompt blocks. |
| **Agent Integration** | `DatabaseAgent` + `RuleManager` | Instantiating `DatabaseAgent` configured with `RuleManager(scopes=["database"])`. | Agent prompt reflects rules loaded from disk (`rules/20_sql_invariants.md`); passes query execution tests. |
| **Full Regression** | Workspace Test Suite | `pytest tests/` | All 170 existing unit and integration tests pass with 0 regressions. |
