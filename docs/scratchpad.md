# Agent Documentation Scratchpad

This scratchpad contains raw notes, conceptual examples, and drafts that might be integrated into the main documentation later.

---

## Code-Level RBAC and `user_role` Definition Example

**Concept:**
The `user_role` typically comes from the application's authentication and authorization layer (e.g., extracted from a JWT token in the `Authorization` header, a session database, or an Identity Provider).

**Implementation Example:**
Here is a practical example showing how an API endpoint extracts the user's role, instantiates the `ToolDispatcher`, and processes an LLM's tool call.

```python
from fastapi import FastAPI, Depends, HTTPException
from typing import Dict, Any

app = FastAPI()

# 1. Mock dependency to simulate extracting user context from a JWT token
def get_current_user_context(token: str) -> dict:
    # In reality, you would decode the JWT and verify signatures here.
    if token == "token_alice":
        return {"user_id": "u_123", "role": "viewer", "tenant": "acme_corp"}
    elif token == "token_bob":
        return {"user_id": "u_456", "role": "admin", "tenant": "acme_corp"}
    raise HTTPException(status_code=401, detail="Invalid token")

# 2. Main API Endpoint or Agent Loop entry point
@app.post("/api/agent/chat")
async def chat_with_agent(
    user_message: str, 
    token: str, # Passed as a Header (e.g., Authorization: Bearer <token>)
):
    # Step 1: Get the authenticated user's context (Where user_role is defined!)
    user_context = get_current_user_context(token)
    
    # Step 2: Initialize the Dispatcher with the authenticated role
    dispatcher = ToolDispatcher(
        user_role=user_context["role"], 
        user_tenant=user_context["tenant"]
    )
    
    # ... (Imagine we pass user_message to the LLM here) ...
    # ... (The LLM decides to call the 'execute_read_only_sql' tool) ...
    
    # Step 3: The LLM outputs a tool call request
    llm_requested_tool = "execute_read_only_sql"
    llm_requested_args = {"query": "SELECT * FROM users"}
    
    # Step 4: Dispatch the tool securely
    tool_result = dispatcher.dispatch(
        tool_name=llm_requested_tool,
        tool_args=llm_requested_args
    )
    
    # Step 5: Handle the result
    if tool_result.status == "error":
        # The LLM tried to do something it wasn't allowed to do.
        # We feed this error back to the LLM so it knows it was blocked.
        return {"agent_response": f"I cannot perform that action: {tool_result.data}"}
    
    return {"agent_response": "Here is the data...", "data": tool_result.data}
```

**How it works:**
1. If Alice (`token_alice`) asks the agent to query the database, `get_current_user_context` returns her role as `"viewer"`.
2. The `ToolDispatcher` is initialized with `user_role="viewer"`.
3. When the LLM attempts to call `execute_read_only_sql`, the `dispatcher.dispatch()` method checks the permissions.
4. Because `"viewer"` does not have `"execute_read_only_sql"` in its allowed list, the dispatcher blocks it and returns an `Access Denied` error to the agent without querying the database. 

---

## RAG vis-a-vis Context Window

**Initial Classification Decision Check:**
When orchestrating an agentic workflow with massive context window models (1M+ tokens), the architecture should enforce an early routing decision check: *Should this query use RAG or Full Context?*

*   **Route to RAG:** If the query requires strict data provenance/citations, demands low latency (TTFT), queries highly dynamic live databases, or requires enforcing document-level Role-Based Access Control (RBAC).
*   **Route to Full Context:** If the query demands a holistic synthesis across a massive codebase or document library, requires complex cross-referencing to avoid "lost in the middle" retrieval failures, or involves complex refactoring dependencies.
*   **Hybrid Routing:** Use RAG to locate the correct *documents* (not chunks), then load the entire found documents into the massive context window.
