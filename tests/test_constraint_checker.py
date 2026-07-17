"""Unit tests for constraint_checker."""

import pytest
from aidep.core import constraint_checker
from aidep.core.models import TrainingExample


def test_no_constraints():
    example = TrainingExample(
        instruction="Do something",
        output="Done",
        constraints=[],
    )
    violations = constraint_checker.check_violations(example)
    assert violations == []
    assert constraint_checker.satisfaction_ratio(example) == 1.0


def test_positive_constraint_met():
    example = TrainingExample(
        instruction="Do something",
        output='Here is a JSON response: {"status": "ok"}',
        constraints=["Must contain JSON"],
    )
    violations = constraint_checker.check_violations(example)
    assert violations == []
    assert constraint_checker.satisfaction_ratio(example) == 1.0


def test_negative_constraint_violated():
    example = TrainingExample(
        instruction="Do something",
        output="I am sorry, but as an AI...",
        constraints=["Return JSON format"],
    )
    violations = constraint_checker.check_violations(example)
    assert len(violations) == 1
    assert "Constraint requires JSON output but none found." in violations[0]
    assert constraint_checker.satisfaction_ratio(example) == 0.0


def test_mixed_constraints():
    example = TrainingExample(
        instruction="Do something",
        output="""def my_func():\n    pass\n""",
        constraints=["Must output code", "under 1 words"],
    )
    violations = constraint_checker.check_violations(example)
    # The heuristic will catch the word count because code has 3 words
    assert len(violations) == 1
    assert constraint_checker.satisfaction_ratio(example) == 0.5

