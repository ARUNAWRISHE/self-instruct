"""Abstract base classes defining the contract for every AIDEP engine."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from aidep.core.models import (
    GeneratedInstruction,
    InstructionMetadata,
    PipelineResult,
    QualityMetrics,
    SeedTask,
    TrainingExample,
    ValidationResult,
)


class BaseKnowledgeEngine(ABC):
    """Manages the Knowledge Foundation: seeds, prompts, domains, constraints, taxonomy."""

    @abstractmethod
    def load_seeds(self, path: str) -> List[SeedTask]:
        """Parse a JSONL file and return SeedTask objects."""

    @abstractmethod
    def get_all_seeds(self) -> List[SeedTask]:
        """Return all seeds currently stored."""


class BaseInstructionEngine(ABC):
    """Generates new instruction candidates from seed tasks."""

    @abstractmethod
    def generate(self, seeds: List[SeedTask], count: int) -> List[GeneratedInstruction]:
        """Generate `count` instruction candidates from the seed pool."""


class BaseIntelligenceEngine(ABC):
    """Analyzes each instruction and produces structured task metadata."""

    @abstractmethod
    def analyze(self, instruction: GeneratedInstruction) -> InstructionMetadata:
        """Classify task type, domain, difficulty, reasoning, output format, and complexity."""


class BaseExampleEngine(ABC):
    """Converts an analyzed instruction into a complete training example."""

    @abstractmethod
    def generate_example(
        self,
        instruction: GeneratedInstruction,
        metadata: InstructionMetadata,
    ) -> TrainingExample:
        """Generate input, output, and metadata for a training sample."""


class BaseValidationEngine(ABC):
    """Validates training examples against quality and uniqueness criteria."""

    @abstractmethod
    def validate(
        self,
        example: TrainingExample,
        existing: List[TrainingExample],
    ) -> ValidationResult:
        """Return ValidationResult indicating pass/fail with reasons."""


class BaseQualityEngine(ABC):
    """Scores validated training examples on multiple quality dimensions."""

    @abstractmethod
    def score(
        self,
        example: TrainingExample,
        metadata: InstructionMetadata,
    ) -> QualityMetrics:
        """Compute and return a QualityMetrics object."""


class BaseDatasetEngine(ABC):
    """Manages storage, export, and reporting of the final dataset."""

    @abstractmethod
    def export(
        self,
        examples: List[TrainingExample],
        version: str,
        output_path: str,
    ) -> str:
        """Export approved examples to JSONL and return the file path."""


class BaseOrchestrator(ABC):
    """Thin workflow coordinator that sequences engine calls."""

    @abstractmethod
    def run_pipeline(self, seed_ids: List[int]) -> PipelineResult:
        """Execute the full AIDEP pipeline end-to-end."""
