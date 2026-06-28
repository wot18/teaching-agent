import logging
from pathlib import Path

from .llm_client import LLMClient

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_prompt(filename: str) -> str:
    path = _PROMPTS_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    logger.warning("Prompt file %s not found, using fallback", path)
    return ""


_FALLBACK_P1 = """请从以下课件文本中提取核心知识点，输出为Markdown格式。

要求：
1. 第一行写明课程标题和章节标题
2. 每个知识点用三级标题（###），格式为：### 知识点名称 [分类]
3. 分类从以下选择：知识表示、推理、搜索、不确定推理、深度学习、其他
4. 每个知识点下写50-100字摘要
5. 如有关键公式，用单独一行以"公式："开头列出
6. 最后用"## 总结"写一段200字以内的全章概括

示例格式：

# 课程标题 - 章节标题

### 命题逻辑 [知识表示]

命题是有真假值的陈述句，分为原子命题和复合命题...

公式：$A \\wedge B$, $A \\rightarrow B$

### 假言推理 [推理]

假言推理规则：若$A \\rightarrow B$且$A$为真，则$B$为真...

## 总结

本章介绍了知识表示与推理的基本方法...

课件文本：
"""

_FALLBACK_P2 = """你是一位大学课程的教学专家。请根据以下知识点总结，生成一套作业题。

要求：
1. 共10道题，题目数量根据知识点的重要性分配
2. 所有内容必须使用中文，变量名和函数名可用英文
3. 每道题格式：

### 第N题 (题型) 难度:X

**知识点**: 知识点1, 知识点2

题目描述

### 解答

完整解答过程

4. 题目之间用 --- 分隔
5. 题型标签用中文：(逻辑推理)、(计算)、(证明)、(编程)、(综合)
6. 解答必须完整正确，推理题标注每步规则

知识点总结：
"""


class ExerciseGenerator:
    def __init__(self, llm_client: LLMClient | None = None):
        self.llm = llm_client or LLMClient()
        self._p1 = _load_prompt("p1_extract_knowledge.md") or _FALLBACK_P1
        self._p2 = _load_prompt("p2_generate_exercise.md") or _FALLBACK_P2

    _ZH_SYSTEM = (
        "你必须全程使用中文输出，包括所有说明文字、题目描述、解答过程、规则名称等。"
        "数学公式和代码中的变量名/函数名可以用英文，但所有自然语言内容必须是中文。"
    )

    def extract_knowledge(self, pdf_text: str) -> str:
        """Extract knowledge points from PDF text, return Markdown."""
        user_prompt = self._p1 + pdf_text
        result = self.llm.chat(
            system_prompt="你是一位课程知识分析专家。请按要求的Markdown格式输出知识点总结，不要输出其他内容。"
            + self._ZH_SYSTEM,
            user_prompt=user_prompt,
        )
        logger.info("Extracted knowledge summary (%d chars)", len(result))
        return result

    def generate_exercises(self, knowledge_md: str) -> str:
        """Generate exercise draft from knowledge summary, return Markdown."""
        user_prompt = self._p2 + knowledge_md
        result = self.llm.chat(
            system_prompt="你是一位大学课程的教学专家。请按要求的格式生成作业题，每道题必须包含题目和完整解答。"
            + self._ZH_SYSTEM,
            user_prompt=user_prompt,
            temperature=0.5,
        )
        logger.info("Generated exercise draft (%d chars)", len(result))
        return result

    def full_pipeline(self, pdf_text: str) -> tuple[str, str]:
        """Run the complete pipeline: PDF text → knowledge MD → exercise MD."""
        knowledge_md = self.extract_knowledge(pdf_text)
        exercise_md = self.generate_exercises(knowledge_md)
        return knowledge_md, exercise_md
