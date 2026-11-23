"""
Sub-Agent Skill Execution Engine.

Provides isolated child ReAct agent loops for complex, multi-step skill execution.
Enforces strict loop bounds (Rule 1), timeout protection (Rule 4), and context isolation,
preventing parent agent context pollution while bridging sub-agents cleanly as standard tools.
"""

import asyncio
from dataclasses import asdict, dataclass, field
import logging
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional, Union

from core.dispatcher import AsyncToolDispatcher, ToolExecutionResult
from core.llm_clients import BaseLLMClient, get_llm_client
from core.output_guard import OutputGuard, OutputGuardMode
from core.skills import SkillPackage, SkillRegistry
from core.utils import RepetitionDetector

logger = logging.getLogger(__name__)


@dataclass
class SubAgentConfig:
    """
    Configuration options for a child sub-agent execution loop.
    Enforces strict safety ceilings to prevent token burns and hung processes.
    """
    model: str = "auto"
    provider: Optional[str] = None
    max_loops: int = 10                  # Rule 1: Strict hard limit threshold
    timeout_seconds: float = 60.0        # Rule 4: Execution safety timeout
    max_concurrency: int = 3             # Concurrency for child tool dispatcher
    auto_offload_outputs: bool = True    # OutputGuard protection for large tool results
    verbose: bool = False


@dataclass
class SubAgentExecutionResult:
    """
    Structured execution outcome of a child sub-agent workflow.
    Returned to the parent agent or caller as a consolidated final artifact.
    """
    task: str
    skill_name: str
    final_answer: str
    total_loops: int
    duration: float
    success: bool = True
    error: Optional[str] = None
    trajectory: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __str__(self) -> str:
        return self.final_answer


