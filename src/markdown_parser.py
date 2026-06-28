from __future__ import annotations

import logging
import re
from pathlib import Path

from .models import (
    Exercise,
    ExerciseSet,
    QuestionType,
    RubricItem,
    ScaffoldCell,
)

logger = logging.getLogger(__name__)

_TYPE_MAP = {
    "逻辑推理": QuestionType.LOGICAL_REASONING,
    "计算": QuestionType.CALCULATION,
    "证明": QuestionType.PROOF,
    "编程": QuestionType.PROGRAMMING,
    "综合": QuestionType.LOGICAL_REASONING,
    "logical_reasoning": QuestionType.LOGICAL_REASONING,
    "calculation": QuestionType.CALCULATION,
    "proof": QuestionType.PROOF,
    "programming": QuestionType.PROGRAMMING,
}

_SCAFFOLD_RATIO = 0.4


def _parse_type(type_str: str) -> QuestionType:
    for key, qtype in _TYPE_MAP.items():
        if key in type_str:
            return qtype
    return QuestionType.LOGICAL_REASONING


def _extract_course_info(md: str) -> tuple[str, str]:
    title_pat = re.compile(r"^#\s+(.+?)(?:\s*[-—]\s*(.+))?$", re.MULTILINE)
    m = title_pat.search(md)
    if m:
        return m.group(1).strip(), (m.group(2) or "").strip()
    return "课程", ""


def _strip_header(md: str) -> str:
    """Strip the document header before the first question.

    LLM-generated answers contain Python comments (e.g. ``# 测试``)
    inside fenced code blocks that look like Markdown headings.
    We pre-compute the character ranges of all fenced code blocks
    and skip any heading match that falls inside one.
    """
    code_ranges: list[tuple[int, int]] = []
    for m in re.finditer(r"```.*?```", md, re.DOTALL):
        code_ranges.append((m.start(), m.end()))

    def _in_code(pos: int) -> bool:
        return any(s <= pos < e for s, e in code_ranges)

    end = 0
    for m in re.finditer(r"^#{1,2}\s+.+$", md, re.MULTILINE):
        if _in_code(m.start()):
            continue
        if not re.search(r"第\d+题|解答", m.group()):
            end = m.end()
        else:
            break
    return md[end:].strip() if end else md.strip()


def _split_by_separator(md: str) -> list[str]:
    blocks = re.split(r"\n\s*---+\s*\n", md)
    blocks = [b.strip() for b in blocks if b.strip()]
    if blocks and not re.search(r"解答", blocks[0]):
        blocks = blocks[1:] if len(blocks) > 1 else blocks
    return blocks


