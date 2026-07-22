import unittest

from knowledge_engine.processors.normalizer import Normalizer


class NormalizerTest(unittest.TestCase):
    def test_normalize_collapses_whitespace_and_filters_headers(self):
        normalizer = Normalizer()
        text = "Header\nHeader\nHeader\n\nLine 1   \n\nLine 2\n"
        output = normalizer.normalize(text)
        self.assertIn("Line 1", output)
        self.assertNotIn("Header\nHeader\nHeader", output)
        self.assertNotIn("  ", output)


if __name__ == "__main__":
    unittest.main()
