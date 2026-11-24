def get_anthropic_tools(use_checklist: bool = False, enable_pipeline: bool = True) -> list[dict]:
    """
    Returns the tool schemas available to the agent in Anthropic format.
    """
    tools = [
        {
            "name": "execute_python",
            "description": "Execute Python code in a sandboxed environment. Pre-imports pandas as pd and matplotlib.pyplot as plt. Output charts are automatically saved.",
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

    if enable_pipeline:
        tools.append({
            "name": "execute_tool_pipeline",
            "description": "Execute a chained DAG pipeline of dependent tool calls in a single turn without waiting for round-trip LLM turns. Supports referencing previous step outputs via '{{steps.<step_id>.output}}' or '{{steps.<step_id>.output.path}}'.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "description": "List of pipeline steps with IDs, tool names, inputs, and optional dependencies.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string", "description": "Unique alphanumeric step identifier (e.g. step_1)"},
                                "tool": {"type": "string", "description": "Name of the tool to invoke"},
                                "input": {"type": "object", "description": "Input dictionary for the tool. May contain '{{steps.<id>.output}}'"},
                                "depends_on": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "List of step IDs that must complete before this step"
                                },
                                "timeout": {"type": "number", "description": "Optional per-step timeout in seconds"}
                            },
                            "required": ["id", "tool", "input"]
                        }
                    },
                    "on_error": {
                        "type": "string",
                        "enum": ["halt", "skip_dependents", "continue"],
                        "description": "Strategy when a step encounters an error."
                    }
                },
                "required": ["steps"]
            }
        })
    
    if use_checklist:
        tools.append({
            "name": "manage_checklist",
            "description": "Use this tool to manage your internal task checklist. Call it with action='add' to create tasks, and action='complete' to mark them done. It helps you stay on track.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add", "complete"],
                        "description": "The action to perform on the checklist."
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

def get_openai_tools(use_checklist: bool = False, enable_pipeline: bool = True) -> list[dict]:
    """
    Returns the tool schemas available to the agent in OpenAI format (used by Hugging Face Inference).
    """
    tools = [
        {
            "type": "function",
            "function": {
                "name": "execute_python",
                "description": "Execute Python code in a sandboxed environment. Pre-imports pandas as pd and matplotlib.pyplot as plt. Output charts are automatically saved.",
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

    if enable_pipeline:
        tools.append({
            "type": "function",
            "function": {
                "name": "execute_tool_pipeline",
                "description": "Execute a chained DAG pipeline of dependent tool calls in a single turn without waiting for round-trip LLM turns. Supports referencing previous step outputs via '{{steps.<step_id>.output}}' or '{{steps.<step_id>.output.path}}'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "steps": {
                            "type": "array",
                            "description": "List of pipeline steps with IDs, tool names, inputs, and optional dependencies.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string", "description": "Unique alphanumeric step identifier (e.g. step_1)"},
                                    "tool": {"type": "string", "description": "Name of the tool to invoke"},
                                    "input": {"type": "object", "description": "Input dictionary for the tool. May contain '{{steps.<id>.output}}'"},
                                    "depends_on": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "List of step IDs that must complete before this step"
                                    },
                                    "timeout": {"type": "number", "description": "Optional per-step timeout in seconds"}
                                },
                                "required": ["id", "tool", "input"]
                            }
                        },
                        "on_error": {
                            "type": "string",
                            "enum": ["halt", "skip_dependents", "continue"],
                            "description": "Strategy when a step encounters an error."
                        }
                    },
                    "required": ["steps"]
                }
            }
        })
    
    if use_checklist:
        tools.append({
            "type": "function",
            "function": {
                "name": "manage_checklist",
                "description": "Use this tool to manage your internal task checklist. Call it with action='add' to create tasks, and action='complete' to mark them done. It helps you stay on track.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["add", "complete"],
                            "description": "The action to perform on the checklist."
                        },
                        "task_name": {
                            "type": "string",
                            "description": "A short, descriptive name of the task."
                        }
                    },
                    "required": ["action", "task_name"]
                }
            }
        })
        
    return tools
