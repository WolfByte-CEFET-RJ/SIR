"""
MAVI/parser/__init__.py

Public API surface for the parser sub-package.
Pure re-exports — no logic lives here.
"""

from MAVI.parser.base import DocumentParser
from MAVI.parser.factory import get_parser

__all__ = ["DocumentParser", "get_parser"]
