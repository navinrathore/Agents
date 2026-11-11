"""3-Tier Agent Memory & State Manager for Autonomous Systems.

Implements:
1. L1 Working Memory: Task checklist, mutable scratchpad, and immediate execution frame.
2. L2 Episodic Buffer: Sliding-window turn history with automated token budgeting and micro-summarization.
3. L3 Semantic Memory: Persistent entity fact registry and user preference store.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class WorkingMemory:
    """L1 Working Memory: Scratchpad and active task checklist."""

    def __init__(self):
        self.scratchpad: str = ""
        self.checklist: Dict[str, bool] = {}  # {task_name: is_completed}
        self.execution_vars: Dict[str, Any] = {}

    def add_task(self, task: str):
        if task not in self.checklist:
            self.checklist[task] = False

    def complete_task(self, task: str):
        if task in self.checklist:
            self.checklist[task] = True

    def set_scratchpad(self, text: str):
        self.scratchpad = text

    def append_scratchpad(self, text: str):
        if self.scratchpad:
            self.scratchpad += f"\n{text}"
        else:
            self.scratchpad = text

    def get_status_summary(self) -> str:
        tasks_done = sum(1 for v in self.checklist.values() if v)
        total_tasks = len(self.checklist)
        return f"{tasks_done}/{total_tasks} tasks complete"


class EpisodicTurn:
    """Represents a single conversational/execution turn."""

    def __init__(self, role: str, content: str, timestamp: Optional[str] = None):
        self.role = role
        self.content = content
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content, "timestamp": self.timestamp}

    @classmethod
    def from_dict(cls, data: dict) -> "EpisodicTurn":
        return cls(role=data["role"], content=data["content"], timestamp=data.get("timestamp"))


class EpisodicBuffer:
    """L2 Episodic Memory: Rolling window buffer with token estimation."""

    def __init__(self, max_turns: int = 10, max_chars: int = 8000):
        self.max_turns = max_turns
        self.max_chars = max_chars
        self.turns: List[EpisodicTurn] = []
        self.compressed_summary: str = ""

    def add_turn(self, role: str, content: str):
        turn = EpisodicTurn(role=role, content=content)
        self.turns.append(turn)
        self._enforce_bounds()

    def _enforce_bounds(self):
        # Truncate oldest turns if exceeding max_turns
        if len(self.turns) > self.max_turns:
            evicted = self.turns[:-self.max_turns]
            self.turns = self.turns[-self.max_turns:]
            # Micro-summarize evicted turns
            summaries = [f"[{t.role}] {t.content[:80]}..." for t in evicted]
            new_summary = " | ".join(summaries)
            if self.compressed_summary:
                self.compressed_summary += f" | {new_summary}"
            else:
                self.compressed_summary = new_summary


class SemanticStore:
    """L3 Semantic Memory: Verified fact registry and entity store."""

    def __init__(self):
        self.facts: Dict[str, Any] = {}

    def set_fact(self, key: str, value: Any):
        self.facts[key] = value

    def get_fact(self, key: str, default: Any = None) -> Any:
        return self.facts.get(key, default)

    def delete_fact(self, key: str):
        self.facts.pop(key, None)

    def get_all_facts(self) -> Dict[str, Any]:
        return dict(self.facts)


class AgentMemoryManager:
    """Unified 3-Tier Agent Memory & State Manager."""

    def __init__(self, max_turns: int = 10):
        self.working = WorkingMemory()
        self.episodic = EpisodicBuffer(max_turns=max_turns)
        self.semantic = SemanticStore()

    def add_interaction(self, role: str, content: str):
        self.episodic.add_turn(role=role, content=content)

    def set_fact(self, key: str, value: Any):
        self.semantic.set_fact(key, value)

    def get_fact(self, key: str, default: Any = None) -> Any:
        return self.semantic.get_fact(key, default)

    def get_prompt_context(self) -> str:
        """Assembles a token-efficient prompt context incorporating all 3 tiers."""
        sections = []

        # Tier 3: Semantic Facts
        facts = self.semantic.get_all_facts()
        if facts:
            fact_lines = [f"- {k}: {v}" for k, v in facts.items()]
            sections.append("### SEMANTIC FACTS & CONSTRAINTS:\n" + "\n".join(fact_lines))

        # Tier 1: Working Plan
        if self.working.checklist:
            cl_lines = [f"[{chr(120) if done else chr(32)}] {t}" for t, done in self.working.checklist.items()]
            sections.append("### ACTIVE TASK CHECKLIST:\n" + "\n".join(cl_lines))

        if self.working.scratchpad:
            sections.append("### WORKING SCRATCHPAD:\n" + self.working.scratchpad)

        # Tier 2: Compressed History
        if self.episodic.compressed_summary:
            sections.append("### EARLIER CONVERSATION ABSTRACT:\n" + self.episodic.compressed_summary)

        # Tier 2: Recent Turns
        if self.episodic.turns:
            turn_lines = [f"{t.role.upper()}: {t.content}" for t in self.episodic.turns]
            sections.append("### RECENT INTERACTION TURNS:\n" + "\n".join(turn_lines))

        return "\n\n".join(sections)

    def export_state(self) -> dict:
        """Export complete state for checkpointing and durable persistence."""
        return {
            "working": {
                "scratchpad": self.working.scratchpad,
                "checklist": self.working.checklist,
                "execution_vars": self.working.execution_vars
            },
            "episodic": {
                "compressed_summary": self.episodic.compressed_summary,
                "turns": [t.to_dict() for t in self.episodic.turns]
            },
            "semantic": {
                "facts": self.semantic.get_all_facts()
            }
        }

    def import_state(self, state_dict: dict):
        """Restore state from serialized checkpoint."""
        if "working" in state_dict:
            w = state_dict["working"]
            self.working.scratchpad = w.get("scratchpad", "")
            self.working.checklist = w.get("checklist", {})
            self.working.execution_vars = w.get("execution_vars", {})

        if "episodic" in state_dict:
            e = state_dict["episodic"]
            self.episodic.compressed_summary = e.get("compressed_summary", "")
            self.episodic.turns = [EpisodicTurn.from_dict(td) for td in e.get("turns", [])]

        if "semantic" in state_dict:
            s = state_dict["semantic"]
            self.semantic.facts = s.get("facts", {})
