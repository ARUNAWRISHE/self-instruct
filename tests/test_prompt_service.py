"""Unit tests for PromptLibraryService."""

import pytest
from aidep.services.prompt_service import PromptLibraryService


def test_get_prompt_fallback():
    # Without a DB session, it should fall back to memory defaults
    service = PromptLibraryService(session=None)
    prompt = service.get_prompt("instruction_generation")
    assert "Create 5 unique, diverse" in prompt


def test_get_prompt_unknown():
    service = PromptLibraryService(session=None)
    with pytest.raises(ValueError, match="unknown prompt type"):
        service.get_prompt("unknown_type")
