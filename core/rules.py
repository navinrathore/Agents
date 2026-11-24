"""Universal Application Rules Engine (`RuleManager`).

Implements declarative rule discovery, three-tier precedence resolution,
and deterministic KV-cache prompt prefix compilation according to AGENTS.md Rule 16.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import os
import re
import threading
from typing import Any, Dict, List, Optional, Set, Tuple
import unicodedata
import yaml


# --- Custom Exception Hierarchy ---

class RuleEngineError(Exception):
    """Base exception for all Rule Engine errors."""
    pass


class RuleParseError(RuleEngineError):
    """Raised when a rule markdown file contains malformed frontmatter or unreadable content."""
    pass


class ImmutableRuleOverrideError(RuleEngineError):
    """Raised when a rule attempts to override a Tier 1 Immutable Invariant."""
    pass


class VolatilePromptPrefixError(RuleEngineError):
    """Raised when volatile dynamic tokens (timestamps, UUIDs, templates) contaminate the static prefix."""
    pass


# --- Core Data Contracts (Dataclasses) ---

@dataclass
class RuleMetadata:
    """Metadata extracted from rule file YAML frontmatter."""
    name: str
    description: str = ""
    scope: List[str] = field(default_factory=lambda: ["*"])
    priority: int = 50
    immutable: bool = False
    enabled: bool = True
    file_path: Optional[Path] = None

    def __post_init__(self) -> None:
        # Enforce Tier 1 invariant rule: Any rule with priority < 20 is strictly immutable.
        if self.priority < 20:
            self.immutable = True

        # Normalize scope: ensure non-empty list of stripped lowercase strings
        if not self.scope:
            self.scope = ["*"]
        else:
            self.scope = [s.strip().lower() for s in self.scope if isinstance(s, str) and s.strip()]
            if not self.scope:
                self.scope = ["*"]


@dataclass
class RulePackage:
    """Complete rule package containing parsed metadata and normalized markdown body."""
    metadata: RuleMetadata
    content: str  # Markdown body normalized with LF line endings and stripped whitespace


@dataclass
class CompiledPromptPrefix:
    """Deterministic compiled static system prompt prefix for KV-cache optimization."""
    system_prompt: str
    sha256_hash: str
    cached_token_estimate: int
    active_rule_names: List[str]
    cache_control_blocks: Optional[List[Dict[str, Any]]] = None


# --- Regex Patterns for Normalization & Parsing ---

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n(.*)$", re.DOTALL)


def normalize_content(text: str) -> str:
    """Normalize text with Unicode NFKC, strip UTF-8 BOM, and enforce LF newlines.
    
    Guarantees cross-platform byte invariance across Linux, macOS, and Windows.
    """
    if text.startswith("\ufeff"):
        text = text[1:]
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def parse_rule_file(file_path: Path | str) -> RulePackage:
    """Parse a markdown rule file, extracting YAML frontmatter and markdown body.
    
    If frontmatter is missing, derives rule metadata from the filename with default priority=50.
    Uses yaml.safe_load to prevent arbitrary code execution vulnerabilities.
    
    Raises:
        FileNotFoundError: If the file does not exist.
        RuleParseError: If YAML frontmatter is malformed.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Rule file does not exist: {path}")

    try:
        raw_text = path.read_text(encoding="utf-8")
    except Exception as e:
        raise RuleParseError(f"Failed to read rule file {path}: {e}") from e

    normalized_raw = normalize_content(raw_text)
    match = _FRONTMATTER_PATTERN.match(normalized_raw)

    if not match:
        # No YAML frontmatter: fallback to filename as rule name, default priority 50 (Tier 3)
        name = path.stem.lower().replace(" ", "_")
        metadata = RuleMetadata(
            name=name,
            description=f"Rule loaded from {path.name}",
            scope=["*"],
            priority=50,
            immutable=False,
            enabled=True,
            file_path=path,
        )
        return RulePackage(metadata=metadata, content=normalized_raw)

    yaml_block, body_content = match.groups()

    try:
        data = yaml.safe_load(yaml_block) or {}
    except Exception as e:
        raise RuleParseError(f"Malformed YAML frontmatter in {path}: {e}") from e

    if not isinstance(data, dict):
        raise RuleParseError(f"YAML frontmatter in {path} must be a dictionary, got {type(data).__name__}")

    # Extract fields with safe fallbacks
    name = str(data.get("name") or path.stem).strip().lower().replace(" ", "_")
    description = str(data.get("description", "")).strip()

    raw_scope = data.get("scope", ["*"])
    if isinstance(raw_scope, str):
        scope = [raw_scope]
    elif isinstance(raw_scope, list):
        scope = [str(s) for s in raw_scope]
    else:
        scope = ["*"]

    try:
        priority = int(data.get("priority", 50))
    except (ValueError, TypeError):
        priority = 50

    immutable = bool(data.get("immutable", False))
    enabled = bool(data.get("enabled", True))

    metadata = RuleMetadata(
        name=name,
        description=description,
        scope=scope,
        priority=priority,
        immutable=immutable,
        enabled=enabled,
        file_path=path,
    )

    clean_body = normalize_content(body_content)
    return RulePackage(metadata=metadata, content=clean_body)


