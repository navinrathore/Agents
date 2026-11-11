"""Universal Provider-Agnostic LLM Client Engine (projects/Agents/core).

Supports:
- Anthropic Claude API
- Hugging Face Inference Router (https://router.huggingface.co/v1)
- OpenAI and OpenAI-compatible endpoints (vLLM, Ollama, Groq, DeepSeek)
- MockLLMClient for zero-token, hermetic testing & CI/CD
- Context pruning and token budgeting
- Schema-enforced structured generation with Pydantic and JSON repair
"""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, Union

from core.utils import JsonExtractor, StructuredOutputParser

try:
    from pydantic import BaseModel, ValidationError
    PYDANTIC_AVAILABLE = True
except ImportError:
    BaseModel = Any
    ValidationError = Exception
    PYDANTIC_AVAILABLE = False

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


def resolve_hf_token(explicit_token: Optional[str] = None) -> Optional[str]:
    """Resolve Hugging Face token from parameter, env vars, or local credential files."""
    if explicit_token is not None:
        token_str = explicit_token.strip()
        return token_str if token_str else None

    env_token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
    if env_token:
        return env_token.strip()

    candidate_paths = [
        Path.cwd() / "hf_token",
        Path.cwd() / "token",
        Path.home() / ".cache" / "huggingface" / "token",
    ]
    for p in candidate_paths:
        try:
            if p.exists() and p.is_file():
                token = p.read_text(encoding="utf-8").strip()
                if token:
                    return token
        except OSError:
            continue

    return None


