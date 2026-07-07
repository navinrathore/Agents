import textwrap
from .executor import PythonExecutor
from .llm_clients import get_llm_client
from .utils import ExecutionTimer, RepetitionDetector

class DataAnalystAgent:
    def __init__(self, config: dict, output_dir: str = "outputs"):
        self.config = config
        self.output_dir = output_dir
        self.executor = PythonExecutor(output_dir=self.output_dir)
        self.use_checklist = self.config.get('use_checklist', False)
        self.llm = get_llm_client(
            self.config.get('model', 'claude-sonnet-4-6'), 
            use_checklist=self.use_checklist,
            pruning_config=self.config.get('context_pruning', {})
        )
        self.checklist = {}  # Internal task state: {task_name: is_complete}
        
    def _get_dynamic_system_prompt(self):
        base_prompt = self.config.get('system', '')
        
        if not self.use_checklist:
            return base_prompt
            
        checklist_instruction = "\n\nBefore executing any Python code, use the `manage_checklist` tool to `add` tasks outlining your step-by-step plan. As you complete each step, use `manage_checklist` to `complete` the task."
            
        if not self.checklist:
            return base_prompt + checklist_instruction + "\n\n### Internal Checklist\n(No tasks added yet.)"
        
        cl_str = "\n".join([f"[{'x' if status else ' '}] {task}" for task, status in self.checklist.items()])
        return base_prompt + checklist_instruction + f"\n\n### Internal Checklist\n{cl_str}"

    def run(self, data_path: str, question: str):
        verbose = self.config.get("verbose", False)
        
        print(f"--- Starting Agent: {self.config.get('name')} ---")
        print(f"Dataset: {data_path}")
        print(f"Question: {question}\n")
        
        user_prompt = f"Dataset Path: {data_path}\nQuestion: {question}"
        self.llm.add_user_message(user_prompt)
        
        loop_count = 0
        max_loops = 10
        error_detector = RepetitionDetector(threshold=3)
        break_agent_loop = False
        
        with ExecutionTimer(name="Total Agent Run", verbose=verbose):
            while loop_count < max_loops and not break_agent_loop:
                loop_count += 1
                
                with ExecutionTimer(name=f"Loop {loop_count} Iteration", verbose=verbose):
                    print(f"\n🔄 [Agent Loop {loop_count}] Thinking...")
                    
                    # Update system prompt with the latest checklist state
                    self.llm.set_system_prompt(self._get_dynamic_system_prompt())
                    
                    response = self.llm.generate_response()
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
                        
                    for tc in tool_calls:
                        tool_name = tc.get("name")
                        if verbose:
                            print(f"🔍 [Debug] Executing Tool: {tool_name}")
                            
                        if tool_name == "execute_python":
                            code = tc.get("input", {}).get("code", "")
                            print(f"\n⚙️ [System]: Executing Python Code:\n")
                            print(textwrap.indent(code.strip(), '    │ '))
                            
                            result = self.executor.execute(code)
                            
                            stdout = result.get('stdout', '')
                            stderr = result.get('stderr', '')
                            exit_code = result.get('exit_code', 0)
                            
                            print(f"\n⚙️ [System]: Execution complete (Exit Code {exit_code})")
                            if stdout:
                                print(">> STDOUT:")
                                print(textwrap.indent(stdout, '   '))
                            if stderr:
                                print(">> STDERR:")
                                print(textwrap.indent(stderr, '   '))
                                if error_detector.check(stderr):
                                    print("\n❌ [System]: Exact same error repeated 3 times. Breaking loop to prevent infinite repetition.")
                                    break_agent_loop = True
                                    break
                            else:
                                error_detector.reset()
                                
                            # Format result for LLM
                            tool_output = f"Exit Code: {exit_code}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
                            if verbose:
                                print(f"🔍 [Debug] Code execution finished in {result.get('duration', 'N/A')}s")
                                
                            self.llm.add_tool_result(
                                tool_call_id=tc.get("id"),
                                name=tool_name,
                                result=tool_output
                            )
                        elif tool_name == "manage_checklist":
                            action = tc.get("input", {}).get("action")
                            task_name = tc.get("input", {}).get("task_name")
                            
                            if action == "add":
                                self.checklist[task_name] = False
                                msg = f"Task '{task_name}' added to checklist."
                            elif action == "complete":
                                if task_name in self.checklist:
                                    self.checklist[task_name] = True
                                    msg = f"Task '{task_name}' marked as complete."
                                else:
                                    msg = f"Error: Task '{task_name}' not found."
                            else:
                                msg = "Error: Invalid action."
                                
                            print(f"\n📋 [System]: {msg}")
                            self.llm.add_tool_result(tc.get("id"), tool_name, msg)
                        else:
                            print(f"⚠️ [System]: Unknown tool requested: {tool_name}")
                            self.llm.add_tool_result(
                                tool_call_id=tc.get("id"),
                                name=tool_name,
                                result=f"Error: Unknown tool {tool_name}"
                            )
        
        if loop_count >= max_loops:
            print("\n❌ [System]: Reached maximum number of loops.")
        print("--- Agent Run Complete ---")
