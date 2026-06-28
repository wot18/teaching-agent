#!/usr/bin/env python3
"""Standalone CLI script for grading student submissions."""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config_loader import get_llm_config
from src.llm_client import LLMClient
from src.models import ExerciseSet
from src.grading_agent import GradingAgent


def main():
    parser = argparse.ArgumentParser(description="Grade student Jupyter Notebook submissions")
    parser.add_argument("student_nb", help="Path to student's .ipynb file")
    parser.add_argument("standard_json", help="Path to standard answer ExerciseSet JSON file")
    parser.add_argument("-o", "--output", help="Output file path (default: stdout)", default=None)
    parser.add_argument("--markdown", help="Also generate Markdown report at this path", default=None)
    parser.add_argument("--config", help="Path to config.yaml", default=None)
    args = parser.parse_args()

    # Load standard answers
    with open(args.standard_json, "r", encoding="utf-8") as f:
        exercise_data = json.load(f)
    exercise_set = ExerciseSet.model_validate(exercise_data)

    # Grade
    llm_config = get_llm_config()
    if args.config:
        import yaml
        with open(args.config, "r", encoding="utf-8") as f:
            override = yaml.safe_load(f)
        llm_config.update(override.get("llm", {}))

    llm = LLMClient(llm_config)
    agent = GradingAgent(llm)
    result = agent.grade_submission(args.student_nb, exercise_set)

    # Output JSON
    result_json = result.model_dump_json(indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(result_json, encoding="utf-8")
        print(f"Grading result saved to {args.output}")
    else:
        print(result_json)

    # Optional Markdown report
    if args.markdown:
        report = _generate_markdown_report(result, exercise_set)
        Path(args.markdown).write_text(report, encoding="utf-8")
        print(f"Markdown report saved to {args.markdown}")

    # Print summary
    print(f"\n总分: {result.total_score:.1f} / {result.total_max:.1f}")


def _generate_markdown_report(result, exercise_set) -> str:
    lines = ["# 作业批改报告\n"]
    lines.append(f"**学生文件**: {result.student_file}\n")
    lines.append(f"**批改时间**: {result.graded_at}\n\n")
    lines.append(f"**总分: {result.total_score:.1f} / {result.total_max:.1f}**\n\n---\n")

    for qg in result.question_grades:
        q_num = qg.question_id.replace("q", "")
        lines.append(f"\n### 第 {q_num} 题（得分: {qg.total_score:.1f}/{qg.total_max:.1f}）\n")
        lines.append(qg.feedback)
        lines.append("\n---")

    lines.append(f"\n\n---\n*批改报告 - 生成时间: {result.graded_at}*")
    return "\n".join(lines)


if __name__ == "__main__":
    main()