class BaseLLMClient:
    """Abstract base class defining unified stateful and stateless LLM interactions."""

    def __init__(
        self,
        model: str,
        use_checklist: bool = False,
        pruning_config: Optional[dict] = None,
        temperature: float = 0.1,
        max_retries: int = 3,
    ):
        self.model = model
        self.model_name = model
        self.use_checklist = use_checklist
        self.pruning_config = pruning_config or {}
        self.temperature = temperature
        self.max_retries = max_retries
        self.messages: List[Dict[str, Any]] = []
        self.system_prompt: str = ""

    def set_system_prompt(self, prompt: str):
        self.system_prompt = prompt

    def count_tokens(self) -> int:
        return sum(len(str(m)) // 4 for m in self.messages)

    def prune_context(self):
        if not self.pruning_config.get("enabled"):
            return

        max_tokens = self.pruning_config.get("max_tokens", 4000)
        if self.count_tokens() <= max_tokens:
            return

        assistant_indices = [i for i, m in enumerate(self.messages) if m.get("role") == "assistant"]
        if len(assistant_indices) < 2:
            return

        keep_from_idx = assistant_indices[-2]
        messages_to_summarize = self.messages[:keep_from_idx]
        messages_to_keep = self.messages[keep_from_idx:]

        print(f"\n✂️ [System]: Context size ({self.count_tokens()} tokens) exceeded {max_tokens}. Pruning older messages...")
        summary_text = self._generate_summary(messages_to_summarize)
        summary_message = {
            "role": "user",
            "content": f"[System Note: Older conversation history has been pruned for context limits. Summary of previous steps:\n{summary_text}]",
        }
        self.messages = [summary_message] + messages_to_keep

    def _generate_summary(self, messages_to_summarize: list) -> str:
        raise NotImplementedError

    def add_user_message(self, text: str):
        self.messages.append({"role": "user", "content": text})

    def add_assistant_message(self, text: str, tool_calls: Optional[list] = None):
        raise NotImplementedError

    def add_tool_result(self, tool_call_id: str, name: str, result: str):
        raise NotImplementedError

    def generate_response(self, tools: Optional[list] = None) -> dict:
        """Stateful turn generation (returns dict with text and tool_calls)."""
        raise NotImplementedError

    def generate(self, messages: Optional[List[Dict[str, str]]] = None, **kwargs: Any) -> str:
        """Stateless / graph-friendly generation given a list of messages.

        If messages is None, defaults to [system_prompt] + self.messages.
        """
        raise NotImplementedError

    def generate_structured(
        self,
        messages: Optional[List[Dict[str, str]]] = None,
        schema: Optional[Type[T]] = None,
        **kwargs: Any,
    ) -> T:
        """Enforces structured output parsing using a Pydantic schema with schema injection & error repair."""
        if schema is None or not PYDANTIC_AVAILABLE:
            raise ValueError("A valid Pydantic BaseModel schema is required for generate_structured.")

        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        system_instruction = (
            f"\n\nCRITICAL OUTPUT REQUIREMENT:\n"
            f"You must return ONLY a single valid JSON object strictly matching this JSON Schema:\n"
            f"{schema_json}\n"
            f"Do not include conversational chatter, explanation, or markdown code fences outside the JSON."
        )

        input_messages = list(messages if messages is not None else ([{"role": "system", "content": self.system_prompt}] + self.messages))
        if input_messages and input_messages[-1].get("role") == "user":
            last_msg = input_messages[-1]
            input_messages[-1] = {
                "role": "user",
                "content": f"{last_msg.get('content', '')}{system_instruction}",
            }
        else:
            input_messages.append({"role": "user", "content": system_instruction})

        raw_response = self.generate(messages=input_messages, **kwargs)
        success, validated_model, err = StructuredOutputParser.parse(raw_response, response_model=schema)

        if success and validated_model is not None:
            return validated_model

        # Error repair loop
        logger.warning(f"Initial schema validation failed: {err}. Attempting single-turn repair...")
        repair_messages = [
            {"role": "user", "content": f"The following JSON response was malformed:\n{raw_response}\n\nValidation Error: {err}\nPlease fix and output ONLY the valid JSON matching schema:\n{schema_json}"}
        ]
        repaired_raw = self.generate(messages=repair_messages, **kwargs)
        repair_success, repaired_model, repair_err = StructuredOutputParser.parse(repaired_raw, response_model=schema)

        if repair_success and repaired_model is not None:
            return repaired_model

        raise ValueError(f"Failed to extract structured response for {schema.__name__}: {repair_err or err}")


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude Client supporting tool calling, streaming, and context pruning."""

    def __init__(self, model: str = "claude-sonnet-4-6", use_checklist: bool = False, pruning_config: Optional[dict] = None, **kwargs):
        super().__init__(model, use_checklist, pruning_config, **kwargs)
        from anthropic import Anthropic
        self.client = Anthropic()

    def add_assistant_message(self, text: str, tool_calls: Optional[list] = None):
        content = []
        if text:
            content.append({"type": "text", "text": text})
        if tool_calls:
            for tc in tool_calls:
                content.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["input"],
                })
        self.messages.append({"role": "assistant", "content": content})

    def add_tool_result(self, tool_call_id: str, name: str, result: str):
        if not self.messages or self.messages[-1]["role"] != "user" or isinstance(self.messages[-1]["content"], str):
            self.messages.append({"role": "user", "content": []})

        self.messages[-1]["content"].append({
            "type": "tool_result",
            "tool_use_id": tool_call_id,
            "content": result,
        })

    def _generate_summary(self, messages_to_summarize: list) -> str:
        summary_prompt = "Please write a concise summary (under 200 words) of the following conversation history and steps taken so far:\n\n" + str(messages_to_summarize)
        response = self.client.messages.create(
            model=self.model,
            messages=[{"role": "user", "content": summary_prompt}],
            max_tokens=300,
        )
        return response.content[0].text

    def generate(self, messages: Optional[List[Dict[str, str]]] = None, **kwargs: Any) -> str:
        msgs = list(messages if messages is not None else self.messages)
        # Extract system prompt if in messages
        system_text = self.system_prompt
        clean_msgs = []
        for m in msgs:
            if m.get("role") == "system":
                system_text = m.get("content", "")
            else:
                clean_msgs.append(m)

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    system=system_text,
                    messages=clean_msgs,
                    max_tokens=kwargs.get("max_tokens", 2000),
                    temperature=kwargs.get("temperature", self.temperature),
                )
                text = ""
                for block in response.content:
                    if block.type == "text":
                        text += block.text
                return text
            except Exception as e:
                logger.warning(f"Anthropic call failed (attempt {attempt}/{self.max_retries}): {e}")
                if attempt == self.max_retries:
                    raise
                time.sleep(min(2 ** attempt, 8))
        return ""

    def generate_response(self, tools: Optional[list] = None) -> dict:
        self.prune_context()
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "system": self.system_prompt,
            "messages": self.messages,
            "max_tokens": 2000,
        }
        if tools:
            kwargs["tools"] = tools

        response = self.client.messages.create(**kwargs)
        text = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                tool_calls.append({"id": block.id, "name": block.name, "input": block.input})
        return {"text": text, "tool_calls": tool_calls}


class HuggingFaceClient(BaseLLMClient):
    """Hugging Face Inference Router Client.

    Routes through modern OpenAI-compatible https://router.huggingface.co/v1 endpoint.
    """

    def __init__(
        self,
        model: str = "Qwen/Qwen2.5-72B-Instruct",
        use_checklist: bool = False,
        pruning_config: Optional[dict] = None,
        hf_token: Optional[str] = None,
        base_url: str = "https://router.huggingface.co/v1",
        **kwargs,
    ):
        super().__init__(model, use_checklist, pruning_config, **kwargs)
        token = resolve_hf_token(hf_token)
        if not token:
            raise ValueError(
                "HF_TOKEN is required for HuggingFaceClient. "
                "Provide it via parameter, HF_TOKEN environment variable, or ~/.cache/huggingface/token."
            )
        from openai import OpenAI
        self.client = OpenAI(base_url=base_url, api_key=token)

    def add_assistant_message(self, text: str, tool_calls: Optional[list] = None):
        msg: Dict[str, Any] = {"role": "assistant", "content": text or ""}
        if tool_calls:
            msg["tool_calls"] = []
            for tc in tool_calls:
                msg["tool_calls"].append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["input"]),
                    },
                })
        self.messages.append(msg)

    def add_tool_result(self, tool_call_id: str, name: str, result: str):
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": result,
        })

    def _generate_summary(self, messages_to_summarize: list) -> str:
        summary_prompt = "Please write a concise summary (under 200 words) of the following conversation history and steps taken so far:\n\n" + str(messages_to_summarize)
        actual_model = "Qwen/Qwen2.5-72B-Instruct" if self.model.startswith("claude-") else self.model
        response = self.client.chat.completions.create(
            model=actual_model,
            messages=[{"role": "user", "content": summary_prompt}],
            max_tokens=300,
        )
        return response.choices[0].message.content or ""

    def generate(self, messages: Optional[List[Dict[str, str]]] = None, **kwargs: Any) -> str:
        msgs = list(messages if messages is not None else ([{"role": "system", "content": self.system_prompt}] + self.messages))
        actual_model = "Qwen/Qwen2.5-72B-Instruct" if self.model.startswith("claude-") else self.model

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=actual_model,
                    messages=msgs,  # type: ignore
                    temperature=kwargs.get("temperature", self.temperature),
                    max_tokens=kwargs.get("max_tokens", 2000),
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                logger.warning(f"HF Router call failed (attempt {attempt}/{self.max_retries}): {e}")
                if attempt == self.max_retries:
                    raise
                time.sleep(min(2 ** attempt, 8))
        return ""

    def generate_response(self, tools: Optional[list] = None) -> dict:
        self.prune_context()
        hf_messages = [{"role": "system", "content": self.system_prompt}] + self.messages
        actual_model = "Qwen/Qwen2.5-72B-Instruct" if self.model.startswith("claude-") else self.model

        kwargs: Dict[str, Any] = {
            "model": actual_model,
            "messages": hf_messages,
            "max_tokens": 2000,
            "temperature": self.temperature,
        }
        if tools:
            kwargs["tools"] = tools

        response = self.client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        text = message.content or ""
        tool_calls = []
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": json.loads(tc.function.arguments),
                })
        return {"text": text, "tool_calls": tool_calls}


class OpenAILLMClient(BaseLLMClient):
    """Client for OpenAI and OpenAI-compatible endpoints (vLLM, Ollama, Groq)."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        use_checklist: bool = False,
        pruning_config: Optional[dict] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(model, use_checklist, pruning_config, **kwargs)
        from openai import OpenAI
        token = api_key or os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=token, base_url=base_url)

    def add_assistant_message(self, text: str, tool_calls: Optional[list] = None):
        msg: Dict[str, Any] = {"role": "assistant", "content": text or ""}
        if tool_calls:
            msg["tool_calls"] = []
            for tc in tool_calls:
                msg["tool_calls"].append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": json.dumps(tc["input"])},
                })
        self.messages.append(msg)

    def add_tool_result(self, tool_call_id: str, name: str, result: str):
        self.messages.append({"role": "tool", "tool_call_id": tool_call_id, "name": name, "content": result})

    def _generate_summary(self, messages_to_summarize: list) -> str:
        prompt = "Summarize the previous conversation turns:\n\n" + str(messages_to_summarize)
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
        )
        return resp.choices[0].message.content or ""

    def generate(self, messages: Optional[List[Dict[str, str]]] = None, **kwargs: Any) -> str:
        msgs = list(messages if messages is not None else ([{"role": "system", "content": self.system_prompt}] + self.messages))
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=msgs,  # type: ignore
                    temperature=kwargs.get("temperature", self.temperature),
                    max_tokens=kwargs.get("max_tokens", 2000),
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                logger.warning(f"OpenAI call failed (attempt {attempt}/{self.max_retries}): {e}")
                if attempt == self.max_retries:
                    raise
                time.sleep(min(2 ** attempt, 8))
        return ""

    def generate_response(self, tools: Optional[list] = None) -> dict:
        self.prune_context()
        msgs = [{"role": "system", "content": self.system_prompt}] + self.messages
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": msgs,
            "max_tokens": 2000,
            "temperature": self.temperature,
        }
        if tools:
            kwargs["tools"] = tools

        response = self.client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        text = msg.content or ""
        tool_calls = []
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": json.loads(tc.function.arguments),
                })
        return {"text": text, "tool_calls": tool_calls}


