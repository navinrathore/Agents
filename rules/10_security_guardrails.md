---
name: security_guardrails
description: Data protection, PII masking, and sandboxing rules
scope:
  - "*"
priority: 15
immutable: true
enabled: true
---

# Security & Sandboxing Guardrails
1. **Credential Boundaries**: Never leak environment variables, API keys, or raw auth tokens into outputs.
2. **PII Masking**: Ensure sensitive identifiers (passwords, social security numbers) are redacted or masked.
3. **Code Isolation**: Local code execution must strictly observe timeouts and sandbox isolation constraints.
