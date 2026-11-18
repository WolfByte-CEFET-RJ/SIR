"""
MAVI/parser/plain_text_parser.py

Fast, zero-dependency parser for plain text and markdown documents.
"""

from __future__ import annotations

import io


class PlainTextParser:
    """
    DocumentParser implementation for plain text formats (.txt, .md).
    Decodes the byte stream directly into text without invoking ML models.
    """

    def convert_stream(self, stream: io.BytesIO, file_name: str) -> str:
        stream.seek(0)
        return stream.getvalue().decode("utf-8", errors="replace")
