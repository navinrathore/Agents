from collections import Counter, deque
import hashlib
import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Type, Union

try:
    from pydantic import BaseModel, ValidationError
    PYDANTIC_AVAILABLE = True
except ImportError:
    BaseModel = Any
    ValidationError = Exception
    PYDANTIC_AVAILABLE = False


class ExecutionTimer:
    """
    A context manager to time the execution of code blocks.
    Only prints the duration if verbose is set to True.
    """
    def __init__(self, name="Execution", verbose=False):
        self.name = name
        self.verbose = verbose
        self.start_time = None
        self.duration = 0.0

    def __enter__(self):
        self.start_time = time.time()
        if self.verbose:
            print(f"\n⏱️  [{self.name}] Timer started...")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duration = time.time() - self.start_time
        if self.verbose:
            print(f"⏱️  [{self.name}] Completed in {self.duration:.2f} seconds.\n")


class RepetitionDetector:
    """
    A robust detector to identify when an agent repeats states, errors, or tool outputs.
    Supports both consecutive repetition tracking (A -> A -> A) and sliding-window
    non-consecutive cyclic loop detection (A -> B -> A -> B -> A) via SHA-256 hashing.
    """
    def __init__(
        self,
        threshold: int = 3,
        window_size: int = 10,
        consecutive_only: bool = False,
    ):
        self.threshold = max(2, threshold)
        self.window_size = max(self.threshold, window_size)
        self.consecutive_only = consecutive_only
        self.history: deque[str] = deque(maxlen=self.window_size)
        self.hash_counts: Counter[str] = Counter()
        self.last_item: Optional[str] = None
        self.consecutive_count: int = 0

    def _hash_item(self, item: str) -> str:
        """Computes a compact SHA-256 digest of the item string."""
        return hashlib.sha256(item.encode("utf-8")).hexdigest()[:16]

    def check(self, item: str) -> bool:
        """
        Records the item and returns True if repetition threshold is reached.
        - In consecutive_only mode: returns True if repeated `threshold` times consecutively.
        - In sliding-window mode (default): returns True if either:
          a) repeated `threshold` times consecutively, OR
          b) appears `threshold` times within the sliding window of `window_size`.
        """
        if not item or not isinstance(item, str):
            return False

        item_str = item.strip()
        if not item_str:
            return False

        # 1. Check consecutive repetition
        if item_str == self.last_item:
            self.consecutive_count += 1
        else:
            self.consecutive_count = 1
            self.last_item = item_str

        if self.consecutive_count >= self.threshold:
            return True

        if self.consecutive_only:
            return False

        # 2. Check sliding-window non-consecutive repetition
        item_hash = self._hash_item(item_str)

        # If window is at capacity, remove the oldest element from counter before appending
        if len(self.history) == self.window_size:
            oldest_hash = self.history[0]
            self.hash_counts[oldest_hash] -= 1
            if self.hash_counts[oldest_hash] <= 0:
                del self.hash_counts[oldest_hash]

        self.history.append(item_hash)
        self.hash_counts[item_hash] += 1

        return self.hash_counts[item_hash] >= self.threshold

    def get_count(self, item: str) -> int:
        """Returns the number of times this item appears in the active window."""
        item_hash = self._hash_item(item.strip())
        return self.hash_counts.get(item_hash, 0)

    def reset(self) -> None:
        """Resets the history window and consecutive counter."""
        self.history.clear()
        self.hash_counts.clear()
        self.last_item = None
        self.consecutive_count = 0


class JsonExtractor:
    """
    Robust JSON extractor for LLM output text.
    Extracts raw JSON objects or lists from conversational responses,
    markdown code blocks (```json ... ```), and handles common formatting glitches.
    """
    @staticmethod
    def extract(text: str) -> Union[dict, list]:
        if not text or not isinstance(text, str):
            raise ValueError("Input text must be a non-empty string.")

        text_str = text.strip()

        # Tier 1: Direct JSON parsing
        try:
            return json.loads(text_str)
        except json.JSONDecodeError:
            pass

        # Tier 2: Extract from Markdown code fences (```json ... ``` or ``` ... ```)
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text_str, re.IGNORECASE)
        if fence_match:
            candidate = fence_match.group(1).strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
            # Try cleaning candidate (stripping trailing commas)
            cleaned_candidate = JsonExtractor._sanitize_json_string(candidate)
            try:
                return json.loads(cleaned_candidate)
            except json.JSONDecodeError:
                pass

        # Tier 3: Extract outermost JSON object {...} or array [...] via regex
        obj_match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text_str)
        if obj_match:
            candidate = obj_match.group(1).strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
            cleaned_candidate = JsonExtractor._sanitize_json_string(candidate)
            try:
                return json.loads(cleaned_candidate)
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Failed to extract valid JSON from LLM output. Raw response fragment: {text_str[:150]}...")

    @staticmethod
    def _sanitize_json_string(s: str) -> str:
        """Removes trailing commas before closing braces/brackets."""
        return re.sub(r",\s*([\}\]])", r"\1", s)


