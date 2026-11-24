"""Unit tests for Phase 1 of Universal Application Rules Engine (`core/rules.py`)."""

from pathlib import Path
import pytest
from core.rules import (
    RuleMetadata,
    RulePackage,
    RuleParseError,
    ImmutableRuleOverrideError,
    VolatilePromptPrefixError,
    normalize_content,
    parse_rule_file,
)


def test_rule_metadata_defaults() -> None:
    meta = RuleMetadata(name="test_rule")
    assert meta.name == "test_rule"
    assert meta.scope == ["*"]
    assert meta.priority == 50
    assert meta.immutable is False
    assert meta.enabled is True


def test_rule_metadata_priority_under_20_forces_immutable() -> None:
    meta = RuleMetadata(name="security_invariant", priority=10, immutable=False)
    assert meta.priority == 10
    assert meta.immutable is True  # Enforces Tier 1 non-overridable invariant


def test_normalize_content_crlf_and_bom() -> None:
    text_with_bom_and_crlf = "\ufeffLine 1\r\nLine 2\r\n  "
    normalized = normalize_content(text_with_bom_and_crlf)
    assert normalized == "Line 1\nLine 2"
    assert "\r" not in normalized
    assert "\ufeff" not in normalized


def test_parse_rule_file_valid_frontmatter(tmp_path: Path) -> None:
    rule_file = tmp_path / "sql_safety.md"
    content = """---
name: sql_safety_invariants
description: Mandatory read-only safety rules
scope:
  - database
  - sql
priority: 15
enabled: true
---

# SQL Rules
1. Only SELECT queries.
"""
    rule_file.write_text(content, encoding="utf-8")

    pkg = parse_rule_file(rule_file)
    assert pkg.metadata.name == "sql_safety_invariants"
    assert pkg.metadata.description == "Mandatory read-only safety rules"
    assert pkg.metadata.scope == ["database", "sql"]
    assert pkg.metadata.priority == 15
    assert pkg.metadata.immutable is True  # priority 15 < 20 forces immutable Tier 1
    assert pkg.metadata.enabled is True
    assert "# SQL Rules\n1. Only SELECT queries." in pkg.content


def test_parse_rule_file_no_frontmatter_fallback(tmp_path: Path) -> None:
    rule_file = tmp_path / "general_guidelines.md"
    raw_markdown = "# General Guidelines\nBe concise and clear."
    rule_file.write_text(raw_markdown, encoding="utf-8")

    pkg = parse_rule_file(rule_file)
    assert pkg.metadata.name == "general_guidelines"
    assert pkg.metadata.scope == ["*"]
    assert pkg.metadata.priority == 50  # Tier 3 default
    assert pkg.metadata.immutable is False
    assert pkg.content == raw_markdown


def test_parse_rule_file_malformed_yaml_raises_error(tmp_path: Path) -> None:
    rule_file = tmp_path / "corrupted.md"
    content = """---
name: [unclosed list
priority: 10
---
Broken rule content
"""
    rule_file.write_text(content, encoding="utf-8")

    with pytest.raises(RuleParseError) as exc_info:
        parse_rule_file(rule_file)
    assert "Malformed YAML frontmatter" in str(exc_info.value)


def test_parse_rule_file_nonexistent_raises_file_not_found(tmp_path: Path) -> None:
    missing_file = tmp_path / "nonexistent.md"
    with pytest.raises(FileNotFoundError):
        parse_rule_file(missing_file)


# --- Phase 2: RuleRegistry Tests ---

from core.rules import RuleRegistry


