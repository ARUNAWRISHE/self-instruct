"""
ConstraintChecker — shared utility (ISSUE-10)

Extracted from ValidationEngine._check_constraints() and
QualityEngine._check_consistency() to eliminate DRY violation.
Both engines now import this single source of truth.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from aidep.core.models import TrainingExample


def check_violations(example: "TrainingExample") -> List[str]:
    """
    Return a list of constraint violation messages.
    Empty list means all constraints are satisfied.
    """
    issues: List[str] = []

    for constraint in example.constraints:
        c_lower = constraint.lower()

        # Word count limit: "under N words"
        if "under" in c_lower and "words" in c_lower:
            try:
                limit = int(re.search(r"\d+", c_lower).group())
                word_count = len(example.output.split())
                if word_count > limit:
                    issues.append(
                        f"Output exceeds word limit ({word_count} > {limit})."
                    )
            except (AttributeError, ValueError):
                pass

        # JSON output required
        elif "json" in c_lower:
            if "{" not in example.output and "[" not in example.output:
                issues.append("Constraint requires JSON output but none found.")

        # Code output required
        elif any(k in c_lower for k in ["code", "python", "function"]):
            if not any(
                k in example.output
                for k in ["def ", "class ", "import ", "```"]
            ):
                issues.append("Constraint requires code output but none found.")

    return issues


def satisfaction_ratio(example: "TrainingExample") -> float:
    """
    Return constraint satisfaction ratio [0.0–1.0].
    1.0 means all constraints satisfied (or no constraints).
    """
    if not example.constraints:
        return 1.0

    satisfied = 0
    for constraint in example.constraints:
        c = constraint.lower()
        if "under" in c and "words" in c:
            try:
                limit = int(re.search(r"\d+", c).group())
                if len(example.output.split()) <= limit:
                    satisfied += 1
            except (AttributeError, ValueError):
                satisfied += 1
        elif "json" in c:
            if "{" in example.output or "[" in example.output:
                satisfied += 1
        elif any(k in c for k in ["code", "python", "function"]):
            if any(k in example.output for k in ["def ", "class ", "import ", "```"]):
                satisfied += 1
        else:
            satisfied += 1

    total = len(example.constraints)
    return max(0.0, min(1.0, round(satisfied / total, 4)))
