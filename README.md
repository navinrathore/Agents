# Autonomous Data Analyst Agent

This project is a fully autonomous, local ReAct (Reasoning and Acting) AI agent designed to perform data analysis. Given a dataset (e.g., a CSV) and a natural language question, the agent will autonomously inspect the data schema, write python code to clean and aggregate the data, execute it in a local sandbox, and synthesize a final answer based on the execution results.

## Getting Started

1. **Prerequisites**: Ensure you have Python installed. The project relies on `pandas`, `matplotlib`, `anthropic`, and `huggingface_hub`.
2. **Authentication**: 
   - **Option A (Recommended)**: Export an `ANTHROPIC_API_KEY` in your `.env` file to use Claude.
   - **Option B (Fallback)**: Provide a Hugging Face token (either in a `.env` file via `HF_TOKEN` or by placing an `hf_token` file in the root directory). The agent defaults to `Qwen/Qwen2.5-72B-Instruct` via the HF Inference API.
3. **Run the Agent**:
```bash
# Activate your virtual environment
source .venv/bin/activate

# Execute the agent
python .vscode/Agents/run_agent.py \
  --data sample_data/sales.csv \
  --question "What are the top 3 products by total revenue?"
```

## Project Structure

* `run_agent.py`: The CLI entry point that parses arguments, loads environment variables, and kicks off the agent.
* `spec.yaml`: The configuration file containing the agent's system prompt instructions, model settings, and toggles (e.g., `use_checklist`).
* `agent/analyst.py`: The core ReAct `while` loop that handles the conversation history, calls the LLM, and routes tool execution.
* `agent/executor.py`: A `subprocess` wrapper that safely executes the agent's Python code and intercepts `plt.show()` to save charts locally.
* `agent/llm_clients.py`: An abstraction layer seamlessly supporting both Anthropic's SDK and Hugging Face's Inference SDK with OpenAI-compatible tool schemas.
* `agent/tools.py`: JSON Schema definitions for the tools available to the LLM (e.g., `execute_python`, `manage_checklist`).
* `outputs/`: The local directory where all generated charts and data artifacts are saved.
* `docs/`: Contains deeper dives into Agent safety (`lessons_learned.md`) and future improvements (`backlog.md`).

## Key Architectural Decisions

Throughout the development of this framework, several important design decisions were made to balance complexity, cost, and reliability:

### 1. Unified LLM Client Interface
Instead of tying the agent strictly to OpenAI or Anthropic, we built `agent/llm_clients.py` to abstract away provider differences. The system automatically detects if an `ANTHROPIC_API_KEY` is present. If it is not, it gracefully degrades to using the Hugging Face Inference API. 
*Decision Rationale*: Ensures the agent remains highly flexible and runnable by anyone, regardless of which API keys they currently have access to.

### 2. Local Subprocess Execution (Phase 1 & 2)
The `PythonExecutor` runs the LLM's generated code using Python's `subprocess` module with a strict 30-second timeout.
*Decision Rationale*: While production systems (like Devin) use Docker or Firecracker microVMs for total isolation, we opted for local subprocess execution for immediate feedback and simplicity. Moving to Docker is noted in `docs/backlog.md` for future scaling.

### 3. Local Output Redirection
The `PythonExecutor` dynamically intercepts `plt.show()` in the LLM's code and forces it to `plt.savefig()` into the `outputs/` directory.
*Decision Rationale*: AI agents cannot "see" pop-up windows. Redirecting visual output to a static local directory allows users to easily review the generated charts asynchronously after the agent finishes its run.

### 4. Conditional "Checklist" Guardrails
We built a custom `manage_checklist` tool that allows the LLM to write down its plan and check off tasks. This state is maintained in the Python script's memory and dynamically injected into the system prompt on every loop.
*Decision Rationale*: While forcing a Chain-of-Thought checklist prevents weaker models from hallucinating in infinite loops, it imposes a "Token Tax" (wasting turns and tokens) on advanced frontier models that don't need it. We made this feature completely optional via the `use_checklist: false` toggle in `spec.yaml`, providing maximum flexibility depending on the model being used.

### 5. Context Pruning for Long-Running Tasks
To prevent the agent from hitting maximum token limits during extended analysis loops, a context pruning mechanism is built into the `BaseLLMClient`. When the conversation history exceeds a configurable threshold (defined in `spec.yaml`), the agent replaces older `user`/`assistant` turns with a concise LLM-generated summary. **Technically, the algorithm preserves the two most recent `assistant` turns (and their corresponding tool results) in their exact, raw format to ensure the agent's immediate working memory is never broken**, while all prior history is compressed into a single `user` message containing the summary.
*Decision Rationale*: This resets the context window size while seamlessly preserving the agent's situational awareness and progress, avoiding hard truncations that could drop vital instructions or intermediate findings.
