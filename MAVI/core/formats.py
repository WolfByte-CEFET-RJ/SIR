"""
MAVI/core/formats.py

Neutral, zero-dependency module that defines canonical file-type identifiers,
the default allowlist for document ingestion, and a filename-based detector.
"""

from enum import StrEnum
from pathlib import Path


class FileType(StrEnum):
    """Canonical lower-case extension values for every file type MAVI handles."""
    PDF    = "pdf"
    DOCX   = "docx"
    DOC    = "doc"
    PPTX   = "pptx"
    PPT    = "ppt"
    HTML   = "html"
    HTM    = "htm"
    PNG    = "png"
    JPEG   = "jpeg"
    JPG    = "jpg"
    MD     = "md"
    TXT    = "txt"
    XLSX   = "xlsx"
    XLS    = "xls"
    CSV    = "csv"


# File types that are actively converted to text by default.
# Spreadsheets (.xlsx, .csv, .xls) are excluded intentionally.
ALLOWED_PARSE_TYPES: set[FileType] = {
    FileType.PDF,
    FileType.DOCX,
    FileType.DOC,
    FileType.PPTX,
    FileType.PPT,
    FileType.HTML,
    FileType.HTM,
    FileType.PNG,
    FileType.JPEG,
    FileType.JPG,
    FileType.MD,
    FileType.TXT,
}


def detect_file_type(file_name: str) -> FileType | None:
    """
    Infer the FileType from a filename's extension.

    Returns the matching FileType, or None when the extension is unrecognised
    or the filename has no extension at all.
    """
    suffix = Path(file_name).suffix.lower().lstrip(".")
    if not suffix:
        return None
    try:
        return FileType(suffix)
    except ValueError:
        return None
