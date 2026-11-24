# Plan: Universal Application Rules Engine (`core/rules.py`)

## Architecture Flow

```
                      Rule Files on Disk
              (rules/*.md, config/rules/*.md)
                             │
                             ▼
                    ┌─────────────────┐
                    │   RuleScanner   │
                    │ & YAML Parser   │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  RuleRegistry   │
                    │ (Indexes rules  │
                    │  by scope/prio) │
                    └────────┬────────┘
                             │
               Target Scopes (e.g. ['database'])
                             │
                             ▼
                    ┌─────────────────┐
                    │   RuleManager   │
                    │ (Filters &      │
                    │  Sorts rules)   │
                    └────────┬────────┘
                             │
           Deterministic Compilation & KV Cache Structuring
                             │
                             ▼
               ┌───────────────────────────┐
               │    CompiledPromptPrefix   │
               │  - Static System Prompt   │
               │  - Anthropic cache_control│
               │  - Token Estimations      │
               └─────────────┬─────────────┘
                             │
              Directly feeds into BaseLLMClient
               (Ahead of dynamic user messages)
```

---

## Phased Implementation Roadmap

### Phase 1: Data Contracts & Rule Parsing (`core/rules.py`)
1. Define `RuleMetadata` and `RulePackage` dataclasses.
2. Implement `parse_rule_file(path: Path) -> RulePackage`:
   - Extracts YAML frontmatter (`name`, `description`, `scope`, `priority`, `enabled`).
   - Normalizes markdown body content.
3. Unit tests verifying parsing of valid rules, rules without frontmatter, and malformed files.

### Phase 2: Discovery & Registry (`RuleRegistry`)
1. Implement `RuleRegistry(search_paths: List[Path])`:
   - `discover_rules()`: walks search paths in deterministic precedence order (`config/rules/` > `.agents/rules/` > `rules/`), parses `.md` files using `yaml.safe_load`.
   - Protects state mutation with `threading.RLock()` to guarantee thread safety in multi-threaded environments.
   - Detects symlink loops and avoids infinite directory traversal (`follow_symlinks=False` or visited inode set).
   - In-memory index caching with file `mtime` tracking to prevent redundant disk I/O on every turn.
   - `get_rules_for_scope(scopes: List[str]) -> List[RulePackage]`:
     - Scope filter: Collects global rules (`scope=["*"]`) + any matching the requested scopes.
     - Deduplication & Tier 1 Invariant Enforcement:
       - Groups candidate rules by `name`.
       - When multiple rules share a name, highest-precedence search path wins.
       - If an override targets an existing rule where `immutable is True` or `priority < 20`, raise `ImmutableRuleOverrideError`.
       - If both rules are Tier 2, downstream path replaces default.
     - Sorts strictly by `(priority ASC, name ASC, file_path ASC)` for deterministic KV caching.

### Phase 3: Prompt Compiler & Cache Guard (`RuleManager`)
1. Implement `RuleManager(registry: RuleRegistry)`:
   - `compile_system_prefix(agent_role: str, scopes: List[str], extra_static_blocks: List[str]) -> CompiledPromptPrefix`:
     - Compiles: `[AGENT_ROLE] -> [TIER 1 INVARIANTS] -> [TIER 2 DEFAULTS] -> [TIER 3 OVERRIDES] -> [STATIC_CONTEXT]`.
     - In-memory memoization / `freeze()`: caches compiled result keyed by `(agent_role, frozenset(scopes))` to ensure it is compiled once per session and not repeated per-turn.
     - Validates against volatile dynamic tokens: checks for ISO-8601 timestamps (`\b\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])(?:T|\s)\d{2}:\d{2}`), UUID4s, and unrendered template tokens (`{{...}}`, `${...}`). Raises `VolatilePromptPrefixError` if detected.
     - Normalizes line endings to LF (`\n`), strips UTF-8 BOM, and applies NFKC normalization.
     - Diagnostic token estimation: logs an informative notice if prefix < 1,024 tokens (noting that Anthropic/OpenAI caching engages at $\ge 1,024$ tokens).
   - `format_for_provider(provider: str)`: Emits formatted string or Anthropic `cache_control={"type": "ephemeral"}` block payload for system message blocks.

### Phase 4: Integration with `BaseLLMClient` & `DatabaseAgent`
1. Expose `RuleManager`, `RuleRegistry`, `RuleMetadata`, and custom exceptions in `core/rules.py` and `core/__init__.py`.
2. Update `core/llm_clients.py`:
   - Extend `BaseLLMClient.set_system_prompt` and `AnthropicClient.generate` to accept `Union[str, List[Dict[str, Any]]]` so Anthropic prompt caching structured blocks with `cache_control` pass through seamlessly.
3. Refactor `DatabaseAgent` to optionally load from `RuleManager(scopes=["database"])` instead of hardcoded strings.
4. Establish default project directory `projects/Agents/rules/` with standard generic rules:
   - `00_global_invariants.md`: Universal safety, circuit breakers, and output discipline (Tier 1, `priority: 10`, `immutable: true`).
   - `10_security_guardrails.md`: PII, secrets, and sandboxing boundaries (Tier 1, `priority: 15`, `immutable: true`).
   - `20_sql_invariants.md`: Specific database invariants (Tier 2, `priority: 25`).

### Phase 5: Verification & Comprehensive Test Suite (`tests/test_rules.py`)
1. Discovery and frontmatter parsing tests.
2. Scope filtering and priority ordering assertions.
3. Deterministic byte-for-byte cache stability verification.
4. Full regression across all existing project test suites.
