import asyncio
import concurrent.futures
import os
import textwrap
from core.dispatcher import AsyncToolDispatcher, ToolExecutionResult
from core.llm_clients import get_llm_client
from core.utils import ExecutionTimer, RepetitionDetector
from .executor import PythonExecutor
from .sops import SOPRouter
from .tools import get_anthropic_tools, get_openai_tools


class DataAnalystAgent:
    def __init__(self, config: dict, output_dir: str = None):
        self.config = config
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.output_dir = output_dir or os.path.join(base_dir, "outputs")
        self.executor = PythonExecutor(output_dir=self.output_dir)
        self.use_checklist = self.config.get('use_checklist', False)
        self.llm = get_llm_client(
            self.config.get('model', 'claude-sonnet-4-6'), 
            use_checklist=self.use_checklist,
            pruning_config=self.config.get('context_pruning', {})
        )
        self.checklist = {}  # Internal task state: {task_name: is_complete}
        self.sop_router = SOPRouter()
        self.active_sop_name = None
        self.active_sop_content = ""
        
        # Parallel tool dispatcher configuration
        parallel_enabled = self.config.get('parallel_tool_calls', True)
        max_concurrency = int(self.config.get('max_concurrency', 3))
        tool_timeout = float(self.config.get('tool_timeout', 30.0))

        self.dispatcher = AsyncToolDispatcher(
            default_timeout=tool_timeout,
            parallel_execution=parallel_enabled,
            max_concurrency=max_concurrency,
        )
        self._register_default_tools()

    def _register_default_tools(self):
        """Registers default tools into the AsyncToolDispatcher."""
        async def _execute_python(code: str = "") -> str:
            result = await asyncio.to_thread(self.executor.execute, code)
            stdout = result.get('stdout', '')
            stderr = result.get('stderr', '')
            exit_code = result.get('exit_code', 0)
            return f"Exit Code: {exit_code}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"

        async def _manage_checklist(action: str = "", task_name: str = "") -> str:
            if action == "add":
                self.checklist[task_name] = False
                return f"Task '{task_name}' added to checklist."
            elif action == "complete":
                if task_name in self.checklist:
                    self.checklist[task_name] = True
                    return f"Task '{task_name}' marked as complete."
                return f"Error: Task '{task_name}' not found."
            return "Error: Invalid action."

        self.dispatcher.register_tool("execute_python", _execute_python)
        self.dispatcher.register_tool("manage_checklist", _manage_checklist)
        
    def _get_dynamic_system_prompt(self):
        base_prompt = self.config.get('system', '')
        
        # Inject the active SOP workflow guidelines at the end of the base prompt
        if self.active_sop_content:
            base_prompt = f"{base_prompt}\n\n### Active Workflow Guidelines (SOP)\n{self.active_sop_content}"
        
        if not self.use_checklist:
            return base_prompt
            
        checklist_instruction = "\n\nBefore executing any Python code, use the `manage_checklist` tool to `add` tasks outlining your step-by-step plan. As you complete each step, use `manage_checklist` to `complete` the task."
            
        if not self.checklist:
            return base_prompt + checklist_instruction + "\n\n### Internal Checklist\n(No tasks added yet.)"
        
        cl_str = "\n".join([f"[{'x' if status else ' '}] {task}" for task, status in self.checklist.items()])
        return base_prompt + checklist_instruction + f"\n\n### Internal Checklist\n{cl_str}"

    async def run_async(self, data_path: str, question: str):
        """Asynchronous execution loop supporting concurrent parallel tool calling."""
        verbose = self.config.get("verbose", False)
        
        # Dynamically route the query to the correct SOP
        self.active_sop_name, self.active_sop_content = self.sop_router.route(question)
        
        print(f"--- Starting Agent: {self.config.get('name')} ---")
        print(f"Dataset: {data_path}")
        print(f"Question: {question}")
        print(f"Routed SOP: {self.active_sop_name}\n")
        
        user_prompt = f"Dataset Path: {data_path}\nQuestion: {question}"
        self.llm.add_user_message(user_prompt)
        
        loop_count = 0
        max_loops = 10
        error_detector = RepetitionDetector(threshold=3)
        break_agent_loop = False
        
        # Prepare tools schema based on active LLM provider
        is_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
        tools = get_anthropic_tools(self.use_checklist) if is_anthropic else get_openai_tools(self.use_checklist)

        with ExecutionTimer(name="Total Agent Run", verbose=verbose):
            while loop_count < max_loops and not break_agent_loop:
                loop_count += 1
                
                with ExecutionTimer(name=f"Loop {loop_count} Iteration", verbose=verbose):
                    print(f"\n🔄 [Agent Loop {loop_count}] Thinking...")
                    
                    # Update system prompt with the latest checklist state
                    self.llm.set_system_prompt(self._get_dynamic_system_prompt())
                    
                    response = self.llm.generate_response(tools=tools)
                    text = response.get("text", "")
                    tool_calls = response.get("tool_calls", [])
                    
                    if verbose:
                        print(f"🔍 [Debug] Received {len(tool_calls)} tool calls.")
                    
                    # Record the assistant's own message (needed for API history)
                    self.llm.add_assistant_message(text=text, tool_calls=tool_calls)
                    
                    if text:
                        print(f"🤖 [Agent]: {text}")
                        
                    if not tool_calls:
                        print("\n✅ [System]: Agent has completed the analysis.")
                        break
                        
                    if self.dispatcher.parallel_execution:
                        print(f"\n⚙️ [System]: Executing {len(tool_calls)} tool call(s) concurrently (max {self.dispatcher.max_concurrency})...")
                    else:
                        print(f"\n⚙️ [System]: Executing {len(tool_calls)} tool call(s) sequentially...")
                    for tc in tool_calls:
                        if tc.get("name") == "execute_python":
                            code = tc.get("input", {}).get("code", "")
                            print(f"\n⚙️ [System]: Python Code ({tc.get('id', 'N/A')}):\n")
                            print(textwrap.indent(code.strip(), '    │ '))

                    # Concurrently dispatch all tool calls with fault isolation & timeouts
                    results = await self.dispatcher.dispatch(tool_calls)

                    for res in results:
                        tool_name = res.name
                        tool_output = res.result
                        
                        if verbose:
                            print(f"🔍 [Debug] Tool '{tool_name}' ({res.tool_call_id}) completed in {res.duration}s (success={res.success})")

                        if tool_name == "execute_python":
                            print(f"\n⚙️ [System]: Execution complete for {res.tool_call_id}")
                            if "STDOUT:\n" in tool_output:
                                stdout_part = tool_output.split("STDOUT:\n", 1)[1].split("\nSTDERR:", 1)[0]
                                if stdout_part.strip():
                                    print(">> STDOUT:")
                                    print(textwrap.indent(stdout_part.strip(), '   '))
                            if "STDERR:\n" in tool_output:
                                stderr_part = tool_output.split("STDERR:\n", 1)[1]
                                if stderr_part.strip():
                                    print(">> STDERR:")
                                    print(textwrap.indent(stderr_part.strip(), '   '))
                                    if error_detector.check(stderr_part.strip()):
                                        print("\n❌ [System]: Exact same error repeated 3 times. Breaking loop to prevent infinite repetition.")
                                        break_agent_loop = True
                                else:
                                    error_detector.reset()
                        elif tool_name == "manage_checklist":
                            print(f"\n📋 [System]: {tool_output}")
                        else:
                            if not res.success:
                                print(f"⚠️ [System]: {tool_output}")
                            else:
                                print(f"⚙️ [System]: Tool '{tool_name}' finished.")

                        # Add tool result in preserved order to LLM history
                        self.llm.add_tool_result(
                            tool_call_id=res.tool_call_id,
                            name=tool_name,
                            result=tool_output
                        )

                    if break_agent_loop:
                        break
        
        if loop_count >= max_loops:
            print("\n❌ [System]: Reached maximum number of loops.")
        print("--- Agent Run Complete ---")

    def run(self, data_path: str, question: str):
        """Synchronous entry point wrapping run_async for backwards compatibility."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(asyncio.run, self.run_async(data_path, question)).result()
        else:
            return asyncio.run(self.run_async(data_path, question))
