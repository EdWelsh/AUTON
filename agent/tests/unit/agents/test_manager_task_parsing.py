"""The manager reads a task array robustly (w18 R1 on Sonnet planned 0 tasks from a 9 KB reply)."""

from orchestrator.agents.manager_agent import tasks_from_text


def test_prose_with_brackets_after_the_array_does_not_break_it():
    text = 'Plan:\n[{"task_id": "mm-001", "title": "t"}]\nNotes: see [mm.md] and [arch].'
    assert [t["task_id"] for t in tasks_from_text(text)] == ["mm-001"]


def test_a_bracket_before_the_array_is_skipped():
    text = 'Read [mm.md] first.\n[{"task_id": "a"}, {"task_id": "b"}]'
    assert [t["task_id"] for t in tasks_from_text(text)] == ["a", "b"]


def test_no_array_is_empty():
    assert tasks_from_text("I planned nothing.") == []
