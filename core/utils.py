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
    A generic detector to identify when an agent repeats the exact same state or output.
    This can be used to prevent infinite loops when an LLM repeats the same error.
    """
    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        self.last_item = None
        self.count = 0

    def check(self, item: str) -> bool:
        """
        Returns True if the item has been repeated `threshold` times consecutively.
        """
        if not item:
            self.reset()
            return False

        if item == self.last_item:
            self.count += 1
        else:
            self.count = 1
            self.last_item = item
            
        return self.count >= self.threshold

    def reset(self):
        """Resets the tracker."""
        self.count = 0
        self.last_item = None


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
