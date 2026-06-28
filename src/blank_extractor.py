import re
import logging
from pathlib import Path
from typing import Dict

import nbformat

logger = logging.getLogger(__name__)

_MD_BLANK_PATTERN = re.compile(
    r'<!--\s*BLANK_START:(\w+)\s*-->\s*(.*?)\s*<!--\s*BLANK_END:\1\s*-->',
    re.DOTALL
)

_CODE_BLANK_PATTERN = re.compile(
    r'#\s*BLANK_START:(\w+)\s*\n(.*?)#\s*BLANK_END:\1',
    re.DOTALL
)

_QUESTION_HEADER_PATTERN = re.compile(r'^\s*###\s*第\s*(\d+)\s*题', re.MULTILINE)


def extract_blanks(notebook_path: str | Path) -> Dict[str, str]:
    """Extract student answers from blank regions in a Jupyter Notebook.

    Returns a dict mapping blank_id -> student_answer_text.
    """
    notebook_path = Path(notebook_path)
    if not notebook_path.exists():
        raise FileNotFoundError(f"Notebook not found: {notebook_path}")

    with open(notebook_path, "r", encoding="utf-8") as f:
        nb = nbformat.read(f, as_version=4)

    answers: Dict[str, str] = {}

    for cell in nb.cells:
        source = cell.source if hasattr(cell, 'source') else ""
        cell_type = cell.cell_type if hasattr(cell, 'cell_type') else "markdown"

        if cell_type == "code":
            matches = _CODE_BLANK_PATTERN.findall(source)
        else:
            matches = _MD_BLANK_PATTERN.findall(source)

        for blank_id, content in matches:
            content = content.strip()
            if content and not re.match(r'^[？?]+$', content):
                answers[blank_id] = content
            else:
                answers[blank_id] = ""

    logger.info(f"Extracted {len(answers)} blank answers from {notebook_path.name}")
    return answers


def get_blank_ids(notebook_path: str | Path) -> list[str]:
    """Get all blank IDs from a notebook without extracting content."""
    notebook_path = Path(notebook_path)
    with open(notebook_path, "r", encoding="utf-8") as f:
        nb = nbformat.read(f, as_version=4)

    blank_ids: list[str] = []
    for cell in nb.cells:
        source = cell.source if hasattr(cell, 'source') else ""
        cell_type = cell.cell_type if hasattr(cell, 'cell_type') else "markdown"

        if cell_type == "code":
            pattern = _CODE_BLANK_PATTERN
        else:
            pattern = _MD_BLANK_PATTERN

        for match in pattern.findall(source):
            blank_ids.append(match[0])

    return blank_ids


def extract_question_cells(notebook_path: str | Path) -> Dict[str, list[dict]]:
    """Group all cells belonging to each question in the student notebook.

    The student notebook is laid out as:
      cell 0   → header (name / id / class)
      cell 2k+1 → question text  ("### 第 N 题 …")
      cell 2k+2 → answer/scaffold cell(s) (one or more, until next question)

    Returns ``{ "q1": [{"cell_type": ..., "content": ...}, …], … }``.
    Each question entry contains every answer-area cell in original order.
    """
    notebook_path = Path(notebook_path)
    if not notebook_path.exists():
        raise FileNotFoundError(f"Notebook not found: {notebook_path}")

    with open(notebook_path, "r", encoding="utf-8") as f:
        nb = nbformat.read(f, as_version=4)

    cells = nb.cells

    header_idxs = [
        i for i, c in enumerate(cells)
        if _QUESTION_HEADER_PATTERN.search(c.source or "")
    ]

    if not header_idxs:
        logger.warning("No ### 第N题 headers found in notebook; cannot split by question")
        return {}

    ranges: list[tuple[str, int, int]] = []
    for k, start in enumerate(header_idxs):
        end = header_idxs[k + 1] if k + 1 < len(header_idxs) else len(cells)
        m = _QUESTION_HEADER_PATTERN.search(cells[start].source)
        if m:
            qnum = int(m.group(1))
            ranges.append((f"q{qnum}", start, end))

    questions: Dict[str, list[dict]] = {}
    for qid, start, end in ranges:
        answer_cells: list[dict] = []
        for c in cells[start + 1:end]:
            answer_cells.append({
                "cell_type": getattr(c, "cell_type", "markdown"),
                "content": c.source or "",
            })
        questions[qid] = answer_cells

    logger.info(
        f"Grouped student cells into {len(questions)} questions: "
        f"{sorted(questions.keys(), key=lambda x: int(x[1:]))}"
    )
    return questions