# --- Phase 2: RuleRegistry with Discovery & Override Deduplication ---

import threading


class RuleRegistry:
    """Thread-safe discovery and indexing registry for declarative rule packages.
    
    Walks search paths in deterministic precedence order (`config/rules/` > `.agents/rules/` > `rules/`),
    tracks file modification times (`mtime`) for in-memory caching, and enforces the Three-Tier
    Precedence Model and Immutable Invariant safety guarantees.
    """

    def __init__(self, search_paths: Optional[List[Path | str]] = None) -> None:
        self.search_paths: List[Path] = [Path(p) for p in (search_paths or [])]
        self._lock = threading.RLock()
        self._rules_by_path: Dict[Path, Tuple[float, RulePackage]] = {}  # path -> (mtime, pkg)
        self._indexed_rules: List[RulePackage] = []
        self._visited_inodes: Set[Tuple[int, int]] = set()

    def discover_rules(self, force_reload: bool = False) -> List[RulePackage]:
        """Scan configured search paths and index all valid markdown rule files.
        
        Thread-safe via threading.RLock. Detects symlink loops and caches parsed files by mtime.
        """
        with self._lock:
            if not force_reload and self._indexed_rules:
                # Fast-path: check if any mtimes changed
                has_changed = False
                for p, (last_mtime, _) in list(self._rules_by_path.items()):
                    if not p.exists() or p.stat().st_mtime != last_mtime:
                        has_changed = True
                        break
                if not has_changed:
                    return list(self._indexed_rules)

            self._rules_by_path.clear()
            self._visited_inodes.clear()
            all_discovered: List[RulePackage] = []

            for base_dir in self.search_paths:
                if not base_dir.is_dir():
                    continue

                # Walk directory deterministically
                for root_str, dirs, files in os.walk(base_dir, followlinks=False):
                    root_path = Path(root_str)
                    dirs.sort()  # Alphabetical directory traversal
                    files.sort()  # Alphabetical file traversal

                    for filename in files:
                        if not filename.endswith(".md"):
                            continue

                        file_path = root_path / filename

                        # Cycle detection via inode
                        try:
                            stat_res = file_path.stat()
                            inode_key = (stat_res.st_dev, stat_res.st_ino)
                            if inode_key in self._visited_inodes:
                                continue
                            self._visited_inodes.add(inode_key)
                        except (OSError, PermissionError):
                            continue

                        try:
                            pkg = parse_rule_file(file_path)
                            self._rules_by_path[file_path] = (stat_res.st_mtime, pkg)
                            all_discovered.append(pkg)
                        except (RuleParseError, OSError):
                            # Skip corrupted/unreadable files with log/ignore
                            continue

            self._indexed_rules = all_discovered
            return list(self._indexed_rules)

    def get_rules_for_scope(
        self,
        scopes: Optional[List[str]] = None,
        force_reload: bool = False,
    ) -> List[RulePackage]:
        """Retrieve and resolve rules matching the requested scopes.
        
        Resolution Algorithm:
        1. Filters active rules whose scope intersects with `scopes` or has wildcard `["*"]`.
        2. Enforces Three-Tier Precedence & Deduplication by `rule.metadata.name`:
           - When multiple rules share a name, the rule from higher-precedence `search_path` wins.
           - If an override rule attempts to override a rule where `immutable is True` or `priority < 20`,
             raises `ImmutableRuleOverrideError`.
           - If both rules are Tier 2, the downstream rule replaces the default.
        3. Deterministically sorts final resolved rules by `(priority ASC, name ASC, file_path ASC)`.
        """
        with self._lock:
            all_rules = self.discover_rules(force_reload=force_reload)

            normalized_scopes = set()
            if scopes:
                normalized_scopes = {s.strip().lower() for s in scopes if isinstance(s, str) and s.strip()}

            # Step 1: Filter enabled rules matching requested scope or global wildcard
            matching_rules: List[RulePackage] = []
            for pkg in all_rules:
                if not pkg.metadata.enabled:
                    continue
                rule_scopes = set(pkg.metadata.scope)
                if "*" in rule_scopes or bool(rule_scopes & normalized_scopes):
                    matching_rules.append(pkg)

            # Step 2: Deduplication by rule name respecting search path precedence
            # Search paths ordered from highest to lowest precedence
            path_precedence = {path.resolve(): idx for idx, path in enumerate(self.search_paths)}

            resolved_by_name: Dict[str, RulePackage] = {}

            for pkg in matching_rules:
                name = pkg.metadata.name
                if name not in resolved_by_name:
                    resolved_by_name[name] = pkg
                else:
                    existing = resolved_by_name[name]
                    # Check if existing or new is Tier 1
                    is_existing_tier1 = existing.metadata.immutable or existing.metadata.priority < 20
                    is_new_tier1 = pkg.metadata.immutable or pkg.metadata.priority < 20

                    if is_existing_tier1 or is_new_tier1:
                        # Attempting to override a Tier 1 rule or override with a Tier 1 rule is forbidden
                        target_rule = existing if is_existing_tier1 else pkg
                        violator_rule = pkg if is_existing_tier1 else existing
                        raise ImmutableRuleOverrideError(
                            f"Rule '{violator_rule.metadata.file_path}' attempts to override immutable Tier 1 invariant '{name}' defined in '{target_rule.metadata.file_path}'"
                        )

                    # Both are Tier 2 or Tier 3: higher precedence directory wins (lower index)
                    pkg_prec = 999
                    existing_prec = 999
                    if pkg.metadata.file_path:
                        for sp, idx in path_precedence.items():
                            try:
                                pkg.metadata.file_path.resolve().relative_to(sp)
                                pkg_prec = idx
                                break
                            except ValueError:
                                pass
                    if existing.metadata.file_path:
                        for sp, idx in path_precedence.items():
                            try:
                                existing.metadata.file_path.resolve().relative_to(sp)
                                existing_prec = idx
                                break
                            except ValueError:
                                pass

                    if pkg_prec < existing_prec:
                        resolved_by_name[name] = pkg  # Downstream higher-precedence wins

            # Step 3: Sort strictly by 3-tuple (priority ASC, name ASC, file_path ASC)
            final_rules = list(resolved_by_name.values())

            def sort_key(p: RulePackage) -> Tuple[int, str, str]:
                path_str = str(p.metadata.file_path.resolve()) if p.metadata.file_path else ""
                return (p.metadata.priority, p.metadata.name, path_str)

            final_rules.sort(key=sort_key)
            return final_rules