class MockLLMClient(BaseLLMClient):
    """Hermetic Mock LLM Client for zero-token, deterministic offline test suites."""

    def __init__(
        self,
        model: str = "mock-model",
        use_checklist: bool = False,
        pruning_config: Optional[dict] = None,
        canned_responses: Optional[List[str]] = None,
        structured_generator: Optional[Callable[[List[Dict[str, str]], Type[BaseModel]], BaseModel]] = None,
        **kwargs,
    ):
        super().__init__(model, use_checklist, pruning_config, **kwargs)
        self.canned_responses = list(canned_responses or ["Mock response."])
        self.response_index = 0
        self.structured_generator = structured_generator
        self.call_history: List[List[Dict[str, str]]] = []

    def add_assistant_message(self, text: str, tool_calls: Optional[list] = None):
        self.messages.append({"role": "assistant", "content": text or ""})

    def add_tool_result(self, tool_call_id: str, name: str, result: str):
        self.messages.append({"role": "tool", "tool_call_id": tool_call_id, "name": name, "content": result})

    def _generate_summary(self, messages_to_summarize: list) -> str:
        return "Mock summary of pruned messages."

    def generate(self, messages: Optional[List[Dict[str, str]]] = None, **kwargs: Any) -> str:
        msgs = list(messages if messages is not None else ([{"role": "system", "content": self.system_prompt}] + self.messages))
        self.call_history.append(msgs)
        if not self.canned_responses:
            return "{}"
        resp = self.canned_responses[self.response_index % len(self.canned_responses)]
        self.response_index += 1
        return resp

    def generate_response(self, tools: Optional[list] = None) -> dict:
        text = self.generate()
        return {"text": text, "tool_calls": []}

    def generate_structured(
        self,
        messages: Optional[List[Dict[str, str]]] = None,
        schema: Optional[Type[T]] = None,
        **kwargs: Any,
    ) -> T:
        msgs = list(messages if messages is not None else ([{"role": "system", "content": self.system_prompt}] + self.messages))
        if self.structured_generator:
            self.call_history.append(msgs)
            res = self.structured_generator(msgs, schema)
            if isinstance(res, schema):
                return res

        return super().generate_structured(messages=msgs, schema=schema, **kwargs)


