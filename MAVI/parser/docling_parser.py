"""
MAVI/parser/docling_parser.py

Lazy-loaded adapter that wraps the `docling` library.

All `docling` imports are deferred so that:
  - The module can be imported in environments without `docling` installed.
  - `docling` and its models are only loaded when conversion is actually requested.
"""

from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)


class DoclingParser:
    """
    DocumentParser implementation backed by `docling`.

    Relies on Docling's native format detection via DocumentStream.
    """

    def __init__(self) -> None:
        self._converter = None

    def _get_converter(self):
        if self._converter is None:
            # Lazy import and instantiate converter with default supported formats
            from docling.document_converter import DocumentConverter  # type: ignore[import]

            self._converter = DocumentConverter()
        return self._converter

    def convert_stream(self, stream: io.BytesIO, file_name: str) -> str:
        """
        Convert a binary document stream to Markdown using docling.

        Raises
        ------
        ImportError
            If `docling` is not installed in the current environment.
        """
        # Lazy import of DocumentStream
        from docling.datamodel.document import DocumentStream  # type: ignore[import]

        converter = self._get_converter()

        stream.seek(0)
        doc_stream = DocumentStream(name=file_name, stream=stream)

        logger.debug("DoclingParser: converting '%s'", file_name)
        result = converter.convert(doc_stream)
        return result.document.export_to_markdown()