def _clean_question_text(text: str) -> str:
    text = re.sub(r"^###\s*第\d+题\s*.*$\n?", "", text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^\s*---+\s*\n", "", text)
    text = text.strip()
    return text


def _split_question_answer(block: str) -> tuple[str, str]:
    answer_pat = re.compile(r"^#{1,4}\s*解答", re.MULTILINE)
    m = answer_pat.search(block)
    if m:
        return _clean_question_text(block[:m.start()]), block[m.end():].strip()
    return _clean_question_text(block), ""


def _extract_type_hint(text: str) -> str:
    m = re.search(r"[（(]\s*([^)）]+?)\s*[)）]", text[:200])
    if m:
        return m.group(1).strip()
    return ""


def _extract_difficulty(text: str) -> int:
    m = re.search(r"难度\s*[:：]?\s*(\d)", text[:200])
    if m:
        return min(3, max(1, int(m.group(1))))
    return 2


def _extract_knowledge_points(text: str) -> list[str]:
    kp_pat = re.compile(r"\*\*知识点\*\*[:：]\s*(.+)")
    m = kp_pat.search(text)
    if m:
        return [k.strip() for k in re.split(r"[,，、]", m.group(1)) if k.strip()]
    return []


def _build_scaffold_and_rubric(
    question_text: str, answer: str, q_id: str, is_code: bool = False,
) -> tuple[list[ScaffoldCell], list[RubricItem]]:
    if not answer:
        cell_type = "code" if is_code else "markdown"
        blank_id = f"{q_id}_step1"
        marker_open = f"# BLANK_START:{blank_id}" if is_code else f"<!-- BLANK_START:{blank_id} -->"
        marker_close = f"# BLANK_END:{blank_id}" if is_code else f"<!-- BLANK_END:{blank_id} -->"
        placeholder = "?????" if is_code else "？？？？？"
        return (
            [ScaffoldCell(
                cell_type=cell_type,
                content=f"{marker_open}\n{placeholder}\n{marker_close}",
                has_blanks=True,
                blank_ids=[blank_id],
            )],
            [RubricItem(step=blank_id, weight=1.0, description="完整作答")],
        )

    code_pat = re.compile(r"```python\s*\n(.*?)```", re.DOTALL)
    code_match = code_pat.search(answer)

    if code_match and (is_code or len(code_match.group(1).strip().split("\n")) > 3):
        full_code = code_match.group(1).strip()
        lines = [l for l in full_code.split("\n") if l.strip()]
        n_show = max(1, int(len(lines) * _SCAFFOLD_RATIO))
        blank_lines = lines[n_show:]
        n_blanks = max(1, len(blank_lines))

        blank_ids = [f"{q_id}_step{i+1}" for i in range(n_blanks)]
        scaffold_parts = lines[:n_show]
        for i, _line in enumerate(blank_lines):
            bid = blank_ids[i]
            scaffold_parts.append(f"# BLANK_START:{bid}")
            scaffold_parts.append("?????")
            scaffold_parts.append(f"# BLANK_END:{bid}")

        scaffold_content = "```python\n" + "\n".join(scaffold_parts) + "\n```"
        weight = round(1.0 / n_blanks, 2)
        remainder = round(max(0.0, 1.0 - weight * (n_blanks - 1)), 2)
        rubric = [
            RubricItem(
                step=blank_ids[i],
                weight=weight if i < n_blanks - 1 else remainder,
                description=f"代码第{n_show + i + 1}行",
            )
            for i in range(n_blanks)
        ]
        return (
            [ScaffoldCell(cell_type="code", content=scaffold_content, has_blanks=True, blank_ids=blank_ids)],
            rubric,
        )

    steps = re.split(r"\n(?=(?:步骤\s*\d+|第[一二三四五六七八九十]+步|[①②③④⑤⑥⑦⑧⑨⑩]))", answer)
    steps = [s.strip() for s in steps if s.strip()]

    if len(steps) <= 1:
        paragraphs = [p.strip() for p in answer.split("\n\n") if p.strip()]
        if len(paragraphs) >= 3:
            steps = paragraphs
        else:
            blank_id = f"{q_id}_step1"
            marker_open = f"<!-- BLANK_START:{blank_id} -->"
            marker_close = f"<!-- BLANK_END:{blank_id} -->"
            return (
                [ScaffoldCell(
                    cell_type="markdown",
                    content=f"{marker_open}\n？？？？？\n{marker_close}",
                    has_blanks=True,
                    blank_ids=[blank_id],
                )],
                [RubricItem(step=blank_id, weight=1.0, description="完整作答")],
            )

    n_show = max(1, int(len(steps) * _SCAFFOLD_RATIO))
    shown = steps[:n_show]
    hidden = steps[n_show:]
    n_blanks = len(hidden)
    blank_ids = [f"{q_id}_step{i+1}" for i in range(n_blanks)]

    scaffold_md = "\n\n".join(shown) + "\n\n"
    for i, _h in enumerate(hidden):
        bid = blank_ids[i]
        scaffold_md += f"<!-- BLANK_START:{bid} -->\n？？？？？\n<!-- BLANK_END:{bid} -->\n\n"

    weight = round(1.0 / n_blanks, 2)
    remainder = round(max(0.0, 1.0 - weight * (n_blanks - 1)), 2)
    rubric = [
        RubricItem(
            step=blank_ids[i],
            weight=weight if i < n_blanks - 1 else remainder,
            description=hidden[i][:30],
        )
        for i in range(n_blanks)
    ]

    return (
        [ScaffoldCell(cell_type="markdown", content=scaffold_md.strip(), has_blanks=True, blank_ids=blank_ids)],
        rubric,
    )


def _strip_think_tags(md: str) -> str:
    return re.sub(r"<think>.*?</think>", "", md, flags=re.DOTALL)


def parse_exercise_markdown(
    exercise_md: str,
    knowledge_md: str = "",
) -> ExerciseSet:
    course_name, chapter = _extract_course_info(knowledge_md) if knowledge_md else ("课程", "")
    exercise_md = _strip_think_tags(exercise_md)
    body = _strip_header(exercise_md)
    blocks = _split_by_separator(body)

    if not blocks:
        logger.warning("No question blocks found after splitting by ---")
        return ExerciseSet(course_name=course_name or "课程作业", chapter=chapter or "")

    exercises = []
    for idx, block in enumerate(blocks, start=1):
        q_id = f"q{idx}"
        question_part, answer_part = _split_question_answer(block)
        type_hint = _extract_type_hint(question_part)
        q_type = _parse_type(type_hint) if type_hint else QuestionType.LOGICAL_REASONING
        difficulty = _extract_difficulty(question_part)
        kps = _extract_knowledge_points(question_part)
        if not kps:
            kps = _extract_knowledge_points(block)

        is_code = q_type == QuestionType.PROGRAMMING or bool(re.search(r"```python", answer_part))
        scaffold_cells, rubric = _build_scaffold_and_rubric(question_part, answer_part, q_id, is_code)

        exercises.append(Exercise(
            id=q_id,
            type=q_type,
            difficulty=difficulty,
            knowledge_points=kps,
            question_text=question_part,
            scaffold_cells=scaffold_cells,
            standard_answer=answer_part,
            rubric=rubric,
        ))

    return ExerciseSet(
        course_name=course_name or "课程作业",
        chapter=chapter or "",
        questions=exercises,
    )


def save_markdown(content: str, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    logger.info("Saved Markdown to %s", path)
    return path