def get_llm_client(
    model: str = "auto",
    provider: Optional[str] = None,
    use_checklist: bool = False,
    pruning_config: Optional[dict] = None,
    **kwargs,
) -> BaseLLMClient:
    """Universal factory helper to instantiate the configured LLM provider.

    Selection rules:
    - If provider is explicitly specified: uses 'mock', 'openai', 'anthropic', or 'huggingface'/'hf'.
    - If provider is None:
      - If first argument matches known provider ('mock', 'openai', 'hf', 'anthropic', 'auto'), routes to that provider.
      - If first argument looks like a model name ('claude*', 'gpt*', 'meta-llama*', or contains '/'), uses auto-discovery.
      - Otherwise treats non-model string as provider name (raising ValueError if unsupported).
    """
    model_arg = kwargs.pop("model_name", None)
    known_providers = {"mock", "openai", "huggingface", "hf", "anthropic", "auto"}
    known_model_prefixes = ("claude", "gpt", "meta-llama", "qwen", "mistral", "deepseek")

    if provider is not None:
        prov = provider.lower()
        effective_model = model_arg or model
    elif model.lower() in known_providers:
        prov = model.lower()
        effective_model = model_arg or "auto"
    elif any(model.lower().startswith(pfx) for pfx in known_model_prefixes) or "/" in model:
        prov = None
        effective_model = model_arg or model
    else:
        # Passed an unknown provider string as the first positional argument
        prov = model.lower()
        effective_model = model_arg or "auto"

    if prov == "mock":
        return MockLLMClient(model=effective_model, use_checklist=use_checklist, pruning_config=pruning_config, **kwargs)
    elif prov == "openai":
        return OpenAILLMClient(model=effective_model, use_checklist=use_checklist, pruning_config=pruning_config, **kwargs)
    elif prov in ("hf", "huggingface"):
        return HuggingFaceClient(model=effective_model, use_checklist=use_checklist, pruning_config=pruning_config, **kwargs)
    elif prov == "anthropic":
        return AnthropicClient(model=effective_model, use_checklist=use_checklist, pruning_config=pruning_config, **kwargs)
    elif prov and prov != "auto":
        raise ValueError(f"Unsupported LLM provider: {prov}")

    # Auto discovery
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicClient(model=effective_model, use_checklist=use_checklist, pruning_config=pruning_config, **kwargs)

    token = resolve_hf_token(kwargs.get("hf_token"))
    if token:
        return HuggingFaceClient(model=effective_model, use_checklist=use_checklist, pruning_config=pruning_config, hf_token=token, **kwargs)

    if os.environ.get("OPENAI_API_KEY"):
        return OpenAILLMClient(model=effective_model, use_checklist=use_checklist, pruning_config=pruning_config, **kwargs)

    return MockLLMClient(model=effective_model, use_checklist=use_checklist, pruning_config=pruning_config, **kwargs)