# --- Phase 3: RuleManager Prompt Compiler & Cache Guard ---

# Volatile token patterns: ISO-8601 datetimes, UUID4, unrendered template placeholders
_VOLATILE_DATETIME_PATTERN = re.compile(
    r"\b\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])(?:T|\s)\d{2}:\d{2}",
    re.ASCII
)
_VOLATILE_UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
    re.ASCII
)
_VOLATILE_TEMPLATE_PATTERN = re.compile(
    r"(\{\{.*?\}\}|\$\{.*?\})"
)


def assert_no_volatile_tokens(text: str, context_label: str = "prompt block") -> None:
    """Validate that text does not contain volatile dynamic values.
    
    Rejects ISO-8601 datetimes, UUIDs, and unrendered template tokens to prevent 0% KV cache hit rates.
    Permits version strings like '3.11-slim' or 'v1.2.3'.
    
    Raises:
        VolatilePromptPrefixError: If dynamic tokens are found.
    """
    dt_match = _VOLATILE_DATETIME_PATTERN.search(text)
    if dt_match:
        raise VolatilePromptPrefixError(
            f"Volatile datetime token '{dt_match.group(0)}' detected in {context_label}. Dynamic tokens must not be injected into static system prompt."
        )

    uuid_match = _VOLATILE_UUID_PATTERN.search(text)
    if uuid_match:
        raise VolatilePromptPrefixError(
            f"Volatile UUID token '{uuid_match.group(0)}' detected in {context_label}. Dynamic tokens must not be injected into static system prompt."
        )

    tmpl_match = _VOLATILE_TEMPLATE_PATTERN.search(text)
    if tmpl_match:
        raise VolatilePromptPrefixError(
            f"Unrendered template placeholder '{tmpl_match.group(0)}' detected in {context_label}. Unrendered template tokens invalidate prompt caching."
        )


