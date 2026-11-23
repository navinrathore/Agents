from pathlib import Path
import sys
import pytest

AGENTS_ROOT = str(Path(__file__).resolve().parent.parent)
if AGENTS_ROOT not in sys.path:
    sys.path.insert(0, AGENTS_ROOT)

from core.sanitizer import CodeSanitizer, ExtractionStrategy, SanitizationResult


# ==============================================================================
# 1. Basic Cleaning & Passthrough
# ==============================================================================

def test_clean_pure_code_passthrough():
    raw_code = "import os\n\ndef main():\n    return os.getcwd()\n"
    res = CodeSanitizer.clean(raw_code)
    assert res == raw_code.strip()


def test_clean_empty_and_whitespace():
    assert CodeSanitizer.clean("") == ""
    assert CodeSanitizer.clean("   \n\n  ") == ""
    assert CodeSanitizer.clean(None) == ""


# ==============================================================================
# 2. Markdown Fence Stripping
# ==============================================================================

def test_clean_fenced_python():
    llm_output = (
        "Here is the code you requested:\n"
        "```python\n"
        "import pandas as pd\n"
        "df = pd.DataFrame({'a': [1, 2, 3]})\n"
        "print(df)\n"
        "```\n"
        "Hope this helps!"
    )
    res = CodeSanitizer.clean(llm_output)
    expected = (
        "import pandas as pd\n"
        "df = pd.DataFrame({'a': [1, 2, 3]})\n"
        "print(df)"
    )
    assert res == expected


def test_clean_fenced_bash():
    llm_output = (
        "Run the following shell script:\n"
        "```bash\n"
        "mkdir -p /tmp/build\n"
        "cd /tmp/build && git status\n"
        "```"
    )
    res = CodeSanitizer.clean(llm_output, language="bash")
    assert res == "mkdir -p /tmp/build\ncd /tmp/build && git status"


def test_clean_four_backtick_fence():
    llm_output = (
        "````python\n"
        "# Code containing 3 backticks in comments or docstrings\n"
        "doc = '```markdown```'\n"
        "````"
    )
    res = CodeSanitizer.clean(llm_output)
    assert res == "# Code containing 3 backticks in comments or docstrings\ndoc = '```markdown```'"


# ==============================================================================
# 3. Conversational Stripping (Without Fences)
# ==============================================================================

def test_clean_conversational_prefixes_and_suffixes():
    llm_output = (
        "Sure thing! Below is the python script to achieve this:\n"
        "import sys\n"
        "print(sys.version)\n"
        "\n"
        "Let me know if you need anything else!"
    )
    res = CodeSanitizer.clean(llm_output)
    assert res == "import sys\nprint(sys.version)"


# ==============================================================================
# 4. Shell Wrappers & Jupyter Magics
# ==============================================================================

def test_clean_heredoc_wrapper():
    llm_output = (
        "cat << 'EOF'\n"
        "from pathlib import Path\n"
        "print(Path.cwd())\n"
        "EOF"
    )
    res = CodeSanitizer.clean(llm_output)
    assert res == "from pathlib import Path\nprint(Path.cwd())"


def test_clean_python_c_command():
    llm_output = 'python3 -c "import math; print(math.sqrt(16))"'
    res = CodeSanitizer.clean(llm_output)
    assert res == "import math; print(math.sqrt(16))"


def test_clean_jupyter_magics():
    llm_output = (
        "```python\n"
        "%matplotlib inline\n"
        "%%time\n"
        "import numpy as np\n"
        "arr = np.zeros(10)\n"
        "```"
    )
    res = CodeSanitizer.clean(llm_output)
    assert res == "import numpy as np\narr = np.zeros(10)"


# ==============================================================================
# 5. Indentation Normalization
# ==============================================================================

def test_clean_indented_inside_bullet():
    # LLM indented code by 4 spaces because it was in a markdown list
    llm_output = (
        "    def calculate(x, y):\n"
        "        return x * y + 42\n"
    )
    res = CodeSanitizer.clean(llm_output)
    expected = (
        "def calculate(x, y):\n"
        "    return x * y + 42"
    )
    assert res == expected


# ==============================================================================
# 6. Extraction Strategies (Multiple Blocks)
# ==============================================================================

def test_multiple_blocks_longest_strategy():
    llm_output = (
        "First a quick test:\n"
        "```python\n"
        "x = 1\n"
        "```\n"
        "And now the full solution:\n"
        "```python\n"
        "def comprehensive_solution(items):\n"
        "    return [item.strip() for item in items if item]\n"
        "```"
    )
    res = CodeSanitizer.clean(llm_output, strategy=ExtractionStrategy.LONGEST)
    assert "comprehensive_solution" in res
    assert "x = 1" not in res


def test_multiple_blocks_first_and_last_strategy():
    llm_output = (
        "```python\n"
        "# Block 1\n"
        "val = 'first'\n"
        "```\n"
        "```python\n"
        "# Block 2\n"
        "val = 'second'\n"
        "```"
    )
    res_first = CodeSanitizer.clean(llm_output, strategy=ExtractionStrategy.FIRST)
    assert "first" in res_first

    res_last = CodeSanitizer.clean(llm_output, strategy=ExtractionStrategy.LAST)
    assert "second" in res_last


def test_multiple_blocks_all_strategy():
    llm_output = (
        "```python\n"
        "part_1 = 10\n"
        "```\n"
        "And second part:\n"
        "```python\n"
        "part_2 = 20\n"
        "```"
    )
    res_all = CodeSanitizer.clean(llm_output, strategy=ExtractionStrategy.ALL)
    assert "part_1 = 10" in res_all
    assert "part_2 = 20" in res_all


# ==============================================================================
# 7. AST Syntax Validation
# ==============================================================================

def test_syntax_validation_valid():
    valid_py = "```python\ndef greet(name: str) -> str:\n    return f'Hello {name}'\n```"
    res = CodeSanitizer.sanitize(valid_py, validate_syntax=True)
    assert res.syntax_valid is True
    assert res.syntax_error is None


def test_syntax_validation_invalid():
    invalid_py = "```python\ndef broken_function(:\n    pass\n```"
    res = CodeSanitizer.sanitize(invalid_py, validate_syntax=True)
    assert res.syntax_valid is False
    assert "SyntaxError" in (res.syntax_error or "")
