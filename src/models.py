"""Pydantic models for the Teaching Agent system.

Defines the structured data schemas for:
- Exercise sets (questions + scaffolds + answers + rubrics)
- Blank regions (for student fill-in areas)
- Grading results
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class QuestionType(str, Enum):
    LOGICAL_REASONING = "logical_reasoning"
    PROOF = "proof"
    CALCULATION = "calculation"
    PROGRAMMING = "programming"


class BlankRegion(BaseModel):
    """A single fill-in-the-blank area inside a scaffold cell."""
    blank_id: str = Field(
        ...,
        description="Unique identifier for this blank, e.g. 'q1_step3'",
    )
    description: str = Field(
        ...,
        description="What the student should fill in at this blank",
    )


class ScaffoldCell(BaseModel):
    """One cell in the scaffold (question or answer cell for the notebook)."""
    cell_type: Literal["markdown", "code"] = "markdown"
    content: str = Field(
        ...,
        description="Cell content with BLANK markers for student fill-in areas",
    )
    has_blanks: bool = False
    blank_ids: list[str] = Field(
        default_factory=list,
        description="IDs of blanks present in this cell",
    )


class RubricItem(BaseModel):
    """Scoring rubric for one blank / step."""
    step: str = Field(
        ...,
        description="blank_id this rubric item scores",
    )
    weight: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Weight of this step (0.0–1.0), all weights per question should sum to 1.0",
    )
    description: str = Field(
        ...,
        description="What is being evaluated at this step",
    )

class Exercise(BaseModel):
    """A single exercise with question, scaffold, answer, and rubric."""
    id: str = Field(..., description="Question identifier, e.g. 'q1'")
    type: QuestionType = QuestionType.LOGICAL_REASONING
    difficulty: int = Field(2, ge=1, le=3, description="Difficulty 1–3")
    knowledge_points: list[str] = Field(
        default_factory=list,
        description="Knowledge areas this question covers",
    )
    question_text: str = Field(
        ...,
        description="Full question description in Markdown",
    )
    scaffold_cells: list[ScaffoldCell] = Field(
        default_factory=list,
        description="Cells to render in the student notebook (with blanks)",
    )
    standard_answer: str = Field(
        ...,
        description="Complete standard answer for grading reference",
    )
    rubric: list[RubricItem] = Field(
        default_factory=list,
        description="Scoring rubric items",
    )

class ExerciseSet(BaseModel):
    """A complete set of exercises for one chapter / PDF."""
    course_name: str = "人工智能基础"
    chapter: str = ""
    questions: list[Exercise] = Field(default_factory=list)

    def get_total_weight(self, question_id: str) -> float:
        """Return the sum of rubric weights for a question."""
        for q in self.questions:
            if q.id == question_id:
                return sum(r.weight for r in q.rubric)
        return 0.0

class KnowledgePoint(BaseModel):
    """A single knowledge point extracted from the PDF."""
    name: str
    category: str = Field("", description="e.g. '知识表示', '推理', '搜索'")
    summary: str
    key_formulas: list[str] = Field(default_factory=list)
    related_concepts: list[str] = Field(default_factory=list)


class KnowledgeExtraction(BaseModel):
    """Result of knowledge extraction from a PDF."""
    course_title: str = ""
    chapter_title: str = ""
    knowledge_points: list[KnowledgePoint] = Field(default_factory=list)
    overall_summary: str = ""

class StepGrade(BaseModel):
    """Grading result for a single blank/step."""
    blank_id: str
    score: float = Field(..., ge=0.0, le=1.0, description="Normalized score 0.0–1.0")
    max_score: float = Field(1.0, description="Max possible score for this step")
    feedback: str = ""
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="LLM confidence in this grade")


class QuestionGrade(BaseModel):
    """Grading result for a single question (aggregated from steps)."""
    question_id: str
    step_grades: list[StepGrade] = Field(default_factory=list)
    total_score: float = 0.0
    total_max: float = 100.0
    feedback: str = ""


class GradingResult(BaseModel):
    """Complete grading result for a student submission."""
    student_file: str = ""
    exercise_set_id: str = ""
    question_grades: list[QuestionGrade] = Field(default_factory=list)
    total_score: float = 0.0
    total_max: float = 100.0
    overall_feedback: str = ""
    graded_at: str = ""

    def compute_totals(self) -> None:
        """Recompute total scores from question grades."""
        self.total_score = sum(qg.total_score for qg in self.question_grades)
        self.total_max = sum(qg.total_max for qg in self.question_grades)
