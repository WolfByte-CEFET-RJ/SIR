"""
MAVI/parser/factory.py

Parser construction and backend routing.

All concrete parser imports are lazy so that this module (and anything that
imports it) can be loaded without any parser backend installed.
"""

from __future__ import annotations

from MAVI.parser.base import DocumentParser
from MAVI.parser.composite import CompositeParser


def get_parser(backend: str = "docling") -> DocumentParser:
    """
    Return a DocumentParser configured with the requested backend
    and fast-path plain text routing.

    Parameters
    ----------
    backend:
        Name of the parser backend. Currently supported: ``"docling"``.

    Raises
    ------
    ValueError
        If *backend* is not recognised.
    """
    if backend == "docling":
        from MAVI.parser.docling_parser import DoclingParser

        primary_parser = DoclingParser()
        return CompositeParser(primary_parser=primary_parser)

    raise ValueError(f"Unknown parser backend: {backend!r}")
