# Agentic AI Design Rules (Backup)

When writing or architecting LLM agents in this workspace, strictly adhere to the following principles:

1. **ReAct Loop Safety (Hard Limits)**: Never write an unbounded autonomous `while` loop. Always implement a strict `max_loops` threshold (e.g., 10-15 loops) to prevent expensive token burn during LLM hallucinations or code execution failures.
2. **Provider Agnosticism**: When generating LLM integration code, abstract the underlying SDKs behind a unified interface (e.g., `BaseLLMClient`). Ensure the architecture can seamlessly fallback or swap between providers (Anthropic, Hugging Face, OpenAI) without refactoring the core agent logic.
3. **Conditional Guardrails (The Token Tax)**: Do not blindly enforce rigid internal state-management tools (like an explicit `manage_checklist` tool) on frontier models. Make these guardrails conditionally configurable so they can be toggled off to reduce token and latency overhead for smarter models.
4. **Execution Safety**: Default to safe code execution environments. If writing local `subprocess` execution for an agent, ensure strict timeouts are enforced and strongly recommend Docker or microVM sandboxing for production deployments.