class SchemaValidator:
    """
    Dual-mode validator supporting both Pydantic BaseModel validation
    and raw dictionary/key/type validation when Pydantic models are not present.
    """
    @staticmethod
    def validate(
        data: Union[dict, list],
        pydantic_model: Optional[Type[BaseModel]] = None,
        required_keys: Optional[List[str]] = None,
        expected_types: Optional[Dict[str, type]] = None
    ) -> Tuple[bool, Optional[Any], Optional[str]]:
        """
        Validates parsed data.
        Returns: (success: bool, validated_object_or_dict, error_message: str | None)
        """
        # Mode 1: Pydantic Model Validation (if provided and available)
        if pydantic_model is not None:
            if not PYDANTIC_AVAILABLE:
                return False, None, "Pydantic is not installed in the python environment."
            
            try:
                if isinstance(data, dict):
                    validated_obj = pydantic_model.model_validate(data)
                    return True, validated_obj, None
                elif isinstance(data, list):
                    # Handle list of items or RootModel validation if model supports it
                    try:
                        from pydantic import TypeAdapter
                        adapter = TypeAdapter(List[pydantic_model])
                        validated_obj = adapter.validate_python(data)
                        return True, validated_obj, None
                    except Exception:
                        return False, None, f"Expected dict for Pydantic model validation, got list."
                else:
                    return False, None, f"Expected dict for Pydantic model validation, got {type(data).__name__}."
            except ValidationError as ve:
                errors = []
                for err in ve.errors():
                    loc = " -> ".join(str(l) for l in err.get("loc", []))
                    msg = err.get("msg", "")
                    errors.append(f"Field '{loc}': {msg}")
                err_str = "; ".join(errors)
                return False, None, f"Pydantic Validation Error: {err_str}"
            except Exception as e:
                return False, None, f"Pydantic validation failed: {str(e)}"

        # Mode 2: Raw Dict / Schema Validation (Fallback when Pydantic model is not present)
        if isinstance(data, dict):
            if required_keys:
                missing = [k for k in required_keys if k not in data]
                if missing:
                    return False, None, f"Missing required JSON keys: {', '.join(missing)}"

            if expected_types:
                type_errors = []
                for k, expected_type in expected_types.items():
                    if k in data and not isinstance(data[k], expected_type):
                        actual_type = type(data[k]).__name__
                        type_errors.append(f"Key '{k}' expected type {expected_type.__name__}, got {actual_type}")
                if type_errors:
                    return False, None, f"JSON type mismatch: {'; '.join(type_errors)}"

            return True, data, None

        elif isinstance(data, list):
            return True, data, None

        return False, None, f"Unsupported data type for validation: {type(data).__name__}"


class StructuredOutputParser:
    """
    High-level convenience parser combining JsonExtractor and SchemaValidator.
    Supports both Pydantic models and raw dict/type validation.
    """
    @staticmethod
    def parse(
        text: str,
        response_model: Optional[Type[BaseModel]] = None,
        required_keys: Optional[List[str]] = None,
        expected_types: Optional[Dict[str, type]] = None
    ) -> Tuple[bool, Optional[Any], Optional[str]]:
        """
        Parses raw text into structured data with validation.
        Returns: (success: bool, parsed_data_or_pydantic_model, error_message: str | None)
        """
        try:
            extracted_json = JsonExtractor.extract(text)
        except ValueError as ve:
            return False, None, str(ve)

        return SchemaValidator.validate(
            data=extracted_json,
            pydantic_model=response_model,
            required_keys=required_keys,
            expected_types=expected_types
        )