def test_rule_registry_discovery_and_scoping(tmp_path: Path) -> None:
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()

    # 1. Global Rule
    (rules_dir / "00_global.md").write_text("""---
name: global_invariants
scope: ["*"]
priority: 10
---
Global safety rule.
""", encoding="utf-8")

    # 2. Database Scoped Rule
    (rules_dir / "20_database.md").write_text("""---
name: sql_rules
scope: ["database", "sql"]
priority: 25
---
SQL only select.
""", encoding="utf-8")

    # 3. Email Scoped Rule
    (rules_dir / "30_email.md").write_text("""---
name: email_rules
scope: ["email"]
priority: 30
---
Email hitl gate.
""", encoding="utf-8")

    registry = RuleRegistry(search_paths=[rules_dir])
    discovered = registry.discover_rules()
    assert len(discovered) == 3

    # Query database scope: should return global + database, but not email
    db_rules = registry.get_rules_for_scope(["database"])
    assert len(db_rules) == 2
    rule_names = [r.metadata.name for r in db_rules]
    assert rule_names == ["global_invariants", "sql_rules"]

    # Query empty scope: should return global only
    general_rules = registry.get_rules_for_scope([])
    assert len(general_rules) == 1
    assert general_rules[0].metadata.name == "global_invariants"


def test_rule_registry_tier2_override_by_downstream_path(tmp_path: Path) -> None:
    default_rules = tmp_path / "default_rules"
    custom_rules = tmp_path / "custom_rules"
    default_rules.mkdir()
    custom_rules.mkdir()

    # Base Tier 2 rule in default path
    (default_rules / "formatting.md").write_text("""---
name: code_formatting
scope: ["*"]
priority: 30
---
Use 4 spaces indentation.
""", encoding="utf-8")

    # Overriding Tier 2 rule in custom path
    (custom_rules / "formatting.md").write_text("""---
name: code_formatting
scope: ["*"]
priority: 30
---
Use 2 spaces indentation for frontend.
""", encoding="utf-8")

    # custom_rules has higher precedence (listed first)
    registry = RuleRegistry(search_paths=[custom_rules, default_rules])
    rules = registry.get_rules_for_scope()
    assert len(rules) == 1
    assert "Use 2 spaces indentation" in rules[0].content


def test_rule_registry_tier1_invariant_override_raises_error(tmp_path: Path) -> None:
    default_rules = tmp_path / "default_rules"
    custom_rules = tmp_path / "custom_rules"
    default_rules.mkdir()
    custom_rules.mkdir()

    # Tier 1 Invariant (priority 10 < 20 forces immutable)
    (default_rules / "read_only.md").write_text("""---
name: database_read_only
scope: ["database"]
priority: 10
immutable: true
---
Never run DROP or DELETE.
""", encoding="utf-8")

    # Attempt to override Tier 1 in custom path
    (custom_rules / "read_only.md").write_text("""---
name: database_read_only
scope: ["database"]
priority: 50
immutable: false
---
Allow DROP table for dev.
""", encoding="utf-8")

    registry = RuleRegistry(search_paths=[custom_rules, default_rules])
    with pytest.raises(ImmutableRuleOverrideError) as exc_info:
        registry.get_rules_for_scope(["database"])
    assert "attempts to override immutable Tier 1 invariant" in str(exc_info.value)


# --- Phase 3: RuleManager Tests ---

from core.rules import RuleManager, assert_no_volatile_tokens


def test_volatile_token_detection_raises_error() -> None:
    # 1. ISO datetime
    with pytest.raises(VolatilePromptPrefixError) as exc_info:
        assert_no_volatile_tokens("System started at 2026-11-24T10:30:00Z")
    assert "Volatile datetime token" in str(exc_info.value)

    # 2. UUID
    with pytest.raises(VolatilePromptPrefixError) as exc_info:
        assert_no_volatile_tokens("Session ID: 12345678-1234-1234-1234-123456789abc")
    assert "Volatile UUID token" in str(exc_info.value)

    # 3. Unrendered template
    with pytest.raises(VolatilePromptPrefixError) as exc_info:
        assert_no_volatile_tokens("User: ${USER_NAME}")
    assert "Unrendered template placeholder" in str(exc_info.value)

    # 4. Safe version strings should NOT raise
    assert_no_volatile_tokens("Using python-3.11-slim and pytest version >= 8.2.2")


