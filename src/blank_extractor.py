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
