import json
import logging
import re
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from .llm_client import LLMClient
from .models import (
    ExerciseSet, Exercise,
    QuestionGrade, GradingResult
)
from .blank_extractor import extract_question_cells

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

_FALLBACK_P3 = """你是一位宽容且严格的大学人工智能课程助教，正在评价学生一整道题的作答。

评分原则：
1. 宽容：学生可能把所有步骤答案写在同一个位置、改写题目、没有严格按"留白"填写，只要逻辑链条连贯且与标准答案等价，请酌情给高分。
2. 严格：逻辑错误、推理缺步、计算错误必须扣分并指出。
3. score 范围 0.0–1.0。
4. feedback 用中文，具体指出对错和改进建议。

输入（JSON）：
{
  "question": "题目",
  "standard_answer": "标准答案",
  "student_answer": "该题作答区所有 cell 的完整原文（含 BLANK 标记）"
}

输出（JSON）：
{"score": 0.8, "feedback": "具体反馈", "confidence": 0.9}

请评价：
"""


class _GradeResponse(BaseModel):
    score: float
    feedback: str
    confidence: float = 0.8


class GradingAgent:
    def __init__(self, llm_client: LLMClient | None = None):
        self.llm = llm_client or LLMClient()
        prompt_path = _PROMPTS_DIR / "p3_grade_answer.md"
        if prompt_path.exists():
            self._prompt = prompt_path.read_text(encoding="utf-8")
        else:
            self._prompt = _FALLBACK_P3

    def _format_student_answer(self, cells: list[dict]) -> str:
        parts: list[str] = []
        for c in cells:
            tag = "CODE" if c.get("cell_type") == "code" else "MD"
            parts.append(f"--- cell ({tag}) ---\n{c.get('content', '')}")
        return "\n\n".join(parts)

    @staticmethod
    def _has_placeholder(student_answer: str) -> bool:
        return bool(re.search(r"[？\?]{3,}", student_answer))

    def grade_question(
        self,
        exercise: Exercise,
        student_cells: list[dict],
    ) -> QuestionGrade:
        """Grade a single question holistically.

        All student answer-area cells for this question are concatenated
        and sent to the LLM together with the question and standard
        answer, so the LLM judges the answer regardless of whether the
        student filled in the BLANK regions in the original layout.
        """
        student_answer = self._format_student_answer(student_cells or [])

        if not student_answer.strip() or all(
            not c.get("content", "").strip() for c in (student_cells or [])
        ):
            return QuestionGrade(
                question_id=exercise.id,
                step_grades=[],
                total_score=0.0,
                total_max=1.0,
                feedback="未作答：该题作答区为空。",
            )

        if self._has_placeholder(student_answer):
            logger.info(
                "%s: placeholder detected, auto-grade 0.0 (skip LLM)",
                exercise.id,
            )
            return QuestionGrade(
                question_id=exercise.id,
                step_grades=[],
                total_score=0.0,
                total_max=1.0,
                feedback=(
                    "该题作答区仍含有占位符（？？？？？或 ?????），"
                    "说明学生未完整填写所有留白，按 0 分计。"
                ),
            )

        input_data = {
            "question": exercise.question_text,
            "standard_answer": exercise.standard_answer,
            "student_answer": student_answer,
        }

        try:
            result = self.llm.chat_json(
                system_prompt="你是一个严格的JSON输出器。只输出合法JSON，用双引号，不加注释，不加说明文字，不要尾逗号。",
                user_prompt=self._prompt + json.dumps(input_data, ensure_ascii=False, indent=2),
                response_model=_GradeResponse,
                temperature=0.2,
            )
            score = min(max(result.score, 0.0), 1.0)
            return QuestionGrade(
                question_id=exercise.id,
                step_grades=[],
                total_score=score,
                total_max=1.0,
                feedback=result.feedback,
            )
        except Exception as e:
            logger.error(f"Grading failed for {exercise.id}: {e}")
            return QuestionGrade(
                question_id=exercise.id,
                step_grades=[],
                total_score=0.0,
                total_max=1.0,
                feedback=f"评分出错：{e}",
            )

    def grade_submission(
        self,
        student_nb_path: str,
        exercise_set: ExerciseSet,
    ) -> GradingResult:
        """Grade a complete student submission."""
        student_questions = extract_question_cells(student_nb_path)
        n_questions = len(exercise_set.questions)
        points_per_question = 100.0 / max(n_questions, 1)

        question_grades = []
        for exercise in exercise_set.questions:
            cells = student_questions.get(exercise.id, [])
            qg = self.grade_question(exercise, cells)
            qg.total_score = qg.total_score * points_per_question
            qg.total_max = points_per_question
            question_grades.append(qg)

        result = GradingResult(
            student_file=str(student_nb_path),
            question_grades=question_grades,
            graded_at=datetime.now().isoformat(),
        )
        result.compute_totals()
        return result