"""
MAVI/connectors/google_drive/loader.py

Google Drive content downloader and format-aware routing layer.

Responsibilities
----------------
* Route native Google Docs to the Drive export API (returns Markdown directly).
* Validate every other file against the ALLOWED_FILE_TYPES allowlist before
  downloading any bytes — skips spreadsheets and unknown formats early.
* Download binary files as an in-memory BytesIO stream.
* Delegate stream → Markdown conversion to an injected DocumentParser so this
  module never imports `docling` or any other heavy backend.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Iterator

from googleapiclient.http import MediaIoBaseDownload

from MAVI.core.formats import ALLOWED_PARSE_TYPES, FileType, detect_file_type
from MAVI.parser.base import DocumentParser

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def get_file_stream(request) -> io.BytesIO:
    """
    Download a Drive media request and return a seeked-to-zero BytesIO buffer.
    """
    file_stream = io.BytesIO()
    downloader = MediaIoBaseDownload(file_stream, request)
    done = False
    while not done:
        _status, done = downloader.next_chunk()
    file_stream.seek(0)
    return file_stream


def get_text_from_google_doc(service, file_id: str, output_type: str = "text/markdown") -> str:
    """
    Export a native Google Doc via the Drive API and return its content as a
    UTF-8 string.

    Parameters
    ----------
    output_type:
        Target MIME type. See
        https://developers.google.com/workspace/drive/api/guides/ref-export-formats
    """
    request = service.files().export_media(fileId=file_id, mimeType=output_type)
    file_stream = get_file_stream(request)
    return file_stream.getvalue().decode("utf-8")


# ---------------------------------------------------------------------------
# Main router
# ---------------------------------------------------------------------------

def get_content_from_google(
    service,
    file_id: str,
    mime_type: str,
    file_name: str | None = None,
    parser: DocumentParser | None = None,
) -> str | None:
    """
    Route a Drive file to the appropriate extraction strategy and return its
    content as a Markdown string, or ``None`` when the file should be skipped.

    Parameters
    ----------
    service:
        Authenticated Google Drive API resource.
    file_id:
        Drive file ID.
    mime_type:
        MIME type as reported by the Drive API.
    file_name:
        Original filename (including extension).  If omitted, the name is
        fetched via a lightweight metadata API call.
    parser:
        A :class:`~MAVI.parser.base.DocumentParser` instance used to convert
        binary streams to Markdown.  When ``None``, binary files that require
        conversion are logged and skipped.

    Returns
    -------
    str | None
        Markdown text, or ``None`` if the file was filtered out or no parser
        was provided for a binary format.
    """
    # --- 1. Native Google Docs: export directly as Markdown ---
    if mime_type == "application/vnd.google-apps.document":
        logger.info("Extracting native Google Doc (ID: %s)", file_id)
        return get_text_from_google_doc(service, file_id, output_type="text/markdown")

    # --- 2. Skip Google-native formats we don't handle (Sheets, Slides, etc.) ---
    if mime_type.startswith("application/vnd.google-apps."):
        logger.debug("Skipping unsupported Google Workspace type '%s' (ID: %s)", mime_type, file_id)
        return None

    # --- 3. Resolve file_name if not provided ---
    if file_name is None:
        logger.debug("file_name not supplied for ID %s — fetching metadata", file_id)
        file_name = service.files().get(fileId=file_id, fields="name").execute()["name"]

    # --- 4. Validate file type against the allowlist ---
    file_type: FileType | None = detect_file_type(file_name)

    if file_type is None:
        logger.info("Skipping '%s' (ID: %s): unrecognised extension", file_name, file_id)
        return None

    if file_type not in ALLOWED_PARSE_TYPES:
        logger.info(
            "Skipping '%s' (ID: %s): file type '%s' is not in the allowlist",
            file_name, file_id, file_type,
        )
        return None

    # --- 5. Require a parser for binary files ---
    if parser is None:
        logger.warning(
            "No parser provided — skipping binary file '%s' (ID: %s)", file_name, file_id
        )
        return None

    # --- 6. Download and convert ---
    logger.info("Downloading '%s' (ID: %s, type: %s)", file_name, file_id, file_type)
    request = service.files().get_media(fileId=file_id)
    file_stream = get_file_stream(request)

    return parser.convert_stream(file_stream, file_name)


# ---------------------------------------------------------------------------
# Tree walker
# ---------------------------------------------------------------------------

def get_content_from_tree(
    service,
    tree: dict,
    current_path: str = "",
    parser: DocumentParser | None = None,
) -> Iterator[dict]:
    """
    Recursively walk the folder tree produced by the crawler and yield one
    metadata dict per file, enriched with a ``"content"`` key when extraction
    succeeds.

    Parameters
    ----------
    service:
        Authenticated Google Drive API resource.
    tree:
        Nested folder dict as returned by ``get_google_drive_tree``.
    current_path:
        Accumulated relative path string (used by recursive calls).
    parser:
        DocumentParser passed through to ``get_content_from_google``.
    """
    # TODO: Batch the file downloads
    for folder_id, folder_data in tree.items():
        new_path = f"{current_path}/{folder_data['name']}" if current_path else folder_data["name"]

        # Process files in the current folder
        files = folder_data.get("files", {})
        for file_id, file_meta in files.items():
            file_meta["id"] = file_id
            file_meta["path"] = new_path
            mime_type = file_meta.get("mimeType", "")
            content = get_content_from_google(
                service,
                file_id,
                mime_type,
                file_name=file_meta.get("name"),
                parser=parser,
            )
            if content is not None:
                file_meta["content"] = content
            yield file_meta

        # Recurse into sub-folders
        subfolders = folder_data.get("folders", {})
        if subfolders:
            yield from get_content_from_tree(service, subfolders, new_path, parser=parser)


if __name__ == "__main__":
    import argparse
    import json
    import os
    from pathlib import Path

    from MAVI.connectors.google_drive.auth import get_google_drive_service
    from MAVI.parser import get_parser

    arg_parser = argparse.ArgumentParser(
        description="Extract content from Google Drive files using a directory tree JSON."
    )
    arg_parser.add_argument(
        "tree_file", type=str, help="Path to the JSON file containing the Drive directory tree."
    )
    args = arg_parser.parse_args()

    tree_file = Path(args.tree_file)

    with open(tree_file, "r", encoding="utf-8") as f:
        tree = json.load(f)

    save_path = tree_file.parent / f"parsed_{tree_file.stem}.jsonl"
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    _service = get_google_drive_service()
    _parser = get_parser()

    with open(save_path, "w", encoding="utf-8") as f:
        for file_meta in get_content_from_tree(_service, tree, parser=_parser):
            f.write(json.dumps(file_meta, ensure_ascii=False) + "\n")

    print(f"Content extracted and saved to {save_path}")