class SkillSubAgent:
    """
    Autonomous child ReAct agent bound to a specific SkillPackage.
    Executes in a completely isolated context window, driving its own loop
    using only the tools and Standard Operating Procedure (SOP) of that skill.
    """

    def __init__(
        self,
        skill_package: SkillPackage,
        config: Optional[SubAgentConfig] = None,
        llm_client: Optional[BaseLLMClient] = None,
        dispatcher: Optional[AsyncToolDispatcher] = None,
    ):
        self.skill_package = skill_package
        self.config = config or SubAgentConfig()
        self.skill_name = self.skill_package.name

        # 1. Initialize isolated LLM client with dedicated context
        if llm_client is not None:
            self.llm = llm_client
        else:
            self.llm = get_llm_client(
                model=self.config.model,
                provider=self.config.provider,
            )

        # 2. Hydrate child system prompt with the skill's specific SOP guidelines
        sop_prompt = (
            f"You are a specialized autonomous sub-agent operating the '{self.skill_name}' skill.\n"
            f"Skill Description: {self.skill_package.description}\n\n"
            f"### Standard Operating Procedure (SOP):\n"
            f"{self.skill_package.sop_content}\n\n"
            "Instructions:\n"
            "- Perform the assigned task thoroughly using your available specialized tools.\n"
            "- When your analysis is complete, provide a clear, concise, and structured final summary.\n"
            "- Do not ask the user for input; synthesize your final answer once the objective is met."
        )
        self.llm.set_system_prompt(sop_prompt)

        # 3. Dedicated AsyncToolDispatcher mounted only with this skill's tools
        if dispatcher is not None:
            self.dispatcher = dispatcher
        else:
            out_guard = (
                OutputGuard(mode=OutputGuardMode.OFFLOAD_AND_TRUNCATE)
                if self.config.auto_offload_outputs
                else None
            )
            self.dispatcher = AsyncToolDispatcher(
                default_timeout=min(30.0, self.config.timeout_seconds),
                parallel_execution=True,
                max_concurrency=self.config.max_concurrency,
                output_guard=out_guard,
            )
            for tool_name, tool_fn in self.skill_package.tool_callables.items():
                self.dispatcher.register_tool(
                    tool_name,
                    tool_fn,
                    require_approval=self.skill_package.metadata.requires_approval,
                )

        # 4. Anti-loop repetition detector for error shielding
        self.repetition_detector = RepetitionDetector(threshold=3, window_size=6)
        self.tool_schemas = self.skill_package.tool_schemas

    async def _run_loop_inner(self, task: str) -> SubAgentExecutionResult:
        """Internal execution loop executed within timeout boundary."""
        start_time = time.perf_counter()
        logger.info(
            "[SubAgent: %s] Spawning child ReAct agent for task: '%s' (max_loops=%d, timeout=%.1fs)",
            self.skill_name,
            task[:80],
            self.config.max_loops,
            self.config.timeout_seconds,
        )

        # Add initial user task to the isolated conversation history
        self.llm.add_user_message(f"Delegated Task: {task}")

        loop_count = 0
        final_answer = ""
        trajectory: List[Dict[str, Any]] = []

        while loop_count < self.config.max_loops:
            loop_count += 1
            loop_start = time.perf_counter()

            if self.config.verbose:
                print(f"  [SubAgent: {self.skill_name}] [Loop {loop_count}/{self.config.max_loops}] Thinking...")

            # Model inference (runs in thread pool if client is sync)
            response = await asyncio.to_thread(
                self.llm.generate_response,
                tools=self.tool_schemas if self.tool_schemas else None,
            )
            if isinstance(response, dict):
                text = response.get("text", "")
                tool_calls = response.get("tool_calls", [])
                if isinstance(text, dict):
                    if not tool_calls and "tool_calls" in text:
                        tool_calls = text.get("tool_calls", [])
                    text = text.get("text", "")
            else:
                text = str(response) if response else ""
                tool_calls = []

            # Record assistant turn in child context
            self.llm.add_assistant_message(text=text, tool_calls=tool_calls)

            logger.debug(
                "[SubAgent: %s] [Loop %d/%d] Generated %d tool call(s) (elapsed: %.2fs)",
                self.skill_name,
                loop_count,
                self.config.max_loops,
                len(tool_calls),
                time.perf_counter() - loop_start,
            )

            # Record trajectory step
            trajectory.append({
                "loop": loop_count,
                "text": text,
                "tool_calls": [tc.get("name") for tc in tool_calls],
            })

            # Termination condition: LLM generated final text without tool calls
            if not tool_calls:
                final_answer = text or "(Task completed with no textual output)"
                logger.info(
                    "[SubAgent: %s] Task completed cleanly in %d loop(s) (%.2fs)",
                    self.skill_name,
                    loop_count,
                    time.perf_counter() - start_time,
                )
                if self.config.verbose:
                    print(f"  [SubAgent: {self.skill_name}] Finished in {loop_count} loops.")
                break

            # Execute tool calls via isolated dispatcher
            tool_results: List[ToolExecutionResult] = await self.dispatcher.dispatch(tool_calls)

            # Feed results back into child context and inspect for repeating errors
            for res in tool_results:
                self.llm.add_tool_result(res.tool_call_id, res.name, res.result)

                # Repetition guardrail (catch ping-pong failure loops)
                if not res.success or "error" in res.result.lower():
                    if self.repetition_detector.check(res.result):
                        err_msg = (
                            f"[SubAgent: {self.skill_name}] Cyclic repetition detected "
                            f"on tool '{res.name}'. Aborting loop to protect quota."
                        )
                        logger.warning(err_msg)
                        return SubAgentExecutionResult(
                            task=task,
                            skill_name=self.skill_name,
                            final_answer=f"Sub-agent stopped: {err_msg}",
                            total_loops=loop_count,
                            duration=round(time.perf_counter() - start_time, 4),
                            success=False,
                            error=err_msg,
                            trajectory=trajectory,
                        )

        # Handle hard loop ceiling reached without final completion
        if loop_count >= self.config.max_loops and not final_answer:
            logger.warning(
                "[SubAgent: %s] Reached maximum loop threshold (%d). Forcing final synthesis.",
                self.skill_name,
                self.config.max_loops,
            )
            # Prompt child LLM to summarize current progress into a final answer
            self.llm.add_user_message(
                "Execution limit reached. Please summarize your findings and provide a final answer based on what you have accomplished so far."
            )
            summary_resp = await asyncio.to_thread(self.llm.generate_response, tools=None)
            if isinstance(summary_resp, dict):
                final_answer = summary_resp.get("text", "Task reached loop limit without full synthesis.")
                if isinstance(final_answer, dict):
                    final_answer = final_answer.get("text", "Task reached loop limit without full synthesis.")
            else:
                final_answer = str(summary_resp)

        duration = round(time.perf_counter() - start_time, 4)
        return SubAgentExecutionResult(
            task=task,
            skill_name=self.skill_name,
            final_answer=final_answer,
            total_loops=loop_count,
            duration=duration,
            success=True,
            trajectory=trajectory,
        )

    async def run(self, task: str) -> SubAgentExecutionResult:
        """
        Executes the sub-agent workflow with strict timeout enforcement.
        """
        try:
            return await asyncio.wait_for(
                self._run_loop_inner(task),
                timeout=self.config.timeout_seconds,
            )
        except asyncio.TimeoutError:
            err = f"SubAgent '{self.skill_name}' timed out after {self.config.timeout_seconds}s."
            logger.error(err)
            return SubAgentExecutionResult(
                task=task,
                skill_name=self.skill_name,
                final_answer=f"Error: {err}",
                total_loops=0,
                duration=self.config.timeout_seconds,
                success=False,
                error=err,
            )
        except Exception as exc:
            err = f"SubAgent '{self.skill_name}' failed with {type(exc).__name__}: {str(exc)}"
            logger.error(err)
            return SubAgentExecutionResult(
                task=task,
                skill_name=self.skill_name,
                final_answer=f"Error: {err}",
                total_loops=0,
                duration=0.0,
                success=False,
                error=err,
            )


