import re


def clean_text(text: str) -> str:
    """
    Clean extracted PDF text.
    """

    # Remove multiple spaces
    text = re.sub(r"[ \t]+", " ", text)

    # Remove excessive blank lines
    text = re.sub(r"\n{2,}", "\n\n", text)

    return text.strip()