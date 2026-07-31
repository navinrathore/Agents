# Multi-Agent AI Framework

A modular, multi-agent AI framework for building autonomous ReAct (Reasoning and Acting) agents. The framework features a shared core framework (`core/`) for provider-agnostic LLM integration, context pruning, and safety guardrails, while keeping individual agent implementations (like the Autonomous Data Analyst) self-contained in dedicated agent directories.

## Getting Started

1. **Prerequisites**: Ensure you have Python installed. The project relies on `pandas`, `matplotlib`, `anthropic`, and `huggingface_hub`.
2. **Authentication**: 
   - **Option A (Recommended)**: Export an `ANTHROPIC_API_KEY` in your `.env` file to use Claude.
   - **Option B (Fallback)**: Provide a Hugging Face token (either in a `.env` file via `HF_TOKEN` or by placing an `hf_token` file in the root directory). The agent defaults to `Qwen/Qwen2.5-72B-Instruct` via the HF Inference API.
3. **Run the Data Analyst Agent**:
```bash
# Activate your virtual environment
source .venv/bin/activate

# Execute the Data Analyst agent
python projects/Agents/run_agent.py \
  --agent data_analyst \
  --data data_analyst/sample_data/sales.csv \
  --question "What are the top 3 products by total revenue?"
```

## Multi-Agent Architecture & Directory Structure

```
projects/Agents/
├── run_agent.py               # Multi-agent CLI runner
├── requirements.txt           # Python dependencies
│
├── core/                      # Shared framework abstractions & utilities
│   ├── config.py              # YAML spec loader & validator
│   ├── llm_clients.py         # Provider-agnostic LLM client (Anthropic & HF) & pruning
│   └── utils.py               # ExecutionTimer & RepetitionDetector
│
├── data_analyst/              # Autonomous Data Analyst Agent
│   ├── agent.py               # Main Data Analyst agent loop & execution routing
│   ├── executor.py            # Subprocess python executor & plot interception
│   ├── tools.py               # Tool definitions (execute_python, manage_checklist)
│   ├── sops.py                # Dynamic SOP router
│   ├── spec.yaml              # Agent prompt instructions, model settings & toggles
│   ├── sops/                  # Declarative SOP markdown procedures
│   ├── templates/             # Agent templates
│   ├── sample_data/           # Sample datasets (sales.csv)
│   └── outputs/               # Generated charts & data artifacts
│
└── docs/                      # Agent architecture & design pattern docs
    ├── AGENTS_rules_backup.md
    ├── agentic_design_patterns.md
    ├── backlog.md
    ├── lessons_learned.md
    └── skills_architecture.md
```

## Core Framework Design

Throughout the development of this framework, several key design principles were implemented:

### 1. Unified Provider-Agnostic LLM Client (`core/llm_clients.py`)
Abstracts away differences between Anthropic and Hugging Face Inference APIs behind a single `BaseLLMClient` interface. Automatically detects available API keys and falls back seamlessly.

### 2. Local Subprocess Execution (`data_analyst/executor.py`)
Runs agent-generated Python code in a isolated subprocess with strict timeouts and automatically intercepts visual outputs (e.g. `plt.show()`), saving charts to the agent's `outputs/` directory.

### 3. Declarative SOP Guidelines (`data_analyst/sops/` & `data_analyst/sops.py`)
Keeps system prompts light by dynamically injecting specific standard operating procedures (data cleaning, visualization, exploration) based on the user's intent.

### 4. Context Pruning for Long-Running Tasks (`core/llm_clients.py`)
Maintains conversation continuity across extended ReAct loops by summarizing older conversation steps while preserving recent assistant turns intact when token thresholds are reached.
