# Retrieval-Augmented Generation (RAG) & Grounding

> **Draft Document:** This document serves as a placeholder and workspace for architectural patterns, safety mechanisms, and best practices related to Retrieval-Augmented Generation (RAG) in our agentic systems.

## 📌 Overview
Retrieval-Augmented Generation (RAG) allows agents to dynamically query external knowledge bases (like vector stores, internal wikis, or databases) to retrieve relevant context before generating a response. This grounds the LLM in factual, private data and reduces hallucinations (OWASP LLM09).

## 🛡️ Security & Mitigation (To Be Expanded)
- **Data Provenance & Citations:** Ensuring the agent cites the exact retrieved document.
- **Access Control:** Ensuring the agent only retrieves documents the end-user is authorized to see (RBAC).
- **Indirect Prompt Injection:** Handling malicious payloads embedded inside retrieved documents (refer to `input_safety_and_payload_management.md`).

## ⚙️ Architecture & Implementation Patterns (To Be Expanded)
- **Vector Stores:** (e.g., Chroma, pgvector, Pinecone).
- **Embedding Models:** Selection criteria and dimensionality.
- **Chunking Strategies:** Semantic chunking vs. fixed-size chunking.
- **Prompt-RAG for SOPs:** Using RAG to dynamically load Standard Operating Procedures instead of stuffing them in the system prompt.

## ⚖️ RAG vs. Massive Context Windows

With modern LLMs supporting 1M+ token context windows, deciding between RAG and "Full Context Stuffing" requires an architectural decision check at the beginning of a task:

1.  **Use RAG when:**
    *   **Data Provenance is critical:** You need strict, auditable citations linked back to specific source chunks.
    *   **Latency matters:** You need fast Time-to-First-Token (TTFT) and cannot wait for the LLM to process a massive prompt.
    *   **Access Control (RBAC) is required:** You must filter documents based on user permissions *before* they reach the LLM.
    *   **Data is highly dynamic:** You are querying live databases that update constantly.

2.  **Use Massive Context (Full Context) when:**
    *   **Holistic synthesis is required:** The task involves cross-referencing or summarizing overarching themes across the entire corpus.
    *   **Codebase refactoring:** The LLM needs to understand intricate dependencies across many interconnected files.
    *   **Retrieval failures are unacceptable:** You want to bypass the risk of the vector database failing to find the relevant chunk.

### 🌉 Achieving the Hybrid Approach

The "Hybrid Approach" provides the best of both worlds: it leverages the speed and access-control of RAG to find the right files, but uses the massive context window to feed the LLM *entire documents* instead of tiny, fractured chunks. 

**How to achieve this:**

1. **Intent Routing (Supervisor/Classifier Layer):** 
   Yes, achieving this starts with intent routing. A fast, lightweight router (or a Tool Dispatcher) analyzes the user's prompt. If the user asks *"Summarize the Q3 Financial Report"*, the intent router determines that a traditional chunk-based RAG search will fail to provide a holistic summary.
2. **Document-Level Retrieval (instead of Chunk-Level):**
   Instead of using semantic vector search to find 500-token chunks, the agent uses metadata filtering (or exact-match search) to retrieve the **Document ID** of the entire "Q3 Financial Report." 
3. **Massive Context Stuffing:**
   Once the relevant document(s) are located, the agent fetches the complete, untruncated text of those documents and stuffs them directly into the massive context window (e.g., passing 100,000 tokens into the prompt). 
4. **Agentic Tool Calling:**
   In an agentic framework, this is often exposed as two different tools:
   *   `search_knowledge_base(query)`: Uses traditional vector chunking for specific fact-finding.
   *   `load_full_document(doc_id)`: Leverages the massive context window to read an entire document end-to-end for deep analysis. The LLM decides which tool to use based on the task.

---
*Note: Further details on implementation, LLM-as-Judge factual evaluators, and integration with the ToolDispatcher will be documented here.*
