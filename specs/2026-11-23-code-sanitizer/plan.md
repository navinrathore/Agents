# Plan: CodeSanitizer

## Architecture & Processing Flow

```
                      Raw LLM Text Payload
                                │
                                ▼
                       ┌─────────────────┐
                       │  CodeSanitizer  │
                       └────────┬────────┘
                                │
                      Are code fences (```) present?
                               / \
                            YES   NO
                            │       │
                            ▼       ▼
                    Extract Fenced    Strip Conversational
                    Blocks (Strategy: Openers/Closers & 
                    LONGEST/FIRST)    Heredocs
                            │       │
                            └───────┬───────┘
                                    │
                                    ▼
                    Normalize Indentation & Line Endings
                            (textwrap.dedent)
                                    │
                                    ▼
                    Strip Shell / Jupyter Magics
                            (cat << EOF, %)
                                    │
                                    ▼
                    Optional Syntax Validation
                          (ast.parse for Python)
                                    │
                                    ▼
                      Return Pure Cleaned Code
```

---

## Phased Implementation Plan

### Phase 1: Core Engine (`projects/Agents/core/sanitizer.py`)
1. **`ExtractionStrategy` Enum**: `FIRST`, `LAST`, `LONGEST`, `ALL`.
2. **`SanitizationResult` Data Structure**:
   - `code: str`: The cleaned, ready-to-run code.
   - `raw_input: str`: Original raw input.
   - `is_modified: bool`: Whether any cleaning or stripping occurred.
   - `detected_language: Optional[str]`: Language tag from markdown fence (e.g. `python`, `sql`, `bash`).
   - `syntax_valid: Optional[bool]`: Status if syntax check was performed.
   - `syntax_error: Optional[str]`: Syntax error message if validation failed.
3. **`CodeSanitizer`**:
   - Static and instance methods for extraction and cleaning.
   - Methods:
     - `extract_code_blocks(text, strategy, language)`
     - `strip_heredoc(text)`
     - `strip_magics(text)`
     - `validate_syntax(code, language)`
     - `sanitize(text, language="python", strategy=ExtractionStrategy.LONGEST, validate_syntax=False) -> SanitizationResult`
     - `clean(text, language="python", validate_syntax=False) -> str` (fast one-line helper).

### Phase 2: Integration & Exports
1. Export `CodeSanitizer`, `ExtractionStrategy`, `SanitizationResult` in `projects/Agents/core/__init__.py`.
2. Update `core/utils.py` if needed for backward-compatibility aliases.

### Phase 3: Comprehensive Test Suite (`projects/Agents/tests/test_sanitizer.py`)
1. Markdown fence extraction (python, bash, sql, untyped).
2. Conversational preface and postfix stripping.
3. Heredoc (`cat << EOF ... EOF`) and `python -c` wrapper stripping.
4. Block selection strategies (`FIRST`, `LAST`, `LONGEST`, `ALL`).
5. Indentation normalization (dedent).
6. Jupyter magic command stripping (`%matplotlib`, `%%time`).
7. Python AST syntax validation (valid code vs invalid syntax reporting).
