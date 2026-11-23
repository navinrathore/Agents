# Requirements: CodeSanitizer

## Overview
When LLMs generate code for tool execution (e.g. `execute_python`, `execute_bash`, `execute_sql`), models frequently pollute the executable payload with:
1. Markdown code block fences (````python ... ````, ````bash ... ````, or untyped ```` ... ````).
2. Conversational conversational prefixes ("Here is the solution:", "Sure, I can help with that:").
3. Trailing conversational sign-offs ("Hope this helps!", "Let me know if you need further adjustments.").
4. Interactive shell or notebook wrappers (`cat << 'EOF' ... EOF`, `python -c "..."`, `%writefile`).
5. Broken indentation caused by the LLM formatting the code inside bullet points or blockquotes.

`CodeSanitizer` is a deterministic input preparation and cleaning utility that extracts, de-indents, sanitizes, and verifies raw code blocks prior to execution by tools.

---

## 1. Scope

### In-Scope
- **Markdown Extraction**:
  - Robust regex and delimiter scanner for backtick fences (````py````, ````python````, ````bash````, ````sh````, ````sql````, or bare ````).
  - Configurable block selection strategy when multiple code blocks are generated:
    - `FIRST`: Selects first code block.
    - `LAST`: Selects last code block.
    - `LONGEST` *(Default)*: Selects the code block with the most content (common in LLM reasoning).
    - `ALL`: Concatenates all code blocks.
- **Conversational & Wrapper Stripping**:
  - Automatically strips conversational opening and closing text if no code blocks are present or if code is surrounded by chat text.
  - Strips shell wrapper heredocs (`cat << 'EOF' ... EOF`) and command invocation wrappers (`python -c "..."` or `python -c '...'`).
  - Strips Jupyter/IPython magic commands (`%matplotlib inline`, `%%writefile ...`).
- **Indentation & Formatting Normalization**:
  - Strips common leading whitespace indentation (`textwrap.dedent`) if the entire code block was indented inside a bullet or quote.
  - Normalizes line endings (`\r\n` -> `\n`) and trailing whitespace.
- **Optional Syntax Verification**:
  - Python AST syntax validation (`validate_python_syntax: bool = False`): checks whether extracted Python code is syntactically valid with `ast.parse()` before execution, returning clear syntax error details instead of crashing the subprocess.
- **Standalone and Dispatcher Middleware Usable**:
  - Can be used directly as a utility (`CodeSanitizer.clean(...)`) or as a wrapper / middleware for code tools.

### Out-of-Scope
- Static type checking (mypy/pyright); runtime execution validates types.
- Semantic code correctness auditing (that is handled by test suites and judge models).
