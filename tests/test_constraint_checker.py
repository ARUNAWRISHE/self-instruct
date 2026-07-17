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
        output="Here is a JSON response.",
        constraints=["Must contain JSON"],
    )
    violations = constraint_checker.check_violations(example)
    assert violations == []
    assert constraint_checker.satisfaction_ratio(example) == 1.0


def test_negative_constraint_violated():
    example = TrainingExample(
        instruction="Do something",
        output="I am sorry, but as an AI...",
        constraints=["Do not apologize"],
    )
    violations = constraint_checker.check_violations(example)
    assert len(violations) == 1
    assert "Constraint violated: Do not apologize" in violations[0]
    assert constraint_checker.satisfaction_ratio(example) == 0.0


def test_mixed_constraints():
    example = TrainingExample(
        instruction="Do something",
        output="Here is the table. I am sorry about the formatting.",
        constraints=["Must output a table", "Do not apologize"],
    )
    violations = constraint_checker.check_violations(example)
    # The heuristic might catch the apology
    assert len(violations) == 1
    assert constraint_checker.satisfaction_ratio(example) == 0.5
