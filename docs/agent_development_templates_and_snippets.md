# 🛠️ Agent Development Templates, Prompts & Code Snippets

> **Copy-Pasteable Reference Library** containing system prompts, spec schemas, SOP templates, and production Python boilerplate for building agents in this workspace. All templates are grounded in the actual [data_analyst/](file:///home/navin/work/AI/projects/Agents/data_analyst/) implementation.

---

## 📌 Table of Contents

- [🤖 1. System Prompt Templates (Prompt-Caching Optimized)](#-1-system-prompt-templates-prompt-caching-optimized)
  - [1.1 ReAct Base System Prompt](#11-react-base-system-prompt)
  - [1.2 Planner / Delegator System Prompt](#12-planner--delegator-system-prompt)
  - [1.3 Evaluator / Judge System Prompt](#13-evaluator--judge-system-prompt)
- [📜 2. Spec-Driven Agent Configuration Template (`spec.yaml`)](#-2-spec-driven-agent-configuration-template-specyaml)
  - [2A. Working Schema (Actual Codebase)](#2a-working-schema-actual-codebase)
  - [2B. Aspirational Full-Featured Schema (Design Target)](#2b-aspirational-full-featured-schema-design-target)
- [📘 3. Declarative SOP Template (`/sops/task_sop.md`)](#-3-declarative-sop-template-sopstask_sopmd)
- [🔧 4. Tool Schemas & Subprocess Sandboxing Boilerplate](#-4-tool-schemas--subprocess-sandboxing-boilerplate)
  - [4.1 Anthropic Tool Schema Format](#41-anthropic-tool-schema-format)
  - [4.2 OpenAI/HuggingFace Tool Schema Format](#42-openaihuggingface-tool-schema-format)
  - [4.3 Pydantic Tool Arguments Schema (Aspirational)](#43-pydantic-tool-arguments-schema-aspirational)
  - [4.4 Subprocess Tool Execution Wrapper](#44-subprocess-tool-execution-wrapper)
- [💻 5. Provider-Agnostic LLM Engine (`BaseLLMClient`)](#-5-provider-agnostic-llm-engine-basellmclient)
  - [5A. Actual Interface (Stateful, Codebase-Aligned)](#5a-actual-interface-stateful-codebase-aligned)
  - [5B. Aspirational Interface (Stateless, Clean ABC)](#5b-aspirational-interface-stateless-clean-abc)
- [🔄 6. Production ReAct Control Loop (Full-Featured)](#-6-production-react-control-loop-full-featured)
- [🚀 7. New Agent Quick-Start Tutorial (0 to Running Agent)](#-7-new-agent-quick-start-tutorial-0-to-running-agent)
- [⚠️ 8. Common Anti-Patterns (Before/After)](#️-8-common-anti-patterns-beforeafter)
- [🛑 9. Error Handling & Human-in-the-Loop (HITL) Template](#-9-error-handling--human-in-the-loop-hitl-template)

---

## 🤖 1. System Prompt Templates (Prompt-Caching Optimized)

> [!TIP]
> **Prompt Caching Layout**: Keep the **System Persona**, **Tool Schemas**, and **Core Constraints** static across requests. Place dynamic inputs (active SOPs, user instructions, turn memory) near the end. This enables KV cache reuse on Anthropic and Gemini.

### 1.1 ReAct Base System Prompt

This is the actual pattern used in [data_analyst/agent.py](file:///home/navin/work/AI/projects/Agents/data_analyst/agent.py#L26-L42):

```markdown
You are an autonomous AI Agent specialized in data analysis and code execution.

## Core Identity & Responsibilities
- You break down complex goals into incremental, logical execution steps.
- You formulate thoughts, execute tools to observe real environment data, and iterate until the goal is achieved.
- You NEVER fabricate data, tool outputs, or execution results.
- Always "look before you compute" — inspect data shapes, columns, and dtypes before writing analysis code.

## Available Tools
The following tools are available for invocation:
{{ tool_manifest_json }}

## Strict Rules & Constraints
1. **Loop Limit**: Work within the allocated step budget. Do not repeat identical failed tool calls.
2. **Schema Compliance**: Tool arguments MUST strictly conform to the JSON schema specified in the manifest.
3. **Observation Reliance**: Base all reasoning and conclusions strictly on tool execution observations.
4. **Error Recovery**: If a tool call fails, analyze the error message carefully. Do NOT retry with identical code.
5. **Final Response**: When the goal is met, provide a comprehensive final answer summarizing key evidence.
6. **Chart Saving**: Save charts to outputs/ directory. Never use plt.show() — use plt.savefig() instead.

## Standard Operating Procedure (Active SOP)
{{ active_sop_content }}

## Input Context
User Goal: {{ user_query }}
Dataset Path: {{ data_path }}
```

> [!NOTE]
> **Dynamic System Prompt Pattern**: The actual agent updates the system prompt on *every* loop turn via `self.llm.set_system_prompt(self._get_dynamic_system_prompt())`. This allows the checklist state and active SOP to be refreshed without breaking the static prefix cache for the persona and tool sections.

---

### 1.2 Planner / Delegator System Prompt

```markdown
You are a Lead Planning & Delegation Agent in a Multi-Agent System.

## Core Responsibilities
1. Analyze the user request and decompose it into distinct, non-overlapping sub-tasks.
2. Assign each sub-task to the appropriate specialized worker agent.
3. Consolidate worker outputs into a coherent, validated final answer.

## Available Worker Agents
- **DataAnalystAgent**: Executes SQL queries, statistical analysis, and data transformations.
- **CoderAgent**: Writes, tests, and debugs code.
- **ReviewerAgent**: Audits code and validates outputs against quality constraints.

## Output Format
Always format sub-task assignments using structured JSON:
```json
{
  "plan_summary": "High level breakdown of the task",
  "delegations": [
    {
      "target_agent": "DataAnalystAgent",
      "sub_task_id": "task_1",
      "instruction": "Detailed task description with specific requirements",
      "expected_output": "Description of what a successful result looks like"
    }
  ]
}
```
```

---

### 1.3 Evaluator / Judge System Prompt

```markdown
You are an Evaluator Agent responsible for auditing trajectory execution quality.

## Evaluation Criteria
Score the agent trajectory on a scale from 1 to 5 based on:
1. **Correctness**: Did the final answer accurately solve the user prompt?
2. **Efficiency**: Did the agent avoid redundant tool calls and runaway loops?
3. **Safety & Compliance**: Did all tool invocations adhere to safety rules (timeouts, schemas)?
4. **Evidence Quality**: Were conclusions grounded in actual tool observations (not fabricated)?

## Output Schema
```json
{
  "score": 4,
  "reasoning": "Clear explanation of evaluation rationale",
  "passed": true,
  "findings": {
    "correctness": "The agent correctly identified the top 3 products",
    "efficiency": "Used 4 tool calls, no redundant executions",
    "safety": "All code executed within timeout, no dangerous operations"
  },
  "recommended_improvements": ["Consider adding error bars to the chart"]
}
```
```

---

## 📜 2. Spec-Driven Agent Configuration Template (`spec.yaml`)

### 2A. Working Schema (Actual Codebase)

This is the **actual working format** that [run_agent.py](file:///home/navin/work/AI/projects/Agents/run_agent.py) and [core/config.py](file:///home/navin/work/AI/projects/Agents/core/) can parse today. Copy this to create a new agent:

```yaml
# Actual working spec.yaml — matches data_analyst/spec.yaml
name: Data analyst
description: Load, explore, and visualize data; build reports and answer questions from datasets.
model: claude-sonnet-4-6
use_checklist: false
system: |-
  You analyze data. Given a dataset (file path, URL, or query) and a question:

  1. Load the data and print its shape, column names, dtypes, and a small sample. Always look before you compute.
  2. Clean obvious issues — nulls, duplicates, type mismatches — and note what you changed.
  3. Answer the question with code. Prefer pandas/polars for tabular work, matplotlib/plotly for charts.
  4. Save any charts or derived tables to outputs/ and summarize findings in plain language.

  Default to simple, readable analysis over clever one-liners.
tools:
  - type: agent_toolset_20260401
context_pruning:
  enabled: true
  max_tokens: 4000
```

### 2B. Aspirational Full-Featured Schema (Design Target)

This is the **design target** for a full-featured spec schema. Not all fields are supported by the current runtime yet — items marked `# [FUTURE]` are tracked in [backlog.md](file:///home/navin/work/AI/projects/Agents/docs/backlog.md):

```yaml
version: "1.0"
agent:
  name: "DataAnalystAgent"
  description: "Specialized agent for data querying, transformation, and visualization."
  
engine:
  provider: "anthropic"                # Options: anthropic, huggingface, openai
  model: "claude-sonnet-4-6"
  fallback_provider: "huggingface"     # [FUTURE] Auto-failover on primary outage
  fallback_model: "Qwen/Qwen2.5-Coder-32B-Instruct"
  temperature: 0.1
  max_tokens: 4096

guardrails:
  max_loops: 10                        # AGENTS.md Rule 1: Bounded ReAct limit
  timeout_seconds: 30                  # Subprocess execution timeout
  use_checklist: false                 # AGENTS.md Rule 3: Disabled for frontier models
  budget_cap_usd: 1.50                 # [FUTURE] Per-session cost ceiling
  repetition_threshold: 3             # [FUTURE] Break on N consecutive identical errors

sops:
  directory: "data_analyst/sops"
  default_sop: "default_analyst.md"
  routes:                              # [FUTURE] Currently keyword-based, upgrade to semantic
    - intent: "data_cleaning"
      keywords: ["clean", "null", "missing", "duplicate", "outlier"]
      sop: "data_cleaning.md"
    - intent: "visualization"
      keywords: ["plot", "chart", "graph", "visualize", "histogram"]
      sop: "visualization.md"

tools:
  - name: "execute_python"
    description: "Execute Python code in a sandboxed subprocess."
    handler: "data_analyst.executor.PythonExecutor.execute"
    idempotent: false
  - name: "manage_checklist"
    description: "Add or complete tasks on the internal checklist."
    handler: "data_analyst.agent.DataAnalystAgent._handle_checklist"
    idempotent: true
    conditional: "use_checklist == true"  # Only injected when guardrail is active

context_pruning:
  enabled: true
  max_tokens: 4000
  strategy: "summarize_oldest"         # [FUTURE] Options: summarize_oldest, truncate, sliding_window

observability:                          # [FUTURE] Dual transcript config
  transcript_short: "logs/transcript.jsonl"
  transcript_full: "logs/transcript_full.jsonl"
  truncation_limit: 200                 # Characters for short transcript
```

---

## 📘 3. Declarative SOP Template (`/sops/task_sop.md`)

This follows the pattern from [data_analyst/sops/](file:///home/navin/work/AI/projects/Agents/data_analyst/sops/):

```markdown
# SOP: Data Visualization Workflow

## Purpose
Guide the agent through generating production-ready charts from tabular datasets.

## Pre-requisites & Verification
1. Inspect the CSV dataset columns and data types using `df.info()` and `df.head()` before plotting.
2. Handle missing or null values explicitly — drop or impute before chart generation.

## Execution Steps
1. **Data Sanitization**: Clean numeric columns and cast timestamps.
2. **Plotting**: Use `matplotlib` or `seaborn` with styling:
   - Always set `plt.style.use('seaborn-v0_8-darkgrid')` or custom dark theme.
   - Include clear axis titles, chart title, and legend.
3. **Save Output**: Save chart image to `outputs/` with a descriptive filename.
4. **Verification**: Confirm the saved file exists and is non-empty before returning.

## Constraints
- Never display plots with blocking `plt.show()` calls. Use `plt.savefig()` instead.
- Max file size for output images is 5MB.

## Common Failures
- `FileNotFoundError` on save → ensure `os.makedirs(OUTPUT_DIR, exist_ok=True)` runs first.
- Empty chart → verify DataFrame is not empty after filtering/cleaning.
```

---

## 🔧 4. Tool Schemas & Subprocess Sandboxing Boilerplate

### 4.1 Anthropic Tool Schema Format

This is the **actual working format** from [data_analyst/tools.py](file:///home/navin/work/AI/projects/Agents/data_analyst/tools.py#L1-L43):

```python
def get_anthropic_tools(use_checklist: bool = False) -> list[dict]:
    """Returns tool schemas in Anthropic format (input_schema)."""
    tools = [
        {
            "name": "execute_python",
            "description": "Execute Python code in a sandboxed environment. "
                           "Pre-imports pandas as pd and matplotlib.pyplot as plt. "
                           "Output charts are automatically saved.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The Python code to execute."
                    }
                },
                "required": ["code"]
            }
        }
    ]
    
    if use_checklist:
        tools.append({
            "name": "manage_checklist",
            "description": "Manage your internal task checklist. "
                           "action='add' to create tasks, action='complete' to mark done.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add", "complete"],
                        "description": "The action to perform."
                    },
                    "task_name": {
                        "type": "string",
                        "description": "A short, descriptive name of the task."
                    }
                },
                "required": ["action", "task_name"]
            }
        })
        
    return tools
```

### 4.2 OpenAI/HuggingFace Tool Schema Format

Same tools, different schema structure. From [data_analyst/tools.py](file:///home/navin/work/AI/projects/Agents/data_analyst/tools.py#L45-L93):

```python
def get_openai_tools(use_checklist: bool = False) -> list[dict]:
    """Returns tool schemas in OpenAI format (parameters). Used by HuggingFace Inference API."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "execute_python",
                "description": "Execute Python code in a sandboxed environment.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "The Python code to execute."
                        }
                    },
                    "required": ["code"]
                }
            }
        }
    ]
    # ... conditional checklist tool (same pattern)
    return tools
```

> [!IMPORTANT]
> **Provider Agnosticism requires dual tool schemas.** Anthropic uses `input_schema` at the top level. OpenAI/HF wraps everything inside `{"type": "function", "function": {..., "parameters": ...}}`. The agent selects the right format based on the active provider at runtime ([agent.py L64-65](file:///home/navin/work/AI/projects/Agents/data_analyst/agent.py#L64-L65)).

### 4.3 Pydantic Tool Arguments Schema (Aspirational)

For future schema enforcement at the code boundary (tracked in [backlog.md](file:///home/navin/work/AI/projects/Agents/docs/backlog.md)):

```python
from pydantic import BaseModel, Field

class PythonExecutionArgs(BaseModel):
    """Schema for Python code execution tool arguments."""
    code: str = Field(
        ..., 
        description="Valid Python 3 code string to execute in the sandbox."
    )

class ChecklistArgs(BaseModel):
    """Schema for manage_checklist tool arguments."""
    action: str = Field(
        ..., 
        description="Action to perform: 'add' or 'complete'.",
        pattern="^(add|complete)$"
    )
    task_name: str = Field(
        ..., 
        description="A short, descriptive name of the task."
    )
```

### 4.4 Subprocess Tool Execution Wrapper

This is the **actual working pattern** from [data_analyst/executor.py](file:///home/navin/work/AI/projects/Agents/data_analyst/executor.py):

```python
import subprocess
import os
import tempfile
import textwrap

class PythonExecutor:
    """Executes Python code in a subprocess safely. (AGENTS.md Rule 4)"""
    
    def __init__(self, output_dir: str, timeout: int = 30):
        self.output_dir = output_dir
        self.timeout = timeout
        os.makedirs(self.output_dir, exist_ok=True)
        
    def execute(self, code: str) -> dict:
        """
        Executes provided python code in isolated subprocess.
        Pre-imports pandas and matplotlib. Intercepts plt.show() → plt.savefig().
        """
        wrapped_code = textwrap.dedent(f"""
        import pandas as pd
        import matplotlib.pyplot as plt
        import os
        
        OUTPUT_DIR = '{self.output_dir}'
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # Override plt.show to save instead (prevents blocking)
        def save_plot(*args, **kwargs):
            plt.savefig(os.path.join(OUTPUT_DIR, 'plot.png'))
            print("Plot saved to", os.path.join(OUTPUT_DIR, 'plot.png'))
        plt.show = save_plot

        """) + "\n" + code

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(wrapped_code)
            temp_script = f.name
            
        try:
            result = subprocess.run(
                ["python", temp_script],
                capture_output=True,
                text=True,
                timeout=self.timeout       # Hard wall-clock timeout (Rule 4)
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode
            }
        except subprocess.TimeoutExpired as e:
            return {
                "stdout": e.stdout.decode('utf-8') if e.stdout else "",
                "stderr": f"Execution timed out after {self.timeout} seconds.",
                "exit_code": 124
            }
        finally:
            if os.path.exists(temp_script):
                os.remove(temp_script)
```

---

## 💻 5. Provider-Agnostic LLM Engine (`BaseLLMClient`)

### 5A. Actual Interface (Stateful, Codebase-Aligned)

This is the **actual working interface** from [core/llm_clients.py](file:///home/navin/work/AI/projects/Agents/core/llm_clients.py):

```python
class BaseLLMClient:
    """
    Stateful LLM client that maintains conversation history internally.
    
    Design rationale: The stateful pattern was chosen because Anthropic and
    OpenAI APIs require the full message history on each request. Rather than
    forcing the agent loop to manage message formatting (which differs per 
    provider), the client encapsulates both history and provider-specific 
    serialization. The agent loop calls simple methods like add_user_message()
    and add_tool_result() without knowing the underlying API format.
    """
    
    def __init__(self, model: str, use_checklist: bool = False, pruning_config: dict = None):
        self.model = model
        self.use_checklist = use_checklist
        self.pruning_config = pruning_config or {}
        self.messages = []          # Internal conversation history
        self.system_prompt = ""

    def set_system_prompt(self, prompt: str):
        """Update system prompt (called every turn for dynamic SOP/checklist injection)."""
        self.system_prompt = prompt

    def count_tokens(self) -> int:
        """Approximate token count (char_count / 4). Replace with tiktoken for accuracy."""
        return sum(len(str(m)) // 4 for m in self.messages)

    def prune_context(self):
        """
        Auto-prune when context exceeds max_tokens.
        Keeps last 2 assistant turns, summarizes everything older.
        """
        if not self.pruning_config.get("enabled"):
            return
        max_tokens = self.pruning_config.get("max_tokens", 4000)
        if self.count_tokens() <= max_tokens:
            return
        # ... summarize older turns, keep recent context
    
    # ---- Methods that subclasses (AnthropicClient, HuggingFaceClient) implement ----
    
    def add_user_message(self, text: str):
        """Append a user message to conversation history."""
        raise NotImplementedError
        
    def add_assistant_message(self, text: str, tool_calls: list = None):
        """Append an assistant response (with optional tool_calls) to history."""
        raise NotImplementedError
        
    def add_tool_result(self, tool_call_id: str, name: str, result: str):
        """Append a tool execution result to history (format varies by provider)."""
        raise NotImplementedError

    def generate_response(self, tools: list = None) -> dict:
        """
        Send current conversation to the LLM and return normalized response.
        Returns: {"text": str, "tool_calls": [{"id": str, "name": str, "input": dict}]}
        """
        raise NotImplementedError
```

**Provider factory** ([llm_clients.py L203-209](file:///home/navin/work/AI/projects/Agents/core/llm_clients.py#L203-L209)):
```python
def get_llm_client(model: str, use_checklist: bool = False, 
                   pruning_config: dict = None) -> BaseLLMClient:
    """Select provider based on available API keys."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicClient(model, use_checklist, pruning_config)
    else:
        return HuggingFaceClient(model, use_checklist, pruning_config)
```

### 5B. Aspirational Interface (Stateless, Clean ABC)

For future refactoring toward a cleaner stateless API (design target):

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class StatelessLLMClient(ABC):
    """
    Stateless LLM interface — caller manages message history externally.
    Aspirational target for future refactoring. Simplifies testing and 
    enables message serialization/deserialization for crash recovery.
    """

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        Returns:
            {
                "content": str,
                "tool_calls": [{"id": str, "name": str, "args": dict}],
                "usage": {"prompt_tokens": int, "completion_tokens": int}
            }
        """
        pass
```

---

## 🔄 6. Production ReAct Control Loop (Full-Featured)

This is the **actual pattern** from [data_analyst/agent.py](file:///home/navin/work/AI/projects/Agents/data_analyst/agent.py), distilled into a reusable template with all production patterns included:

```python
import os
import textwrap
from core.llm_clients import get_llm_client
from core.utils import ExecutionTimer, RepetitionDetector

class AgentTemplate:
    """
    Production ReAct agent template demonstrating all workspace safety patterns.
    
    Implements:
    - AGENTS.md Rule 1: Hard max_loops bound
    - AGENTS.md Rule 3: Conditional checklist guardrail
    - AGENTS.md Rule 4: Subprocess timeout enforcement
    - AGENTS.md Rule 10: Dynamic SOP routing
    - RepetitionDetector: Breaks on 3x consecutive identical errors
    - ExecutionTimer: Per-loop timing for performance analysis
    - Dynamic system prompt: Updated every turn with checklist/SOP state
    """
    
    def __init__(self, config: dict, output_dir: str = None):
        self.config = config
        self.output_dir = output_dir or "outputs"
        self.use_checklist = config.get('use_checklist', False)
        
        # Provider-agnostic LLM client (Rule 2)
        self.llm = get_llm_client(
            config.get('model', 'claude-sonnet-4-6'),
            use_checklist=self.use_checklist,
            pruning_config=config.get('context_pruning', {})
        )
        
        self.checklist = {}  # Internal state: {task_name: is_complete}
        self.active_sop_content = ""
        
    def _get_dynamic_system_prompt(self):
        """
        Build system prompt dynamically each turn.
        Static prefix (persona + tool descriptions) stays constant for cache hits.
        Dynamic suffix (checklist state, active SOP) changes per turn.
        """
        base_prompt = self.config.get('system', '')
        
        # Inject active SOP workflow (Rule 10)
        if self.active_sop_content:
            base_prompt = f"{base_prompt}\n\n### Active Workflow Guidelines (SOP)\n{self.active_sop_content}"
        
        # Conditional checklist guardrail (Rule 3)
        if not self.use_checklist:
            return base_prompt
            
        checklist_instruction = "\n\nBefore executing code, use `manage_checklist` to plan tasks."
        if not self.checklist:
            return base_prompt + checklist_instruction + "\n\n### Internal Checklist\n(No tasks yet.)"
        
        cl_str = "\n".join([f"[{'x' if done else ' '}] {task}" for task, done in self.checklist.items()])
        return base_prompt + checklist_instruction + f"\n\n### Internal Checklist\n{cl_str}"

    def run(self, query: str):
        verbose = self.config.get("verbose", False)
        
        self.llm.add_user_message(query)
        
        loop_count = 0
        max_loops = 10                                      # Rule 1: Hard limit
        error_detector = RepetitionDetector(threshold=3)    # Break on 3x same error
        break_agent_loop = False
        
        # Select tool schema format based on active provider
        is_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
        tools = get_anthropic_tools(self.use_checklist) if is_anthropic \
                else get_openai_tools(self.use_checklist)

        with ExecutionTimer(name="Total Agent Run", verbose=verbose):
            while loop_count < max_loops and not break_agent_loop:
                loop_count += 1
                
                with ExecutionTimer(name=f"Loop {loop_count}", verbose=verbose):
                    print(f"\n🔄 [Agent Loop {loop_count}] Thinking...")
                    
                    # Dynamic system prompt update (checklist + SOP refresh)
                    self.llm.set_system_prompt(self._get_dynamic_system_prompt())
                    
                    response = self.llm.generate_response(tools=tools)
                    text = response.get("text", "")
                    tool_calls = response.get("tool_calls", [])
                    
                    # Record assistant response in conversation history
                    self.llm.add_assistant_message(text=text, tool_calls=tool_calls)
                    
                    if text:
                        print(f"🤖 [Agent]: {text}")
                        
                    # No tool calls = final answer
                    if not tool_calls:
                        print("\n✅ Agent completed.")
                        break
                        
                    # Dispatch each tool call
                    for tc in tool_calls:
                        tool_name = tc.get("name")
                        
                        if tool_name == "execute_python":
                            code = tc.get("input", {}).get("code", "")
                            result = self.executor.execute(code)
                            
                            stderr = result.get('stderr', '')
                            if stderr and error_detector.check(stderr):
                                print("❌ Same error repeated 3x. Breaking loop.")
                                break_agent_loop = True
                                break
                            elif not stderr:
                                error_detector.reset()
                                
                            tool_output = f"Exit Code: {result['exit_code']}\n" \
                                          f"STDOUT:\n{result['stdout']}\n" \
                                          f"STDERR:\n{stderr}"
                            self.llm.add_tool_result(tc.get("id"), tool_name, tool_output)
                            
                        elif tool_name == "manage_checklist":
                            # Handle checklist tool (Rule 3)
                            action = tc.get("input", {}).get("action")
                            task_name = tc.get("input", {}).get("task_name")
                            if action == "add":
                                self.checklist[task_name] = False
                                msg = f"Task '{task_name}' added."
                            elif action == "complete":
                                self.checklist[task_name] = True
                                msg = f"Task '{task_name}' completed."
                            else:
                                msg = "Error: Invalid action."
                            self.llm.add_tool_result(tc.get("id"), tool_name, msg)
                            
                        else:
                            # Handle unknown/hallucinated tool names
                            available = [t.get("name", t.get("function", {}).get("name", "?")) 
                                         for t in tools]
                            self.llm.add_tool_result(
                                tc.get("id"), tool_name,
                                f"Error: Unknown tool '{tool_name}'. Available: {available}"
                            )
        
        if loop_count >= max_loops:
            print(f"\n❌ Reached max loops ({max_loops}).")
```

---

## 🚀 7. New Agent Quick-Start Tutorial (0 to Running Agent)

Follow this step-by-step tutorial to create a new agent in the workspace. We'll build a hypothetical `code_reviewer` agent.

### Step 1: Create Directory Structure

```bash
cd projects/Agents
mkdir -p code_reviewer/sops
touch code_reviewer/__init__.py
```

### Step 2: Create `code_reviewer/spec.yaml`

```yaml
name: Code reviewer
description: Reviews Python code for bugs, style issues, and security vulnerabilities.
model: claude-sonnet-4-6
use_checklist: false
system: |-
  You are a code review agent. Given a Python file or code snippet:

  1. Read the code carefully and identify bugs, style issues, and security concerns.
  2. Execute the code with test inputs to verify behavior.
  3. Provide a structured review with severity ratings.

  Be specific — cite line numbers and suggest fixes.
tools:
  - type: agent_toolset_20260401
context_pruning:
  enabled: true
  max_tokens: 4000
```

### Step 3: Create Default SOP (`code_reviewer/sops/default_reviewer.md`)

```markdown
# SOP: Code Review Workflow

## Steps
1. Read the provided code file using execute_python to print its contents.
2. Identify potential issues: bugs, missing error handling, type safety, security.
3. Run the code with edge-case inputs to verify behavior.
4. Output a structured review in markdown format with severity levels.

## Constraints
- Never modify the original source file.
- Always test with at least 2 edge cases (empty input, large input).
```

### Step 4: Create SOP Router (`code_reviewer/sops_router.py`)

```python
import os

class ReviewSOPRouter:
    def __init__(self):
        self.sops_dir = os.path.join(os.path.dirname(__file__), "sops")
    
    def route(self, query: str) -> tuple:
        """Returns (sop_filename, sop_content)."""
        sop_file = "default_reviewer.md"  # Single SOP for now
        sop_path = os.path.join(self.sops_dir, sop_file)
        try:
            with open(sop_path, "r") as f:
                return sop_file, f.read()
        except Exception as e:
            return "fallback", f"Standard code review guidelines.\n(Error: {e})"
```

### Step 5: Create Agent (`code_reviewer/agent.py`)

```python
import os
from core.llm_clients import get_llm_client
from core.utils import ExecutionTimer, RepetitionDetector
from data_analyst.executor import PythonExecutor  # Reuse existing executor
from data_analyst.tools import get_anthropic_tools, get_openai_tools
from .sops_router import ReviewSOPRouter

class CodeReviewerAgent:
    def __init__(self, config: dict):
        self.config = config
        self.output_dir = os.path.join(os.path.dirname(__file__), "outputs")
        self.executor = PythonExecutor(output_dir=self.output_dir)
        self.use_checklist = config.get('use_checklist', False)
        self.llm = get_llm_client(
            config.get('model', 'claude-sonnet-4-6'),
            use_checklist=self.use_checklist,
            pruning_config=config.get('context_pruning', {})
        )
        self.sop_router = ReviewSOPRouter()
    
    def run(self, code_path: str, review_focus: str = "general"):
        sop_name, sop_content = self.sop_router.route(review_focus)
        system = self.config.get('system', '') + f"\n\n### Active SOP\n{sop_content}"
        self.llm.set_system_prompt(system)
        
        self.llm.add_user_message(f"Review the code at: {code_path}\nFocus: {review_focus}")
        
        max_loops = 10
        error_detector = RepetitionDetector(threshold=3)
        is_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
        tools = get_anthropic_tools(self.use_checklist) if is_anthropic \
                else get_openai_tools(self.use_checklist)
        
        for loop in range(max_loops):
            response = self.llm.generate_response(tools=tools)
            tool_calls = response.get("tool_calls", [])
            self.llm.add_assistant_message(response.get("text", ""), tool_calls)
            
            if not tool_calls:
                print(f"Review complete:\n{response.get('text', '')}")
                return
            
            # ... dispatch tools (same pattern as data_analyst/agent.py)
```

### Step 6: Register in `run_agent.py`

Add the new agent to the runner's dispatch:

```python
elif agent_name == "code_reviewer":
    from code_reviewer.agent import CodeReviewerAgent
    agent = CodeReviewerAgent(config=config)
    agent.run(code_path=data_path, review_focus=question)
```

### Step 7: Run & Verify

```bash
python run_agent.py --agent code_reviewer \
  --data code_reviewer/samples/buggy_script.py \
  --question "Find all bugs and security issues" \
  --verbose
```

---

## ⚠️ 8. Common Anti-Patterns (Before/After)

### Anti-Pattern 1: Unbounded Loop

```diff
# ❌ BEFORE: No loop limit — will burn tokens indefinitely
-while True:
-    response = llm.generate_response(tools=tools)
-    if not response.get("tool_calls"):
-        break

# ✅ AFTER: Hard max_loops bound (AGENTS.md Rule 1)
+max_loops = 10
+loop_count = 0
+while loop_count < max_loops:
+    loop_count += 1
+    response = llm.generate_response(tools=tools)
+    if not response.get("tool_calls"):
+        break
+if loop_count >= max_loops:
+    print("Reached max loops limit.")
```

### Anti-Pattern 2: Regex Parsing of LLM Output

```diff
# ❌ BEFORE: Fragile regex to extract JSON from LLM text
-import re
-match = re.search(r'\{.*\}', response_text, re.DOTALL)
-data = json.loads(match.group(0))

# ✅ AFTER: Use robust JsonExtractor (AGENTS.md Rule 7)
+from core.utils import JsonExtractor
+data = JsonExtractor.extract(response_text)  # 3-tier extraction pipeline
```

### Anti-Pattern 3: Hardcoded Provider SDK

```diff
# ❌ BEFORE: Tightly coupled to Anthropic SDK
-from anthropic import Anthropic
-client = Anthropic()
-response = client.messages.create(model="claude-3-5-sonnet", messages=messages)

# ✅ AFTER: Provider-agnostic factory (AGENTS.md Rule 2)
+from core.llm_clients import get_llm_client
+llm = get_llm_client(config.get('model'), pruning_config=config.get('context_pruning'))
+response = llm.generate_response(tools=tools)
```

### Anti-Pattern 4: Silent Error Swallowing

```diff
# ❌ BEFORE: Agent silently retries forever on the same error
-stderr = result.get('stderr', '')
-llm.add_tool_result(tc_id, "execute_python", f"STDERR: {stderr}")

# ✅ AFTER: Detect repetition and break (lessons_learned.md §1-2)
+stderr = result.get('stderr', '')
+if stderr and error_detector.check(stderr):
+    print("Same error 3x. Breaking loop.")
+    break_agent_loop = True
+    break
+elif not stderr:
+    error_detector.reset()
+llm.add_tool_result(tc_id, "execute_python", f"STDERR: {stderr}")
```

### Anti-Pattern 5: Monolithic System Prompt

```diff
# ❌ BEFORE: All instructions crammed into one static prompt
-system_prompt = """You are a data analyst. Here are ALL workflows:
-  Data cleaning: ... (200 lines)
-  Visualization: ... (150 lines)
-  SQL querying: ... (100 lines)
-  Report generation: ... (100 lines)"""

# ✅ AFTER: Minimal core prompt + dynamic SOP injection (AGENTS.md Rule 10)
+base_prompt = "You analyze data. Always look before you compute."
+sop_name, sop_content = sop_router.route(question)  # Dynamic routing
+system_prompt = f"{base_prompt}\n\n### Active SOP\n{sop_content}"
```

---

## 🛑 9. Error Handling & Human-in-the-Loop (HITL) Template

### 9.1 Error Classification & Escalation Ladder

```python
from enum import Enum

class ErrorSeverity(Enum):
    TRANSIENT = "transient"    # Network timeout, rate limit → retry with backoff
    SEMANTIC = "semantic"      # LLM misunderstood the task → rephrase and retry
    LOGICAL = "logical"       # Wrong approach, repeated failures → escalate to HITL
    FATAL = "fatal"           # Crash, auth failure, missing resource → abort immediately

def classify_error(stderr: str, exit_code: int) -> ErrorSeverity:
    """Classify tool execution errors for appropriate handling."""
    if exit_code == 124:  # Timeout
        return ErrorSeverity.TRANSIENT
    if "ModuleNotFoundError" in stderr or "ImportError" in stderr:
        return ErrorSeverity.FATAL  # Missing dependency, can't self-fix
    if "FileNotFoundError" in stderr:
        return ErrorSeverity.SEMANTIC  # Wrong path, LLM can try different path
    if "KeyError" in stderr or "ValueError" in stderr:
        return ErrorSeverity.LOGICAL  # Wrong column/logic, may need human help
    return ErrorSeverity.SEMANTIC  # Default: let agent retry once
```

### 9.2 HITL Interrupt Pattern

```python
def handle_with_escalation(error: str, severity: ErrorSeverity, 
                           retry_count: int, max_retries: int = 3) -> str:
    """
    Escalation ladder: retry → self-correct → ask human → abort.
    Implements the pattern from agentic_design_patterns.md §3.
    """
    if severity == ErrorSeverity.FATAL:
        return "ABORT"  # Cannot recover, terminate session
        
    if severity == ErrorSeverity.TRANSIENT and retry_count < max_retries:
        return "RETRY"  # Retry with exponential backoff
        
    if severity == ErrorSeverity.SEMANTIC and retry_count < 2:
        return "SELF_CORRECT"  # Let agent try a different approach
        
    # Escalate to human
    return "HITL"  # Pause loop, ask user for guidance

# Usage in the agent loop:
if severity_result == "HITL":
    user_input = input("🙋 Agent is stuck. Please provide guidance (or 'abort'): ")
    if user_input.lower() == "abort":
        break_agent_loop = True
    else:
        llm.add_user_message(f"Human guidance: {user_input}")
```
