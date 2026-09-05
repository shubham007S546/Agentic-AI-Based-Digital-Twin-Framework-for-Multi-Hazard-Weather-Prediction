import unittest
from pathlib import Path

from knowledge_engine.knowledge.store import safe_document_id


class SafeDocumentIdTest(unittest.TestCase):
    def test_safe_document_id_replaces_invalid_windows_chars(self):
        source = r"project_repo:collectors\openmeteo_collector.py:6726203789f7"
        safe_id = safe_document_id(source)
        self.assertNotIn(":", safe_id)
        self.assertNotIn("<", safe_id)
        self.assertNotIn(">", safe_id)
        self.assertNotIn("\"", safe_id)
        self.assertNotIn("/", safe_id)
        self.assertNotIn("\\", safe_id)
        self.assertNotIn("|", safe_id)
        self.assertNotIn("?", safe_id)
        self.assertNotIn("*", safe_id)
        self.assertIn("project_repo_collectors_openmeteo_collector.py_", safe_id)
        self.assertRegex(safe_id, r'^[^<>:"/\\|?*]+$')
        self.assertLessEqual(len(safe_id), 64)

    def test_safe_document_id_is_deterministic(self):
        source = "project_repo:collectors/openmeteo_collector.py:6726203789f7"
        self.assertEqual(safe_document_id(source), safe_document_id(source))

    def test_safe_document_id_truncates_long_names(self):
        source = "project_repo:" + "a" * 200
        safe_id = safe_document_id(source)
        self.assertLessEqual(len(safe_id), 64)


if __name__ == "__main__":
    unittest.main()
