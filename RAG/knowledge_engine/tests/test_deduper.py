import unittest

from knowledge_engine.processors.deduper import compute_content_hash, dedupe_documents


class DeduperTest(unittest.TestCase):
    def test_compute_hash_ignores_trailing_whitespace(self):
        hash1 = compute_content_hash("Hello")
        hash2 = compute_content_hash("Hello ")
        self.assertEqual(hash1, hash2)

    def test_dedupe_documents_removes_duplicates(self):
        docs = [
            {"page_content": "A", "metadata": {}},
            {"page_content": "A", "metadata": {}},
            {"page_content": "B", "metadata": {}},
        ]
        unique = dedupe_documents(docs)
        self.assertEqual(len(unique), 2)
        self.assertNotEqual(unique[0]["metadata"]["content_hash"], unique[1]["metadata"]["content_hash"])


if __name__ == "__main__":
    unittest.main()
