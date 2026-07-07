# Data Analyst Agent Requirements

## Functional Requirements
1. The agent shall parse a YAML configuration specifying system prompts and available tools.        
2. The agent shall accept a user query and a dataset (CSV) path.
3. The agent shall use a mocked LLM interface (for Phase 1) that simulates code generation.
4. The agent shall execute generated Python code in a controlled subprocess.
5. The agent shall capture standard output and standard error from the code execution.
6. The agent shall allow the executed code to read the provided dataset and write outputs (tables, charts) to an `outputs/` directory.

## Non-Functional Requirements
1. **Safety**: Code execution should have a reasonable timeout (e.g., 30 seconds).
2. **Readability**: Code structure should be clean, modular, and well-documented.
3. **Extensibility**: The agent loop should be easy to integrate with a real LLM API (like Anthropic's) in Phase 2.

## Acceptance Criteria
- [ ] Running the agent with a sample CSV and a question successfully generates a mock response, executes Python code, and produces an expected output (e.g., a print statement or a saved file).
