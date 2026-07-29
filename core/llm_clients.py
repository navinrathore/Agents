import os
import json

class BaseLLMClient:
    def __init__(self, model: str, use_checklist: bool = False, pruning_config: dict = None):
        self.model = model
        self.use_checklist = use_checklist
        self.pruning_config = pruning_config or {}
        self.messages = []
        self.system_prompt = ""

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
            return # Too short to prune safely
            
        # Keep the last 2 assistant turns
        keep_from_idx = assistant_indices[-2]
        
        messages_to_summarize = self.messages[:keep_from_idx]
        messages_to_keep = self.messages[keep_from_idx:]
        
        print(f"\n✂️ [System]: Context size ({self.count_tokens()} tokens) exceeded {max_tokens}. Pruning and summarizing older messages...")
        
        summary_text = self._generate_summary(messages_to_summarize)
        
        summary_message = {
            "role": "user", 
            "content": f"[System Note: Older conversation history has been pruned for context limits. Here is a summary of previous steps:\n{summary_text}]"
        }
        
        self.messages = [summary_message] + messages_to_keep

    def _generate_summary(self, messages_to_summarize: list) -> str:
        raise NotImplementedError

    def add_user_message(self, text: str):
        raise NotImplementedError
        
    def add_assistant_message(self, text: str, tool_calls: list = None):
        raise NotImplementedError
        
    def add_tool_result(self, tool_call_id: str, name: str, result: str):
        raise NotImplementedError

    def generate_response(self, tools: list = None) -> dict:
        raise NotImplementedError

class AnthropicClient(BaseLLMClient):
    def __init__(self, model: str, use_checklist: bool = False, pruning_config: dict = None):
        super().__init__(model, use_checklist, pruning_config)
        from anthropic import Anthropic
        self.client = Anthropic()

    def add_user_message(self, text: str):
        self.messages.append({"role": "user", "content": text})
        
    def add_assistant_message(self, text: str, tool_calls: list = None):
        content = []
        if text:
            content.append({"type": "text", "text": text})
        if tool_calls:
            for tc in tool_calls:
                content.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["input"]
                })
        self.messages.append({"role": "assistant", "content": content})
        
    def add_tool_result(self, tool_call_id: str, name: str, result: str):
        # Anthropic groups tool results in a user message
        if not self.messages or self.messages[-1]["role"] != "user" or isinstance(self.messages[-1]["content"], str):
            self.messages.append({"role": "user", "content": []})
            
        self.messages[-1]["content"].append({
            "type": "tool_result",
            "tool_use_id": tool_call_id,
            "content": result
        })

    def _generate_summary(self, messages_to_summarize: list) -> str:
        summary_prompt = "Please write a concise summary (under 200 words) of the following conversation history and steps taken so far. Be sure to include what has been done and what the current state is:\n\n" + str(messages_to_summarize)
        response = self.client.messages.create(
            model=self.model,
            messages=[{"role": "user", "content": summary_prompt}],
            max_tokens=300
        )
        return response.content[0].text

    def generate_response(self, tools: list = None) -> dict:
        self.prune_context()
        kwargs = {
            "model": self.model,
            "system": self.system_prompt,
            "messages": self.messages,
            "max_tokens": 2000
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
    def __init__(self, model: str, use_checklist: bool = False, pruning_config: dict = None):
        super().__init__(model, use_checklist, pruning_config)
        from huggingface_hub import InferenceClient
        token = os.environ.get("HF_TOKEN")
        if not token:
            for token_file in ["hf_token", "token"]:
                if os.path.exists(token_file):
                    with open(token_file, "r") as f:
                        token = f.read().strip()
                        os.environ["HF_TOKEN"] = token
                    break
        self.client = InferenceClient(token=token)

    def add_user_message(self, text: str):
        self.messages.append({"role": "user", "content": text})
        
    def add_assistant_message(self, text: str, tool_calls: list = None):
        msg = {"role": "assistant", "content": text or ""}
        if tool_calls:
            msg["tool_calls"] = []
            for tc in tool_calls:
                msg["tool_calls"].append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["input"])
                    }
                })
        self.messages.append(msg)
        
    def add_tool_result(self, tool_call_id: str, name: str, result: str):
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": result
        })

    def _generate_summary(self, messages_to_summarize: list) -> str:
        summary_prompt = "Please write a concise summary (under 200 words) of the following conversation history and steps taken so far. Be sure to include what has been done and what the current state is:\n\n" + str(messages_to_summarize)
        actual_model = "Qwen/Qwen2.5-72B-Instruct" if self.model.startswith("claude-") else self.model
        response = self.client.chat.completions.create(
            model=actual_model,
            messages=[{"role": "user", "content": summary_prompt}],
            max_tokens=300
        )
        return response.choices[0].message.content or ""

    def generate_response(self, tools: list = None) -> dict:
        self.prune_context()
        hf_messages = [{"role": "system", "content": self.system_prompt}] + self.messages
        actual_model = "Qwen/Qwen2.5-72B-Instruct" if self.model.startswith("claude-") else self.model
        print(f"(Using Model: {actual_model})")
        
        kwargs = {
            "model": actual_model,
            "messages": hf_messages,
            "max_tokens": 2000
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
                    "input": json.loads(tc.function.arguments)
                })
        return {"text": text, "tool_calls": tool_calls}

def get_llm_client(model: str, use_checklist: bool = False, pruning_config: dict = None) -> BaseLLMClient:
    if os.environ.get("ANTHROPIC_API_KEY"):
        print(">> Selected LLM Provider: Anthropic")
        return AnthropicClient(model, use_checklist, pruning_config)
    else:
        print(">> Selected LLM Provider: Hugging Face (Fallback)")
        return HuggingFaceClient(model, use_checklist, pruning_config)