class SubAgentEngine:
    """
    High-level engine that manages sub-agent creation and parent dispatcher tool bridging.
    Enables parent agents to delegate complex domain tasks as standard tool calls.
    """

    def __init__(
        self,
        registry: SkillRegistry,
        default_config: Optional[SubAgentConfig] = None,
    ):
        self.registry = registry
        self.default_config = default_config or SubAgentConfig()

    def create_subagent(
        self,
        skill_name: str,
        config: Optional[SubAgentConfig] = None,
        llm_client: Optional[BaseLLMClient] = None,
    ) -> SkillSubAgent:
        """Spawns an isolated SkillSubAgent for a registered skill package."""
        pkg = self.registry.get_skill(skill_name)
        if not pkg:
            raise ValueError(f"Skill '{skill_name}' not found in registry.")

        cfg = config or self.default_config
        return SkillSubAgent(
            skill_package=pkg,
            config=cfg,
            llm_client=llm_client,
        )

    async def execute_subagent(
        self,
        skill_name: str,
        task: str,
        config: Optional[SubAgentConfig] = None,
        llm_client: Optional[BaseLLMClient] = None,
    ) -> SubAgentExecutionResult:
        """Spawns and executes a sub-agent to completion in a single call."""
        subagent = self.create_subagent(skill_name, config=config, llm_client=llm_client)
        return await subagent.run(task)

    def create_tool(
        self,
        skill_name: str,
        config: Optional[SubAgentConfig] = None,
        llm_client: Optional[BaseLLMClient] = None,
    ) -> Callable[[str], Coroutine[Any, Any, str]]:
        """
        Creates an asynchronous callable tool function ready for registration
        on a parent agent's AsyncToolDispatcher.
        """
        pkg = self.registry.get_skill(skill_name)
        if not pkg:
            raise ValueError(f"Skill '{skill_name}' not found in registry.")

        async def subagent_tool(task: str) -> str:
            sub = self.create_subagent(skill_name, config=config, llm_client=llm_client)
            result = await sub.run(task)
            return result.final_answer

        subagent_tool.__name__ = f"delegate_to_{skill_name}"
        subagent_tool.__doc__ = (
            f"Delegates a complex task to an isolated '{skill_name}' sub-agent.\n"
            f"Description: {pkg.description}\n"
            "Args:\n"
            "    task: Detailed instruction describing what the sub-agent should accomplish."
        )
        return subagent_tool

    def register_skill_as_tool(
        self,
        dispatcher: AsyncToolDispatcher,
        skill_name: str,
        tool_name: Optional[str] = None,
        config: Optional[SubAgentConfig] = None,
        llm_client: Optional[BaseLLMClient] = None,
    ) -> str:
        """
        Registers a sub-agent tool directly into the parent's AsyncToolDispatcher.
        Returns the registered tool name.
        """
        tool_fn = self.create_tool(skill_name, config=config, llm_client=llm_client)
        name = tool_name or tool_fn.__name__
        dispatcher.register_tool(name, tool_fn)
        logger.info(
            "[SubAgentEngine] Registered sub-agent tool '%s' for skill '%s'",
            name,
            skill_name,
        )
        return name
