"""
CodeSanitizer Subsystem.

Deterministic code extraction, cleaning, and sanitization utility for agentic tools.
Strips markdown code fences, conversational fluff, shell heredocs, and Jupyter magics,
normalizes indentation, and provides optional Python AST syntax validation.
"""

import ast
from dataclasses import dataclass
from enum import Enum
import re
import textwrap
from typing import List, Optional, Tuple


class ExtractionStrategy(str, Enum):
    """Strategy for selecting code blocks when multiple blocks are present in LLM output."""
    LONGEST = "longest"  # Default: Pick the largest code block
    FIRST = "first"      # Pick the first code block
    LAST = "last"        # Pick the last code block
    ALL = "all"          # Concatenate all code blocks


@dataclass
class SanitizationResult:
    """Outcome of the code sanitization process."""
    code: str
    raw_input: str
    is_modified: bool
    detected_language: Optional[str] = None
    syntax_valid: Optional[bool] = None
    syntax_error: Optional[str] = None

    def __str__(self) -> str:
        return self.code


class CodeSanitizer:
    """
    Robust code sanitization engine for cleaning LLM responses prior to execution.
    """

    FENCE_PATTERN = re.compile(
        r"(?P<ticks>`{3,})([a-zA-Z0-9_\-\+]*)\s*\n?(.*?)(?P=ticks)",
        re.DOTALL
    )

    CONVERSATIONAL_PREFIXES = [
        re.compile(r"^(?:[Ss]ure(?: thing)?[!.,]?|[Cc]ertainly[!.,]?|[Oo]f course[!.,]?)\s*", re.MULTILINE),
        re.compile(r"^(?:[Hh]ere(?: is|'s)|[Bb]elow is) (?:the |your )?(?:python |bash |sql |shell )?(?:code|script|solution|query)[^:\n]*:?\s*", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^(?:To (?:solve|run|execute|achieve) this[^:\n]*:?)\s*", re.IGNORECASE | re.MULTILINE),
    ]

    CONVERSATIONAL_SUFFIXES = [
        re.compile(r"\n\s*(?:[Hh]ope this helps[!.,]?|[Ff]eel free to ask[^\n]*|[Ll]et me know if (?:you (?:have|need)|there)[^\n]*)\s*$", re.IGNORECASE),
        re.compile(r"\n\s*(?:[Tt]his (?:script|code|solution) (?:will|should)[^\n]*)\s*$", re.IGNORECASE),
    ]

    HEREDOC_PATTERN = re.compile(
        r"cat\s+<<\s*['\"]?([A-Za-z0-9_]+)['\"]?\s*\n(.*?)\n\s*\1\s*$",
        re.DOTALL | re.MULTILINE
    )

    PYTHON_C_PATTERN = re.compile(
        r"python[3]?\s+-c\s+(['\"])(.*?)\1\s*$",
        re.DOTALL
    )

    JUPYTER_MAGIC_PATTERN = re.compile(
        r"^(?:%%?[a-zA-Z0-9_\-]+[^\n]*\n?)",
        re.MULTILINE
    )

    @classmethod
    def extract_fenced_blocks(cls, text: str) -> List[Tuple[Optional[str], str]]:
        """
        Finds all markdown fenced code blocks in the text.
        Returns list of (language_tag, code_content).
        """
        matches = cls.FENCE_PATTERN.finditer(text)
        results = []
        for m in matches:
            lang = m.group(2).strip().lower() or None
            content = m.group(3)
            results.append((lang, content))
        return results

    @classmethod
    def strip_conversational_text(cls, text: str) -> str:
        """Strips leading and trailing conversational sentences."""
        cleaned = text.strip()
        for prefix_pat in cls.CONVERSATIONAL_PREFIXES:
            cleaned = prefix_pat.sub("", cleaned).strip()
        for suffix_pat in cls.CONVERSATIONAL_SUFFIXES:
            cleaned = suffix_pat.sub("", cleaned).strip()
        return cleaned

    @classmethod
    def strip_shell_wrappers(cls, text: str) -> str:
        """Strips shell wrappers like heredocs or python -c '...'."""
        cleaned = text.strip()

        # Check for heredoc
        heredoc_match = cls.HEREDOC_PATTERN.search(cleaned)
        if heredoc_match:
            return heredoc_match.group(2)

        # Check for python -c "..."
        py_c_match = cls.PYTHON_C_PATTERN.search(cleaned)
        if py_c_match:
            return py_c_match.group(2)

        return cleaned

    @classmethod
    def strip_jupyter_magics(cls, text: str) -> str:
        """Removes or comments out Jupyter/IPython magic commands."""
        return cls.JUPYTER_MAGIC_PATTERN.sub("", text)

    @classmethod
    def normalize_indentation(cls, text: str) -> str:
        """Normalizes line endings and dedents common leading whitespace."""
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        return textwrap.dedent(normalized).strip()

    @classmethod
    def validate_python_syntax(cls, code: str) -> Tuple[bool, Optional[str]]:
        """
        Checks whether the code string is valid Python syntax using ast.parse().
        Returns (is_valid, error_message).
        """
        if not code.strip():
            return True, None
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            err = f"SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}"
            if e.text:
                err += f"\n  --> {e.text.strip()}"
            return False, err
        except Exception as e:
            return False, f"Syntax validation error: {str(e)}"

    @classmethod
    def sanitize(
        cls,
        text: str,
        language: str = "python",
        strategy: ExtractionStrategy = ExtractionStrategy.LONGEST,
        validate_syntax: bool = False,
    ) -> SanitizationResult:
        """
        Full sanitization pipeline:
        1. Extract fenced code blocks if present (using configured strategy).
        2. Fallback to raw text with conversational stripping if no fences.
        3. Strip shell wrappers (heredocs, python -c).
        4. Strip Jupyter magics.
        5. Normalize indentation and line endings.
        6. Optional Python AST syntax validation.
        """
        if not text or not isinstance(text, str):
            return SanitizationResult(
                code="",
                raw_input=text or "",
                is_modified=False,
                detected_language=None,
                syntax_valid=True if validate_syntax else None,
            )

        raw_input = text
        fenced_blocks = cls.extract_fenced_blocks(text)
        detected_lang: Optional[str] = None
        extracted_code: str = ""

        if fenced_blocks:
            # Filter by requested language if specified
            lang_match = [b for b in fenced_blocks if b[0] and (language in b[0] or b[0] in language)]
            candidate_blocks = lang_match if lang_match else fenced_blocks

            if strategy == ExtractionStrategy.FIRST:
                detected_lang, extracted_code = candidate_blocks[0]
            elif strategy == ExtractionStrategy.LAST:
                detected_lang, extracted_code = candidate_blocks[-1]
            elif strategy == ExtractionStrategy.ALL:
                detected_lang = candidate_blocks[0][0]
                extracted_code = "\n\n".join(b[1] for b in candidate_blocks)
            else:  # LONGEST (default)
                detected_lang, extracted_code = max(candidate_blocks, key=lambda b: len(b[1]))
        else:
            # No markdown fences found; dedent first to preserve relative indentation across lines
            dedented = cls.normalize_indentation(text)
            extracted_code = cls.strip_conversational_text(dedented)

        # Apply secondary sanitizers
        extracted_code = cls.strip_shell_wrappers(extracted_code)
        extracted_code = cls.strip_jupyter_magics(extracted_code)
        cleaned_code = cls.normalize_indentation(extracted_code)

        # Check syntax if requested
        syntax_valid: Optional[bool] = None
        syntax_error: Optional[str] = None
        if validate_syntax and (language.lower() in ("python", "py")):
            syntax_valid, syntax_error = cls.validate_python_syntax(cleaned_code)

        is_modified = (cleaned_code != raw_input)

        return SanitizationResult(
            code=cleaned_code,
            raw_input=raw_input,
            is_modified=is_modified,
            detected_language=detected_lang,
            syntax_valid=syntax_valid,
            syntax_error=syntax_error,
        )

    @classmethod
    def clean(
        cls,
        text: str,
        language: str = "python",
        strategy: ExtractionStrategy = ExtractionStrategy.LONGEST,
        validate_syntax: bool = False,
    ) -> str:
        """
        Fast convenience helper: returns pure sanitized code string directly.
        """
        res = cls.sanitize(
            text=text,
            language=language,
            strategy=strategy,
            validate_syntax=validate_syntax,
        )
        return res.code
