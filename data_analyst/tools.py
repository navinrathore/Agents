def get_anthropic_tools(use_checklist: bool = False) -> list[dict]:
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

def get_openai_tools(use_checklist: bool = False) -> list[dict]:
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
