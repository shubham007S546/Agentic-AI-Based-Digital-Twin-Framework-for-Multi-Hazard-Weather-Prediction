import os
import tempfile
import unittest
from pathlib import Path

from knowledge_engine.metadata.storage import MetadataStore


class MetadataStorageTest(unittest.TestCase):
    def test_upsert_and_query(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "metadata.db"
            store = MetadataStore(db_path)
            metadata = {
                "doc_id": "doc-123",
                "source": "test",
                "content_hash": "abc123",
                "title": "Test Document",
                "collection": "project",
            }
            store.upsert_document(metadata)
            loaded = store.get_by_doc_id("doc-123")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["source"], "test")
            self.assertEqual(loaded["content_hash"], "abc123")
            self.assertEqual(loaded["collection"], "project")
            store.close()


if __name__ == "__main__":
    unittest.main()
