#!/usr/bin/env python3
"""Build the website's copyable teaching material from repository prompts."""

import argparse
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def code_block(path: Path) -> str:
    match = re.search(r"```text\n(.*?)\n```", path.read_text(encoding="utf-8"), re.S)
    if match is None:
        raise ValueError(f"No text example found in {path.relative_to(ROOT)}")
    return match.group(1).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="教材のMarkdownからWeb用JSONを生成")
    parser.add_argument("--output", type=Path, default=ROOT / "website" / "prompts.json")
    args = parser.parse_args()
    instructions = (ROOT / "prompts" / "secretary-instructions.md").read_text(encoding="utf-8").strip()
    # The combined prompt includes the context already, so avoid an unnecessary
    # initial question before performing the beginner's first practice exercise.
    practice = instructions + "\n\n次の架空の予定で練習します。提供済みの条件で整理し、不足は最後に示してください。\n\n" + code_block(ROOT / "examples" / "first-day.md")
    tasks = []
    for task_id, label, filename in [
        ("daily", "今日の順番", "daily-plan.md"),
        ("email", "メールの読み取り", "read-email.md"),
        ("writing", "返信の文章", "review-message.md"),
        ("handoff", "引き継ぎ", "prepare-handoff.md"),
    ]:
        tasks.append({"id": task_id, "label": label, "prompt": instructions + "\n\n" + code_block(ROOT / "prompts" / filename)})
    data = {
        "instructions": instructions,
        "practice": practice,
        "correction": "元の入力と回答を照合してください。入力にない締切・担当・約束は追加せず、不明として整理し直してください。今日の締切と不在中の締切、固定予定、未担当の仕事をもう一度確認してください。",
        "tasks": tasks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Created {args.output} with {len(tasks)} task prompts")


if __name__ == "__main__":
    main()
