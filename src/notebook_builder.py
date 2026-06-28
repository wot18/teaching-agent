import logging
from pathlib import Path

import nbformat
from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell

from .models import ExerciseSet
from .config_loader import get_app_config

logger = logging.getLogger(__name__)


def build_notebook(exercise_set: ExerciseSet, output_path: str | Path) -> Path:
    """Build a student-facing Jupyter Notebook from an ExerciseSet.

    Layout:
      Cell 0: name / student-id / class input
      Cell 1..N: for each question — one cell for the question text,
                 one cell for the scaffold (fill-in-the-blank) answer area.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    nb = new_notebook()
    nb.metadata.kernelspec = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    nb.metadata.language_info = {"name": "python", "version": "3.10.0"}

    app_cfg = get_app_config()
    course_name = exercise_set.course_name or app_cfg.get("course_name", "人工智能基础")
    chapter = exercise_set.chapter or "课程作业"

    header = (
        f"# {course_name} {chapter} —— 作业\n\n"
        f"**{app_cfg.get('university', '')} {app_cfg.get('department', '')}**\n\n"
        f"- 姓名：？？？？？\n\n"
        f"- 学号：？？？？？\n\n"
        f"- 班级：？？？？？\n\n"
        f"---\n\n"
        f"**说明：** 请在各题作答区中的\"?????\"或\"？？？？？\"处填写答案。"
        f"推理题要求标注每一步所使用的规则名称。计算题需写出完整计算过程。"
    )
    nb.cells.append(new_markdown_cell(header))

    for ex in exercise_set.questions:
        nb.cells.append(new_markdown_cell(f"### 第 {ex.id[1:]} 题\n\n{ex.question_text}"))

        for cell in ex.scaffold_cells:
            content = f"### 解答\n\n{cell.content}"
            if cell.cell_type == "code":
                nb.cells.append(new_code_cell(content))
            else:
                nb.cells.append(new_markdown_cell(content))

    with open(output_path, "w", encoding="utf-8") as f:
        nbformat.write(nb, f)

    logger.info(f"Notebook written to {output_path}")
    return output_path


def build_teacher_markdown(exercise_set: ExerciseSet) -> str:
    """Build a teacher-facing Markdown document with full answers for review."""
    app_cfg = get_app_config()
    course_name = exercise_set.course_name or app_cfg.get("course_name", "人工智能基础")
    chapter = exercise_set.chapter or "课程作业"

    lines = [f"# {course_name} {chapter} —— 作业答案与分析说明\n"]
    lines.append(f"**{app_cfg.get('university', '')} {app_cfg.get('department', '')}**\n\n---")

    for ex in exercise_set.questions:
        lines.append(f"\n### 第 {ex.id[1:]} 题\n")
        lines.append(f"#### 问题回顾\n\n{ex.question_text}\n")
        lines.append(f"---\n\n#### 解答过程\n\n{ex.standard_answer}\n\n---")

    lines.append("\n## 答案汇总\n")
    lines.append("| 题号 | 类型 | 答案概要 |")
    lines.append("|:----:|:----:|----------|")
    for ex in exercise_set.questions:
        answer_preview = ex.standard_answer[:50].replace("\n", " ") + "..."
        lines.append(f"| {ex.id[1:]} | {ex.type.value} | {answer_preview} |")

    lines.append(f"\n---\n\n*{app_cfg.get('university', '')} {app_cfg.get('department', '')} {course_name}课程作业答案*")

    return "\n".join(lines)
