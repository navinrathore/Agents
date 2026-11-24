---
name: global_invariants
description: Mandatory operational boundaries, loop ceilings, and circuit breakers
scope:
  - "*"
priority: 10
immutable: true
enabled: true
---

# Universal Global Invariants
1. **Loop Ceiling**: Never exceed bounded execution limits (Rule 1). When stalled, stop and report rather than loop indefinitely.
2. **Output Discipline**: Adhere strictly to requested formats. When structured output is required, never wrap responses in markdown fences.
3. **Execution Safety**: Never execute destructive operations without verified authorization.
