"""
OutputGuard and Payload Offloader (Data Pointer) Subsystem.

Combines smart head/tail tool output truncation with content-addressed,
lossless payload offloading. Protects the LLM context window from huge outputs
(e.g., large SQL queries, log files, web scrape text, API payloads) while ensuring
complete data preservation for selective querying.
"""

from abc import ABC, abstractmethod
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from pydantic import BaseModel, Field
    PYDANTIC_AVAILABLE = True
except ImportError:
    from dataclasses import dataclass, field
    PYDANTIC_AVAILABLE = False


class OutputGuardMode(str, Enum):
    """Operational mode for tool output management."""
    OFFLOAD_AND_TRUNCATE = "offload_and_truncate"  # Offload lossless to store + return DataPointer
    TRUNCATE_ONLY = "truncate_only"                # Memory-only head/tail truncation (no disk write)
    PASSTHROUGH = "passthrough"                    # No truncation or offloading


if PYDANTIC_AVAILABLE:
    class DataPointer(BaseModel):
        """
        Strongly-typed Data Pointer (Claim Check) contract.
        Represents an offloaded payload stored outside the LLM context.
        """
        pointer_id: str
        storage_uri: str
        media_type: str = "text/plain"
        size_bytes: int
        estimated_tokens: int
        total_lines: int
        preview_snippet: str
        omitted_lines: int
        omitted_chars: int
        head_lines: int
        tail_lines: int
        is_offloaded: bool = True
        metadata: Dict[str, Any] = Field(default_factory=dict)

        def to_llm_string(self) -> str:
            """Formats the Data Pointer into a structured context-friendly string for the LLM."""
            banner = [
                f"[TOOL OUTPUT EXCEEDED INLINE THRESHOLD: {self.size_bytes:,} bytes / ~{self.estimated_tokens:,} tokens]",
                f"Artifact ID: {self.pointer_id}",
                f"Storage URI: {self.storage_uri}",
                f"Total Lines: {self.total_lines:,} (Omitted: {self.omitted_lines:,} lines, ~{self.omitted_chars:,} characters)",
                "Action Required: Full content is preserved losslessly. Query or paginate via pointer tools (e.g. read_pointer_slice, grep_pointer).",
                "",
                "--- HEAD & TAIL PREVIEW ---",
                self.preview_snippet,
                "--- END PREVIEW ---",
            ]
            return "\n".join(banner)
else:
    @dataclass
    class DataPointer:
        pointer_id: str
        storage_uri: str
        size_bytes: int
        estimated_tokens: int
        total_lines: int
        preview_snippet: str
        omitted_lines: int
        omitted_chars: int
        head_lines: int
        tail_lines: int
        media_type: str = "text/plain"
        is_offloaded: bool = True
        metadata: Dict[str, Any] = field(default_factory=dict)

        def to_llm_string(self) -> str:
            banner = [
                f"[TOOL OUTPUT EXCEEDED INLINE THRESHOLD: {self.size_bytes:,} bytes / ~{self.estimated_tokens:,} tokens]",
                f"Artifact ID: {self.pointer_id}",
                f"Storage URI: {self.storage_uri}",
                f"Total Lines: {self.total_lines:,} (Omitted: {self.omitted_lines:,} lines, ~{self.omitted_chars:,} characters)",
                "Action Required: Full content is preserved losslessly. Query or paginate via pointer tools (e.g. read_pointer_slice, grep_pointer).",
                "",
                "--- HEAD & TAIL PREVIEW ---",
                self.preview_snippet,
                "--- END PREVIEW ---",
            ]
            return "\n".join(banner)

        def dict(self) -> Dict[str, Any]:
            from dataclasses import asdict
            return asdict(self)

        def model_dump(self) -> Dict[str, Any]:
            return self.dict()


class TruncationResult:
    """Holds the result of a head/tail excerpt operation."""
    def __init__(
        self,
        text: str,
        omitted_chars: int,
        omitted_lines: int,
        total_lines: int,
        head_lines_count: int,
        tail_lines_count: int,
        is_truncated: bool,
    ):
        self.text = text
        self.omitted_chars = omitted_chars
        self.omitted_lines = omitted_lines
        self.total_lines = total_lines
        self.head_lines_count = head_lines_count
        self.tail_lines_count = tail_lines_count
        self.is_truncated = is_truncated


