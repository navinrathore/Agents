"""Unit tests for 3-tier AgentMemoryManager in Agents Core."""

import pytest
import sys
import os

# Add Agents to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.memory import AgentMemoryManager, WorkingMemory, EpisodicBuffer, SemanticStore


def test_working_memory_checklist():
    wm = WorkingMemory()
    wm.add_task("Query SQL DB")
    wm.add_task("Generate chart")
    assert wm.checklist["Query SQL DB"] is False

    wm.complete_task("Query SQL DB")
    assert wm.checklist["Query SQL DB"] is True
    assert wm.get_status_summary() == "1/2 tasks complete"


def test_episodic_buffer_bounds_and_summary():
    buf = EpisodicBuffer(max_turns=3)
    buf.add_turn("user", "Hello turn 1")
    buf.add_turn("assistant", "Response turn 2")
    buf.add_turn("user", "Question turn 3")
    assert len(buf.turns) == 3
    assert buf.compressed_summary == ""

    # Adding 4th turn evicts oldest turn and updates compressed_summary
    buf.add_turn("assistant", "Answer turn 4")
    assert len(buf.turns) == 3
    assert len(buf.compressed_summary) > 0
    assert "[user] Hello turn 1" in buf.compressed_summary


def test_semantic_store():
    store = SemanticStore()
    store.set_fact("user_role", "Principal Architect")
    store.set_fact("preferred_model", "claude-sonnet-4-6")
    assert store.get_fact("user_role") == "Principal Architect"

    facts = store.get_all_facts()
    assert "preferred_model" in facts


def test_agent_memory_manager_prompt_context():
    mgr = AgentMemoryManager(max_turns=5)
    mgr.set_fact("database_engine", "PostgreSQL 16")
    mgr.working.add_task("Extract schemas")
    mgr.working.set_scratchpad("Schemas extracted successfully.")
    mgr.add_interaction("user", "Please analyze the user churn rates.")
    mgr.add_interaction("assistant", "Starting churn cohort analysis.")

    context = mgr.get_prompt_context()
    assert "### SEMANTIC FACTS & CONSTRAINTS:" in context
    assert "database_engine: PostgreSQL 16" in context
    assert "### ACTIVE TASK CHECKLIST:" in context
    assert "[ ] Extract schemas" in context
    assert "### WORKING SCRATCHPAD:" in context
    assert "### RECENT INTERACTION TURNS:" in context


def test_agent_memory_export_and_import():
    mgr1 = AgentMemoryManager(max_turns=5)
    mgr1.set_fact("env", "staging")
    mgr1.working.add_task("Deploy service")
    mgr1.working.complete_task("Deploy service")
    mgr1.working.set_scratchpad("Pre-check OK")
    mgr1.add_interaction("user", "Ready to deploy?")

    exported = mgr1.export_state()
    assert "working" in exported
    assert "episodic" in exported
    assert "semantic" in exported

    # Restore in fresh manager
    mgr2 = AgentMemoryManager(max_turns=5)
    mgr2.import_state(exported)

    assert mgr2.get_fact("env") == "staging"
    assert mgr2.working.checklist.get("Deploy service") is True
    assert mgr2.working.scratchpad == "Pre-check OK"
    assert len(mgr2.episodic.turns) == 1
    assert mgr2.episodic.turns[0].content == "Ready to deploy?"