def test_rule_manager_deterministic_sorting_and_sha256(tmp_path: Path) -> None:
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()

    (rules_dir / "tier1.md").write_text("""---
name: tier1_invariants
scope: ["*"]
priority: 5
---
Tier 1 Safety
""", encoding="utf-8")

    (rules_dir / "tier2.md").write_text("""---
name: tier2_guidelines
scope: ["*"]
priority: 30
---
Tier 2 Guidelines
""", encoding="utf-8")

    (rules_dir / "tier3.md").write_text("""---
name: tier3_custom
scope: ["*"]
priority: 60
---
Tier 3 Custom
""", encoding="utf-8")

    registry = RuleRegistry(search_paths=[rules_dir])
    manager = RuleManager(registry=registry)

    compiled1 = manager.compile_system_prefix(agent_role="You are an autonomous DB assistant.")
    compiled2 = manager.compile_system_prefix(agent_role="You are an autonomous DB assistant.")

    # 1. Deterministic sorting: Tier 1 -> Tier 2 -> Tier 3
    assert compiled1.active_rule_names == ["tier1_invariants", "tier2_guidelines", "tier3_custom"]
    assert compiled1.system_prompt.index("tier1_invariants") < compiled1.system_prompt.index("tier2_guidelines")
    assert compiled1.system_prompt.index("tier2_guidelines") < compiled1.system_prompt.index("tier3_custom")

    # 2. Byte hash invariance across runs
    assert compiled1.sha256_hash == compiled2.sha256_hash
    assert len(compiled1.sha256_hash) == 64

    # 3. Provider formatting
    openai_fmt = manager.format_for_provider(compiled1, provider="openai")
    anthropic_fmt = manager.format_for_provider(compiled1, provider="anthropic")
    assert isinstance(openai_fmt, str)
    assert isinstance(anthropic_fmt, list)
    assert anthropic_fmt[0]["cache_control"] == {"type": "ephemeral"}


# --- Phase 5: RuleLinter & CLI Tests ---

from core.rules import RuleLinter, run_cli


def test_rule_linter_detects_malformed_yaml(tmp_path: Path) -> None:
    bad_rule = tmp_path / "broken.md"
    bad_rule.write_text("""---
name: [unclosed
priority: 10
---
body
""", encoding="utf-8")

    linter = RuleLinter(search_paths=[tmp_path])
    report = linter.lint_all()
    assert report.scanned_files_count == 1
    assert report.error_count == 1
    assert report.valid_rules_count == 0
    assert "Syntax/Schema Error" in report.issues[0].message


def test_rule_linter_detects_volatile_tokens(tmp_path: Path) -> None:
    volatile_rule = tmp_path / "volatile.md"
    volatile_rule.write_text("""---
name: volatile_rule
scope: ["*"]
priority: 30
---
Rule created on 2026-11-24T12:00:00Z for session ${SESSION_ID}.
""", encoding="utf-8")

    linter = RuleLinter(search_paths=[tmp_path])
    report = linter.lint_all()
    assert report.scanned_files_count == 1
    assert report.error_count >= 1
    assert any("Volatile datetime token" in i.message for i in report.issues)


def test_rule_linter_detects_empty_body(tmp_path: Path) -> None:
    empty_rule = tmp_path / "empty.md"
    empty_rule.write_text("""---
name: empty_rule
scope: ["*"]
priority: 30
---
""", encoding="utf-8")

    linter = RuleLinter(search_paths=[tmp_path])
    report = linter.lint_all()
    assert report.warning_count == 1
    assert "markdown body is empty" in report.issues[0].message


def test_rule_linter_cli_entrypoint(tmp_path: Path, capsys) -> None:
    valid_rule = tmp_path / "valid.md"
    valid_rule.write_text("""---
name: valid_rule
scope: ["test"]
priority: 40
---
# Valid Rule
Content that is completely clean and valid.
""", encoding="utf-8")

    # Run CLI successfully
    exit_code = run_cli(["lint", str(tmp_path)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "RULES ENGINE LINTER REPORT" in captured.out
    assert "Linting PASSED" in captured.out