class RuleManager:
    """Orchestrates declarative rule compilation and deterministic KV-cache prefix hydration.
    
    Ensures exact byte-for-byte reproducibility across agent turns and formats output
    for multi-provider support (OpenAI/Gemini strings or Anthropic ephemeral cache blocks).
    """

    def __init__(self, registry: RuleRegistry) -> None:
        self.registry = registry
        self._lock = threading.RLock()
        self._memoized_prefixes: Dict[Tuple[str, Tuple[str, ...], Tuple[str, ...]], CompiledPromptPrefix] = {}

    def compile_system_prefix(
        self,
        agent_role: str,
        scopes: Optional[List[str]] = None,
        extra_static_blocks: Optional[List[str]] = None,
        force_recompile: bool = False,
    ) -> CompiledPromptPrefix:
        """Compile a deterministic, immutable static system prompt prefix.
        
        Compilation Order (Invariant-to-Variant):
        1. Agent Role / Core Persona
        2. Tier 1 Immutable Invariants (Priority 0–19)
        3. Tier 2 Framework Guidelines (Priority 20–49)
        4. Tier 3 Contextual Overrides (Priority 50+)
        5. Extra Static Context Blocks (e.g. static schema DDL or few-shot exemplars)
        
        Memoizes compiled result keyed by (agent_role, sorted_scopes, extra_static_blocks)
        so compilation runs once per agent lifecycle.
        """
        scopes_tuple = tuple(sorted(s.strip().lower() for s in (scopes or []) if s.strip()))
        extra_blocks_tuple = tuple(extra_static_blocks or [])
        cache_key = (agent_role.strip(), scopes_tuple, extra_blocks_tuple)

        with self._lock:
            if not force_recompile and cache_key in self._memoized_prefixes:
                return self._memoized_prefixes[cache_key]

            # Validate agent role for volatile tokens
            assert_no_volatile_tokens(agent_role, context_label="agent_role")

            # Validate extra static blocks
            for idx, block in enumerate(extra_blocks_tuple):
                assert_no_volatile_tokens(block, context_label=f"extra_static_blocks[{idx}]")

            # Retrieve resolved rules for requested scopes
            resolved_rules = self.registry.get_rules_for_scope(scopes=list(scopes_tuple))

            # Validate rule bodies for volatile tokens
            for pkg in resolved_rules:
                assert_no_volatile_tokens(pkg.content, context_label=f"rule '{pkg.metadata.name}'")

            # Build deterministic prompt sections
            sections: List[str] = []

            # 1. Base Agent Persona
            if agent_role.strip():
                sections.append(normalize_content(agent_role.strip()))

            # 2. Rules in strict priority & name order
            for pkg in resolved_rules:
                header = f"### Rule: {pkg.metadata.name}"
                body = normalize_content(pkg.content)
                sections.append(f"{header}\n{body}")

            # 3. Extra static context (e.g. database schema DDL)
            for block in extra_blocks_tuple:
                if block.strip():
                    sections.append(normalize_content(block.strip()))

            # Combine with double newlines
            raw_compiled = "\n\n".join(sections)
            normalized_prompt = normalize_content(raw_compiled)

            # Calculate SHA-256 hash of UTF-8 encoded bytes for cache verification
            prompt_bytes = normalized_prompt.encode("utf-8")
            sha256_hash = hashlib.sha256(prompt_bytes).hexdigest()

            # Conservative heuristic token estimate (~4 characters per token)
            token_estimate = max(1, len(normalized_prompt) // 4)

            active_rule_names = [p.metadata.name for p in resolved_rules]

            # Construct Anthropic structured message blocks with cache_control on final static block
            cache_control_blocks = [
                {
                    "type": "text",
                    "text": normalized_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

            compiled = CompiledPromptPrefix(
                system_prompt=normalized_prompt,
                sha256_hash=sha256_hash,
                cached_token_estimate=token_estimate,
                active_rule_names=active_rule_names,
                cache_control_blocks=cache_control_blocks,
            )

            self._memoized_prefixes[cache_key] = compiled
            return compiled

    def format_for_provider(
        self,
        compiled: CompiledPromptPrefix,
        provider: str = "openai",
    ) -> Any:
        """Format compiled prompt for target LLM provider.
        
        For Anthropic: returns List[Dict] with cache_control on the static block.
        For OpenAI / Gemini / Default: returns compiled system prompt string.
        """
        provider_norm = provider.strip().lower()
        if "anthropic" in provider_norm or "claude" in provider_norm:
            return compiled.cache_control_blocks
        return compiled.system_prompt


