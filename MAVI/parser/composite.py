"""
MAVI/parser/composite.py

Composite parser that routes streams to specialized parsers
based on file type (e.g. fast plain-text reader vs. heavy ML converter).
"""

from __future__ import annotations

import io
from MAVI.core.formats import PLAIN_TEXT_TYPES, detect_file_type
from MAVI.parser.base import DocumentParser
from MAVI.parser.plain_text_parser import PlainTextParser


class CompositeParser:
    """
    Routes documents to appropriate parsers:
    - Plain text formats (.txt, .md) -> PlainTextParser (instant decode)
    - All other formats -> primary_parser (e.g., DoclingParser)
    """

    def __init__(self, primary_parser: DocumentParser) -> None:
        self.primary_parser = primary_parser
        self.plain_text_parser = PlainTextParser()

    def convert_stream(self, stream: io.BytesIO, file_name: str) -> str:
        file_type = detect_file_type(file_name)
        if file_type in PLAIN_TEXT_TYPES:
            return self.plain_text_parser.convert_stream(stream, file_name)
        return self.primary_parser.convert_stream(stream, file_name)