class ToolOutputTruncator:
    """
    In-memory smart truncator that preserves the head (initial context) and tail
    (final outcome/errors) of oversized text outputs while omitting the middle.
    """

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Approximates token count (standard ~4 chars per token rule of thumb)."""
        return max(1, len(text) // 4)

    @classmethod
    def truncate(
        cls,
        text: str,
        max_chars: int = 8000,
        head_lines: int = 15,
        tail_lines: int = 10,
    ) -> TruncationResult:
        """
        Truncates text by preserving head and tail lines if text exceeds max_chars.
        """
        if not text or len(text) <= max_chars:
            lines = text.splitlines() if text else []
            return TruncationResult(
                text=text,
                omitted_chars=0,
                omitted_lines=0,
                total_lines=len(lines),
                head_lines_count=len(lines),
                tail_lines_count=0,
                is_truncated=False,
            )

        lines = text.splitlines()
        total_lines = len(lines)

        # Case 1: Single line or very few lines but massive characters
        if total_lines <= (head_lines + tail_lines):
            half = max_chars // 2
            head_part = text[:half]
            tail_part = text[-half:]
            omitted_chars = len(text) - (len(head_part) + len(tail_part))
            preview = (
                f"{head_part}\n"
                f"... [OMITTED {omitted_chars:,} characters] ...\n"
                f"{tail_part}"
            )
            return TruncationResult(
                text=preview,
                omitted_chars=omitted_chars,
                omitted_lines=0,
                total_lines=total_lines,
                head_lines_count=total_lines,
                tail_lines_count=0,
                is_truncated=True,
            )

        # Case 2: Multi-line text
        head_slice = lines[:head_lines]
        tail_slice = lines[-tail_lines:] if tail_lines > 0 else []
        omitted_line_count = total_lines - (len(head_slice) + len(tail_slice))

        head_text = "\n".join(head_slice)
        tail_text = "\n".join(tail_slice)

        # Check if head + tail combined still exceeds max_chars
        combined_chars = len(head_text) + len(tail_text)
        if combined_chars > max_chars:
            # Fall back to character slicing
            half = max_chars // 2
            head_text = head_text[:half]
            tail_text = tail_text[-half:]

        omitted_chars = len(text) - (len(head_text) + len(tail_text))

        preview_lines = []
        preview_lines.append(head_text)
        preview_lines.append(
            f"\n... [OMITTED {omitted_line_count:,} lines (~{omitted_chars:,} characters)] ...\n"
        )
        if tail_text:
            preview_lines.append(tail_text)

        preview = "\n".join(preview_lines)

        return TruncationResult(
            text=preview,
            omitted_chars=omitted_chars,
            omitted_lines=omitted_line_count,
            total_lines=total_lines,
            head_lines_count=len(head_slice),
            tail_lines_count=len(tail_slice),
            is_truncated=True,
        )


class BasePayloadStore(ABC):
    """Abstract interface for payload storage backends (Local Disk, Redis, S3, etc.)."""

    @abstractmethod
    def store(
        self,
        payload: str,
        media_type: str = "text/plain",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
        """
        Stores raw payload.
        Returns tuple of (pointer_id, storage_uri).
        """
        pass

    @abstractmethod
    def retrieve(self, pointer_id: str) -> Optional[str]:
        """Retrieves raw payload by pointer_id. Returns None if missing."""
        pass

    @abstractmethod
    def exists(self, pointer_id: str) -> bool:
        """Checks if a payload exists for pointer_id."""
        pass

    @abstractmethod
    def delete(self, pointer_id: str) -> bool:
        """Deletes payload if it exists. Returns True if deleted."""
        pass


class LocalDiskPayloadStore(BasePayloadStore):
    """
    Content-addressed local filesystem payload store.
    Stores payloads indexed by SHA-256 hash to ensure zero duplication.
    """

    def __init__(self, storage_dir: Union[str, Path] = "vault/pointers"):
        self.storage_dir = Path(storage_dir).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_extension(self, media_type: str) -> str:
        if "json" in media_type:
            return ".json"
        if "csv" in media_type:
            return ".csv"
        if "html" in media_type:
            return ".html"
        return ".txt"

    def compute_pointer_id(self, payload: str) -> str:
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f"ptr_{digest}"

    def store(
        self,
        payload: str,
        media_type: str = "text/plain",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
        pointer_id = self.compute_pointer_id(payload)
        ext = self._get_extension(media_type)
        file_path = self.storage_dir / f"{pointer_id}{ext}"
        meta_path = self.storage_dir / f"{pointer_id}.meta.json"

        # Content-addressable: if file already exists with same hash, avoid re-write
        if not file_path.exists():
            file_path.write_text(payload, encoding="utf-8")

        if metadata:
            meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        storage_uri = file_path.as_uri()
        return pointer_id, storage_uri

    def retrieve(self, pointer_id: str) -> Optional[str]:
        # Search for pointer_id.* in storage directory
        matches = list(self.storage_dir.glob(f"{pointer_id}.*"))
        for match in matches:
            if not match.name.endswith(".meta.json") and match.is_file():
                return match.read_text(encoding="utf-8")
        return None

    def exists(self, pointer_id: str) -> bool:
        matches = list(self.storage_dir.glob(f"{pointer_id}.*"))
        return any(m.is_file() and not m.name.endswith(".meta.json") for m in matches)

    def delete(self, pointer_id: str) -> bool:
        deleted = False
        matches = list(self.storage_dir.glob(f"{pointer_id}.*"))
        for match in matches:
            if match.is_file():
                match.unlink()
                deleted = True
        return deleted


class OutputGuardResult:
    """Outcome of processing an output through OutputGuard."""

    def __init__(
        self,
        content: str,
        data_pointer: Optional[DataPointer] = None,
        is_offloaded: bool = False,
        is_truncated: bool = False,
        original_size_bytes: int = 0,
    ):
        self.content = content
        self.data_pointer = data_pointer
        self.is_offloaded = is_offloaded
        self.is_truncated = is_truncated
        self.original_size_bytes = original_size_bytes


class OutputGuard:
    """
    Unified manager for tool output protection.
    Intercepts outputs, checks thresholds, creates smart head/tail previews,
    and offloads full artifacts to persistent storage.
    """

    def __init__(
        self,
        mode: Union[OutputGuardMode, str] = OutputGuardMode.OFFLOAD_AND_TRUNCATE,
        threshold_chars: int = 8000,
        head_lines: int = 15,
        tail_lines: int = 10,
        payload_store: Optional[BasePayloadStore] = None,
        storage_dir: Optional[Union[str, Path]] = None,
    ):
        if isinstance(mode, str):
            mode = OutputGuardMode(mode)
        self.mode = mode
        self.threshold_chars = max(100, threshold_chars)
        self.head_lines = max(1, head_lines)
        self.tail_lines = max(0, tail_lines)

        if payload_store is not None:
            self.payload_store = payload_store
        else:
            path = storage_dir or "vault/pointers"
            self.payload_store = LocalDiskPayloadStore(storage_dir=path)

    def _infer_media_type(self, text: str) -> str:
        s = text.strip()
        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
            try:
                json.loads(s)
                return "application/json"
            except Exception:
                pass
        if s.startswith("<html") or s.startswith("<!DOCTYPE html"):
            return "text/html"
        if "\n" in s and ("," in s or "\t" in s):
            # Check if likely CSV
            lines = s.splitlines()[:5]
            if len(lines) > 1 and all("," in l for l in lines):
                return "text/csv"
        return "text/plain"

    def process(
        self,
        output: str,
        tool_name: Optional[str] = None,
        tool_call_id: Optional[str] = None,
        custom_metadata: Optional[Dict[str, Any]] = None,
    ) -> OutputGuardResult:
        """
        Inspects output string against configured threshold.
        Applies truncation and offloading according to mode.
        """
        if not output:
            return OutputGuardResult(content="", original_size_bytes=0)

        original_size = len(output.encode("utf-8"))

        # If PASSTHROUGH or below threshold: return directly
        if self.mode == OutputGuardMode.PASSTHROUGH or len(output) <= self.threshold_chars:
            return OutputGuardResult(
                content=output,
                data_pointer=None,
                is_offloaded=False,
                is_truncated=False,
                original_size_bytes=original_size,
            )

        # Mode A: TRUNCATE_ONLY (in-memory excerpting, no storage write)
        if self.mode == OutputGuardMode.TRUNCATE_ONLY:
            trunc = ToolOutputTruncator.truncate(
                output,
                max_chars=self.threshold_chars,
                head_lines=self.head_lines,
                tail_lines=self.tail_lines,
            )
            banner = [
                f"[TOOL OUTPUT TRUNCATED: {original_size:,} bytes exceeded threshold of {self.threshold_chars:,} chars]",
                f"Lines: {trunc.total_lines:,} total (Omitted: {trunc.omitted_lines:,} lines, ~{trunc.omitted_chars:,} characters)",
                "Notice: Middle content was omitted to preserve context window. Storage offloading is disabled.",
                "",
                trunc.text,
            ]
            return OutputGuardResult(
                content="\n".join(banner),
                data_pointer=None,
                is_offloaded=False,
                is_truncated=True,
                original_size_bytes=original_size,
            )

        # Mode B: OFFLOAD_AND_TRUNCATE (Lossless store + DataPointer contract)
        media_type = self._infer_media_type(output)
        meta = {
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "media_type": media_type,
            "size_bytes": original_size,
        }
        if custom_metadata:
            meta.update(custom_metadata)

        pointer_id, storage_uri = self.payload_store.store(
            payload=output,
            media_type=media_type,
            metadata=meta,
        )

        trunc = ToolOutputTruncator.truncate(
            output,
            max_chars=self.threshold_chars,
            head_lines=self.head_lines,
            tail_lines=self.tail_lines,
        )

        tokens = ToolOutputTruncator.estimate_tokens(output)

        data_pointer = DataPointer(
            pointer_id=pointer_id,
            storage_uri=storage_uri,
            media_type=media_type,
            size_bytes=original_size,
            estimated_tokens=tokens,
            total_lines=trunc.total_lines,
            preview_snippet=trunc.text,
            omitted_lines=trunc.omitted_lines,
            omitted_chars=trunc.omitted_chars,
            head_lines=trunc.head_lines_count,
            tail_lines=trunc.tail_lines_count,
            is_offloaded=True,
            metadata=meta,
        )

        return OutputGuardResult(
            content=data_pointer.to_llm_string(),
            data_pointer=data_pointer,
            is_offloaded=True,
            is_truncated=True,
            original_size_bytes=original_size,
        )
