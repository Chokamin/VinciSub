"""Validate the project handoff documents without third-party dependencies."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = {
    "HANDOFF.md": ["当前状态", "下一步任务", "已知风险", "阻塞点", "需要验证的内容"],
    "PROJECT_MEMORY.md": ["最近完成的修改", "关键文件", "短期问题"],
    "DECISIONS.md": ["产品与技术"],
    "CLAUDE.md": ["开始工作前", "修改与验证", "完成修改后", "记忆维护"],
}


class ProjectMemoryTests(unittest.TestCase):
    def test_documents_are_root_files_with_required_sections(self):
        for filename, sections in DOCUMENTS.items():
            with self.subTest(document=filename):
                path = ROOT / filename
                self.assertFalse(path.is_symlink())
                self.assertTrue(path.is_file())
                content = path.read_text(encoding="utf-8")
                self.assertTrue(content.startswith("# "))
                for section in sections:
                    self.assertIn(f"## {section}\n", content)

    def test_startup_reading_order_references_existing_documents(self):
        content = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        references = re.findall(r"^\d+\. ([A-Z_]+\.md)$", content, re.MULTILINE)
        self.assertEqual(references, list(DOCUMENTS))
        for filename in references:
            self.assertTrue((ROOT / filename).is_file())

    def test_change_records_include_required_handoff_fields(self):
        content = (ROOT / "PROJECT_MEMORY.md").read_text(encoding="utf-8")
        entries = re.split(r"^### ", content, flags=re.MULTILINE)[1:]
        self.assertTrue(entries, "At least one dated change record is required")
        for entry in entries:
            self.assertRegex(entry, r"^\d{4}-\d{2}-\d{2}：")
            for field in ("需求", "改动", "关键文件", "验证结果", "剩余问题"):
                self.assertRegex(entry, rf"(?m)^- {field}：\S.+")


if __name__ == "__main__":
    unittest.main()
