import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict

from pydantic import BaseModel

from .llm_client import LLMClient
from .models import (
    ExerciseSet, Exercise, RubricItem,
    StepGrade, QuestionGrade, GradingResult
)
from .blank_extractor import extract_blanks

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

_FALLBACK_P3 = """你是一位宽容且严格的大学人工智能课程助教。你的任务是评价学生的作业答案。

评分原则：
1. 宽容：学生可能使用了不同的变量名或略有不同的自然语言表述，只要逻辑链条是连贯且等价的，请酌情给满分
2. 严格：如果逻辑有缺失或推理有错误，必须指出具体在哪一步出了问题
3. 评分范围为0.0到1.0（标准化分数）
4. 必须给出具体的诊断反馈

输入（JSON）：
{"question": "题目", "standard_answer": "标准答案", "rubric_item": {"step": "ID", "description": "要点"}, "student_answer": "学生作答"}

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

    def grade_blank(
        self,
        question: str,
        standard_answer: str,
        rubric_item: RubricItem,
        student_answer: str,
    ) -> StepGrade:
        """Grade a single blank/step using LLM semantic comparison."""
        if not student_answer.strip():
            return StepGrade(
                blank_id=rubric_item.step,
                score=0.0,
                max_score=1.0,
                feedback="该步骤未作答。",
                confidence=1.0,
            )

        input_data = {
            "question": question,
            "standard_answer": standard_answer,
            "rubric_item": {"step": rubric_item.step, "description": rubric_item.description},
            "student_answer": student_answer,
        }

        try:
            result = self.llm.chat_json(
                system_prompt="你是一个严格的JSON输出器。只输出合法JSON，用双引号，不加注释，不加说明文字，不要尾逗号。",
                user_prompt=self._prompt + json.dumps(input_data, ensure_ascii=False, indent=2),
                response_model=_GradeResponse,
                temperature=0.2,
            )
            return StepGrade(
                blank_id=rubric_item.step,
                score=min(max(result.score, 0.0), 1.0),
                max_score=1.0,
                feedback=result.feedback,
                confidence=result.confidence,
            )
        except Exception as e:
            logger.error(f"Grading failed for {rubric_item.step}: {e}")
            return StepGrade(
                blank_id=rubric_item.step,
                score=0.0,
                max_score=1.0,
                feedback=f"评分出错：{e}",
                confidence=0.0,
            )

    def grade_question(
        self,
        exercise: Exercise,
        student_answers: Dict[str, str],
    ) -> QuestionGrade:
        """Grade all steps of a single question."""
        step_grades = []
        for rubric_item in exercise.rubric:
            student_ans = student_answers.get(rubric_item.step, "")
            sg = self.grade_blank(
                question=exercise.question_text,
                standard_answer=exercise.standard_answer,
                rubric_item=rubric_item,
                student_answer=student_ans,
            )
            step_grades.append(sg)

        # Weighted score for this question
        total_weight = sum(r.weight for r in exercise.rubric)
        if total_weight > 0 and step_grades:
            weighted_score = sum(
                sg.score * r.weight for sg, r in zip(step_grades, exercise.rubric)
            ) / total_weight
        else:
            weighted_score = 0.0

        # Collect feedback
        feedback_parts = []
        for sg, r in zip(step_grades, exercise.rubric):
            feedback_parts.append(f"**{r.description}**: {sg.feedback} (得分: {sg.score:.1f})")

        return QuestionGrade(
            question_id=exercise.id,
            step_grades=step_grades,
            total_score=weighted_score,
            total_max=1.0,
            feedback="\n".join(feedback_parts),
        )

    def grade_submission(
        self,
        student_nb_path: str,
        exercise_set: ExerciseSet,
    ) -> GradingResult:
        """Grade a complete student submission."""
        student_answers = extract_blanks(student_nb_path)
        n_questions = len(exercise_set.questions)
        points_per_question = 100.0 / max(n_questions, 1)

        question_grades = []
        for exercise in exercise_set.questions:
            qg = self.grade_question(exercise, student_answers)
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