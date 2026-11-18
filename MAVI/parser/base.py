"""
MAVI/parser/base.py

Structural Protocol that every document parser must satisfy.
Zero third-party imports — safe to import in any environment.
"""

import io
from typing import Protocol, runtime_checkable


@runtime_checkable
class DocumentParser(Protocol):
    """
    Convert a binary stream representing a document file into plain Markdown text.

    Implementations are free to use any backend (docling, pypdf, etc.) as long
    as they honour this interface.
    """

    def convert_stream(self, stream: io.BytesIO, file_name: str) -> str:
        """
        Parse *stream* (positioned at byte 0) and return the document content
        as a Markdown string.

        Parameters
        ----------
        stream:
            In-memory byte buffer of the document.  The implementation must
            call ``stream.seek(0)`` before reading if it cannot guarantee the
            position.
        file_name:
            Original filename including extension (e.g. ``"report.pdf"``).
            Used to hint the parser about the input format.

        Returns
        -------
        str
            Document content serialised as Markdown.
        """
        ...
