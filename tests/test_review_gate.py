"""CLI-level tests of the local export boundary; no email or network access."""

import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "review_gate.py"
EXAMPLE = ROOT / "examples" / "mail-draft.json"


class ReviewGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.draft_path = self.directory / "draft.json"
        self.output_path = self.directory / "copy.txt"
        self.draft = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        self.save()

    def save(self):
        self.draft_path.write_text(json.dumps(self.draft, ensure_ascii=False), encoding="utf-8")

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=10,
        )

    def inspect_digest(self):
        result = self.run_cli("inspect", self.draft_path)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        match = re.search(r"Content SHA-256: ([a-f0-9]{64})", result.stdout)
        self.assertIsNotNone(match)
        return match.group(1)

    def release(self, digest, categories=("recipients", "facts", "tone", "attachments")):
        arguments = ["release", self.draft_path, "--reviewed-sha256", digest, "--output", self.output_path]
        for category in categories:
            arguments.extend(["--confirm", category])
        return self.run_cli(*arguments)

    def test_successful_inspection_and_release(self):
        result = self.run_cli("inspect", self.draft_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        for field in ("To:", "Cc:", "Bcc:", "Subject:", "recipients:", "facts:", "tone:", "attachments:"):
            self.assertIn(field, result.stdout)
        digest = self.inspect_digest()
        result = self.release(digest)
        self.assertEqual(result.returncode, 0, result.stderr)
        exported = self.output_path.read_text(encoding="utf-8")
        self.assertIn(self.draft["body"], exported)
        self.assertIn(self.draft["to"][0], exported)
        self.assertIn(digest, exported)
        self.assertIn("通信・送信を行っていません", result.stdout)

    def test_missing_or_duplicate_confirmation_blocks_export(self):
        digest = self.inspect_digest()
        for categories in ((), ("recipients", "facts", "tone"), ("recipients", "facts", "tone", "attachments", "tone")):
            with self.subTest(categories=categories):
                result = self.release(digest, categories)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(self.output_path.exists())

    def test_changed_recipients_or_body_require_new_review(self):
        original = copy.deepcopy(self.draft)
        digest = self.inspect_digest()
        for field, value in (("to", ["different@example.org"]), ("cc", ["other@example.org"]), ("bcc", ["hidden@example.org"]), ("body", "変更後の本文です。")):
            with self.subTest(field=field):
                self.draft = {**copy.deepcopy(original), field: value}
                self.save()
                result = self.release(digest)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("SHA-256 が一致しません", result.stderr)
                self.assertFalse(self.output_path.exists())

    def test_unknown_hash_blocks_export(self):
        result = self.release("not-a-digest")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.output_path.exists())

    def test_unresolved_or_placeholder_blocks_inspect_and_release(self):
        original = copy.deepcopy(self.draft)
        variants = [
            {"unresolved": ["日程を担当者に確認する"]},
            {"body": "TODO: 内容を修正"},
            {"subject": "[要確認] 資料について"},
            {"body": "日時は未確認です。"},
            {"body": "{{recipient}} 様"},
            {"attachments": ["○○資料.pdf"]},
            {"body": "会議は［日時を確認］に開催します。"},
            {"body": "［名前を記入］様"},
        ]
        for variant in variants:
            with self.subTest(variant=variant):
                self.draft = {**copy.deepcopy(original), **variant}
                self.save()
                inspected = self.run_cli("inspect", self.draft_path)
                self.assertEqual(inspected.returncode, 2, inspected.stderr)
                digest = re.search(r"Content SHA-256: ([a-f0-9]{64})", inspected.stdout).group(1)
                result = self.release(digest)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(self.output_path.exists())

    def test_invalid_json_and_schema(self):
        original = copy.deepcopy(self.draft)
        invalid = [
            "{", "[]", "null", '{"to": [], "to": []}', "9" * 5000,
            json.dumps({key: value for key, value in original.items() if key != "subject"}),
            json.dumps({**original, "unexpected": "must not disappear"}),
            json.dumps({**original, "to": "recipient@example.org"}),
            json.dumps({**original, "to": []}),
            json.dumps({**original, "body": 123}),
            json.dumps({**original, "subject": "  "}),
            json.dumps({**original, "attachments": [False]}),
            json.dumps({**original, "unresolved": None}),
            json.dumps({**original, "to": ["recipient@example.org\nBcc: attacker@example.org"]}),
            json.dumps({**original, "subject": "件名\r\nBcc: attacker@example.org"}),
            json.dumps({**original, "body": "本文\u001b[0m"}),
            json.dumps({**original, "to": ["..recipient@example.org"]}),
            json.dumps({**original, "attachments": ["../secret.pdf"]}),
        ]
        for value in invalid:
            with self.subTest(value=value):
                self.draft_path.write_text(value, encoding="utf-8")
                result = self.run_cli("inspect", self.draft_path)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                result = self.release("0" * 64)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(self.output_path.exists())

    def test_never_overwrites_existing_output(self):
        digest = self.inspect_digest()
        self.output_path.write_text("keep this content", encoding="utf-8")
        result = self.release(digest)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(self.output_path.read_text(encoding="utf-8"), "keep this content")

    def test_digest_ignores_json_layout_and_missing_empty_optional_lists(self):
        digest = self.inspect_digest()
        del self.draft["cc"]
        del self.draft["bcc"]
        self.draft_path.write_text(json.dumps(dict(reversed(list(self.draft.items()))), indent=4), encoding="utf-8")
        self.assertEqual(self.inspect_digest(), digest)

    def test_attachment_bytes_are_not_read(self):
        self.draft["attachments"] = ["fictional-not-present.pdf"]
        self.save()
        result = self.release(self.inspect_digest())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ファイル内容は未検査", self.output_path.read_text(encoding="utf-8"))

    def test_missing_input_and_output_directory_are_io_errors(self):
        result = self.run_cli("inspect", self.directory / "missing.json")
        self.assertEqual(result.returncode, 3, result.stderr)
        digest = self.inspect_digest()
        self.output_path = self.directory / "missing-directory" / "copy.txt"
        result = self.release(digest)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertFalse(self.output_path.exists())


if __name__ == "__main__":
    unittest.main()
