# Validation: CodeSanitizer

## Test Matrix

| Test Case | Component | Verification Criteria |
| :--- | :--- | :--- |
| **Pure Code Passthrough** | `CodeSanitizer.clean()` | Valid code with no fences or conversational fluff returns unchanged. |
| **Markdown Code Fence Extraction** | `CodeSanitizer.clean()` | Removes ```python ... ``` fences, returns only the inner code. |
| **Conversational Prefix/Suffix Stripping** | `CodeSanitizer.clean()` | Strips "Here is the code:" and "Hope this helps!". |
| **Indented Code Normalization** | `CodeSanitizer.clean()` | Code indented inside blockquotes or markdown lists is properly dedented. |
| **Extraction Strategy Selection** | `CodeSanitizer.sanitize()` | `LONGEST` picks largest block; `FIRST` picks first; `ALL` concatenates. |
| **Heredoc Wrapper Removal** | `CodeSanitizer.clean()` | Strips `cat << 'EOF' ... EOF` wrappers cleanly. |
| **Jupyter Magic Stripping** | `CodeSanitizer.clean()` | Comments out or removes `%matplotlib inline`, `%%writefile`. |
| **Python AST Syntax Validation** | `CodeSanitizer.sanitize()` | Returns `syntax_valid=True` for valid Python and `syntax_valid=False` with error details for broken syntax. |
| **Full Regression Suite** | Full Test Harness | All 113 existing project tests pass with zero regressions. |
