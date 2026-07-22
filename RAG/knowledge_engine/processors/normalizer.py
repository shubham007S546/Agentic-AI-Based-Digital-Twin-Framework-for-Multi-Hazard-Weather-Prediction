import re
from typing import List


class Normalizer:
    HEADER_FOOTER_MIN_REPEAT = 2

    def normalize(self, text: str) -> str:
        if not text:
            return ""

        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = self._remove_trailing_whitespace(text)
        text = self._collapse_repeated_lines(text)
        text = self._filter_repeated_headers_footers(text)
        text = self._normalize_whitespace(text)
        return text.strip()

    def _remove_trailing_whitespace(self, text: str) -> str:
        return "\n".join(line.rstrip() for line in text.splitlines())

    def _collapse_repeated_lines(self, text: str) -> str:
        return re.sub(r"\n{3,}", "\n\n", text)

    def _normalize_whitespace(self, text: str) -> str:
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{2,}", "\n\n", text)
        return text

    def _filter_repeated_headers_footers(self, text: str) -> str:
        lines = [line for line in text.splitlines() if line.strip()]
        seen = {}
        result: List[str] = []
        for line in lines:
            normalized = line.strip()
            seen[normalized] = seen.get(normalized, 0) + 1
            if seen[normalized] > self.HEADER_FOOTER_MIN_REPEAT and len(normalized) < 120:
                continue
            result.append(line)
        return "\n".join(result)
