"""
MAVI/parser/factory.py

Parser construction and backend routing.

All concrete parser imports are lazy so that this module (and anything that
imports it) can be loaded without any parser backend installed.
"""

from __future__ import annotations

from MAVI.parser.base import DocumentParser


def get_parser(backend: str = "docling") -> DocumentParser:
    """
    Return a DocumentParser powered by the requested backend.

    Parameters
    ----------
    backend:
        Name of the parser backend.  Currently supported: ``"docling"``.

    Raises
    ------
    ValueError
        If *backend* is not recognised.
    """
    if backend == "docling":
        from MAVI.parser.docling_parser import DoclingParser

        return DoclingParser()

    raise ValueError(f"Unknown parser backend: {backend!r}")
