#!/usr/bin/env python3
"""Offline mail-draft review copy generator. Never connects or sends mail.

Python >= 3.10; standard library only. Confirmations are user declarations,
not proof that a human reviewed the text. Agents must not self-approve.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata


REQUIRED_FIELDS = {"to", "subject", "body", "attachments", "unresolved"}
OPTIONAL_FIELDS = {"cc", "bcc"}
CONFIRMATIONS = ("recipients", "facts", "tone", "attachments")
MAX_INPUT_BYTES = 1024 * 1024
# Intentionally a small, conservative subset: bare ASCII addresses only.
ADDRESS = re.compile(
    r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+\Z"
)
PLACEHOLDER = re.compile(
    r"\b(?:TODO|TBD|FIXME|PLACEHOLDER)\b"
    r"|要確認|未確認|要修正|ここに(?:入力|記入)"
    r"|\{\{[^{}]+\}\}"
    r"|\[(?:宛先|氏名|名前|会社名|日付|日時|件名|本文|添付名)\]"
    r"|\[(?:宛先|氏名|名前|会社名|日付|日時|時刻|期限|件名|本文|添付名|内容)"
    r"を(?:確認|記入|入力)(?:する|してください)?\]"
    r"|(?:○○|〇〇|●●)",
    re.IGNORECASE,
)
CHECKLIST = (
    ("recipients", "宛先: To / Cc / Bcc の相手・役割・共有してよい範囲を確認する"),
    ("facts", "事実: 元資料と照合し、氏名・日付・曜日・時刻・期限・数字・約束を確認する"),
    ("tone", "表現: 自分の意図と一致し、自然な日本語・敬語・依頼の明確さを確認する"),
    ("attachments", "添付: 実ファイルを開き、内容・版・宛先への共有可否を確認する（なしの場合も確認）"),
)


class DraftError(ValueError):
    """A draft cannot be reviewed or released in its current form."""


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DraftError(f"JSON のキーが重複しています: {key!r}")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise DraftError(f"JSON で使用できない値です: {value}")


def validate_text(value: object, location: str, *, multiline: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DraftError(f"{location} は空でない文字列にしてください。")
    for character in value:
        if multiline and character in "\n\t":
            continue
        if unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"}:
            raise DraftError(f"{location} に許可されていない制御文字・不可視文字があります。")
    return value


def validate_draft(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise DraftError("JSON の最上位はオブジェクトにしてください。")
    missing = REQUIRED_FIELDS - raw.keys()
    unknown = raw.keys() - (REQUIRED_FIELDS | OPTIONAL_FIELDS)
    if missing:
        raise DraftError(f"必須項目がありません: {', '.join(sorted(missing))}")
    if unknown:
        raise DraftError(f"未対応の項目があります: {', '.join(repr(k) for k in sorted(unknown))}")
    draft = dict(raw)
    draft.setdefault("cc", [])
    draft.setdefault("bcc", [])
    for field in ("to", "cc", "bcc", "attachments", "unresolved"):
        values = draft[field]
        if not isinstance(values, list):
            raise DraftError(f"{field} は文字列の配列にしてください。")
        if field == "to" and not values:
            raise DraftError("to には少なくとも 1 件の宛先が必要です。")
        for index, value in enumerate(values):
            location = f"{field}[{index}]"
            value = validate_text(value, location)
            if field in {"to", "cc", "bcc"}:
                local = value.partition("@")[0]
                if (
                    not ADDRESS.fullmatch(value)
                    or local.startswith(".")
                    or local.endswith(".")
                    or ".." in local
                    or len(value) > 254
                    or len(local) > 64
                    or any(len(label) > 63 for label in value.partition("@")[2].split("."))
                ):
                    raise DraftError(f"{location} は表示名を付けず、通常の ASCII メールアドレスにしてください。")
            if field == "attachments" and ("/" in value or "\\" in value or value in {".", ".."}):
                raise DraftError(f"{location} にはパスではなくファイル名だけを記入してください。")
    validate_text(draft["subject"], "subject")
    validate_text(draft["body"], "body", multiline=True)
    return draft


def load_draft(path: Path) -> dict[str, object]:
    # Bound the read itself, even when the path is larger than expected.
    with path.open("rb") as source:
        data = source.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise DraftError("下書きは UTF-8 で 1 MiB 以下にしてください。")
    try:
        raw = json.loads(data.decode("utf-8"), object_pairs_hook=unique_object, parse_constant=reject_constant)
    except UnicodeDecodeError as error:
        raise DraftError("下書きは UTF-8 の JSON ファイルにしてください。") from error
    except DraftError:
        raise
    except (ValueError, RecursionError) as error:
        # Includes JSONDecodeError and Python's limit on huge integer tokens.
        raise DraftError("JSON の構文が不正です。引用符・カンマ・改行の書き方を確認してください。") from error
    return validate_draft(raw)


def content_digest(draft: dict[str, object]) -> str:
    canonical = json.dumps(draft, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def blockers(draft: dict[str, object]) -> list[str]:
    problems: list[str] = []
    if draft["unresolved"]:
        problems.append("unresolved に未解決事項が残っています。元資料や相手に確認してから修正してください。")
    for field, value in draft.items():
        entries = enumerate(value) if isinstance(value, list) else [(None, value)]
        for index, text in entries:
            # Normalize only for detection; preserve the exact draft and digest.
            if PLACEHOLDER.search(unicodedata.normalize("NFKC", text)):
                location = field if index is None else f"{field}[{index}]"
                problems.append(f"{location} に仮置き・確認待ちと思われる表現があります。")
    return problems


def render_copy(draft: dict[str, object], digest: str) -> str:
    attachment_names = "、".join(draft["attachments"]) or "なし"
    return "\n".join(
        [
            "確認用コピー（メール送信機能はありません）",
            f"Content SHA-256: {digest}",
            "",
            f"To: {', '.join(draft['to'])}",
            f"Cc: {', '.join(draft['cc']) or 'なし'}",
            f"Bcc: {', '.join(draft['bcc']) or 'なし'}",
            f"Subject: {draft['subject']}",
            f"添付予定（名前のみ・ファイル内容は未検査）: {attachment_names}",
            "",
            draft["body"],
            "",
        ]
    )


def inspect(draft: dict[str, object]) -> int:
    print(render_copy(draft, content_digest(draft)))
    print("人が確認する項目（自動判定ではありません）:")
    for category, label in CHECKLIST:
        print(f"[ ] {category}: {label}")
    if draft["unresolved"]:
        print("\n未解決事項:")
        for item in draft["unresolved"]:
            print(f"- {item}")
    problems = blockers(draft)
    if problems:
        print("\n書き出し不可:")
        for problem in problems:
            print(f"- {problem}")
        return 2
    print("\n機械的な停止条件は見つかりませんでした。人の確認が終わったという意味ではありません。")
    print("人が全文と実際の添付を確認した後、自分で release を実行してください。AI に自己承認させないでください。")
    return 0


def release(draft: dict[str, object], args: argparse.Namespace) -> int:
    problems = blockers(draft)
    if problems:
        raise DraftError(" / ".join(problems))
    digest = content_digest(draft)
    if args.reviewed_sha256 != digest:
        raise DraftError("SHA-256 が一致しません。現在の下書きを inspect し、人が全項目を再確認してください。")
    if len(args.confirm) != len(CONFIRMATIONS) or set(args.confirm) != set(CONFIRMATIONS):
        raise DraftError("4 項目を人が確認し、各 --confirm を 1 回ずつ指定してください: " + ", ".join(CONFIRMATIONS))
    # Exclusive creation also refuses an existing symlink; no overwrite is allowed.
    with args.output.open("x", encoding="utf-8", newline="\n") as destination:
        destination.write(render_copy(draft, digest))
    print("確認用コピーを書き出しました。メールアプリへ手作業で転記し、宛先・本文・実際の添付を再確認して送信してください。")
    print("このコマンドは通信・送信を行っていません。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="送信せず、オフラインでメール下書きの確認用コピーを作ります。")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect", help="下書き・内容 ID・人の確認項目を表示")
    inspect_parser.add_argument("draft", type=Path, help="UTF-8 の下書き JSON")
    release_parser = subparsers.add_parser("release", help="人の確認宣言後にテキストを書き出す（送信しない）")
    release_parser.add_argument("draft", type=Path, help="UTF-8 の下書き JSON")
    release_parser.add_argument("--reviewed-sha256", required=True, help="人が確認した inspect 結果の SHA-256")
    release_parser.add_argument("--confirm", action="append", choices=CONFIRMATIONS, default=[], help="人が確認した項目。4 項目すべてを各 1 回指定")
    release_parser.add_argument("--output", required=True, type=Path, help="新規の確認用 .txt ファイル（既存ファイル不可）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        draft = load_draft(args.draft)
        if args.command == "inspect":
            return inspect(draft)
        return release(draft, args)
    except DraftError as error:
        print(f"確認を停止しました: {error}", file=sys.stderr)
        return 2
    except FileExistsError:
        print("書き出し先はすでに存在します。上書きせず、別のファイル名を指定してください。", file=sys.stderr)
        return 3
    except OSError:
        print("ファイルの読み書きに失敗しました。パス・親フォルダの存在・アクセス権を確認してください。", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
