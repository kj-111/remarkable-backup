"""
Folder structure and metadata handling for reMarkable exports.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DocumentInfo:
    """Document or folder info from metadata."""
    uuid: str
    name: str
    parent: str
    doc_type: str
    last_modified: int = 0  # milliseconds since epoch

    @property
    def is_folder(self) -> bool:
        return self.doc_type == "CollectionType"

    @property
    def is_trashed(self) -> bool:
        return self.parent == "trash"


def slugify(name: str) -> str:
    """Convert a name to a filesystem-safe slug."""
    slug = name.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')


class MetadataCache:
    """
    Loads all metadata once and provides folder path resolution.
    """

    def __init__(self, backup_dir: Path):
        self.backup_dir = Path(backup_dir)
        self._items: dict[str, DocumentInfo] = {}
        self._loaded = False

    def load(self) -> None:
        """Load all .metadata files into the cache."""
        if self._loaded:
            return

        for metadata_file in self.backup_dir.glob("*.metadata"):
            uuid = metadata_file.stem
            try:
                with open(metadata_file) as f:
                    data = json.load(f)
                self._items[uuid] = DocumentInfo(
                    uuid=uuid,
                    name=data.get("visibleName", uuid),
                    parent=data.get("parent", ""),
                    doc_type=data.get("type", "DocumentType"),
                    last_modified=int(data.get("lastModified", "0")),
                )
            except (json.JSONDecodeError, IOError):
                continue

        self._loaded = True

    def get(self, uuid: str) -> DocumentInfo | None:
        """Get DocumentInfo for a uuid."""
        self.load()
        return self._items.get(uuid)

    def get_folder_path(self, uuid: str) -> str:
        """
        Determine the folder path for a document.

        Returns:
            Folder path (e.g. "archive" or "archive/subfolder") or "" for root.
        """
        self.load()
        doc = self._items.get(uuid)
        if not doc:
            return ""

        # Build path by following parents
        parts = []
        current_parent = doc.parent

        while current_parent and current_parent != "trash":
            parent_doc = self._items.get(current_parent)
            if not parent_doc:
                break
            parts.append(slugify(parent_doc.name))
            current_parent = parent_doc.parent

        # Reverse (we walked from child to root)
        parts.reverse()
        return "/".join(parts)

    def documents(self, include_trash: bool = False) -> list[DocumentInfo]:
        """
        Get all documents (no folders).

        Args:
            include_trash: Include items in trash
        """
        self.load()
        result = []
        for doc in self._items.values():
            if doc.is_folder:
                continue
            if not include_trash and doc.is_trashed:
                continue
            result.append(doc)
        return result


def get_page_order(content_path: Path) -> dict[str, int]:
    """
    Read page order from .content file.
    Returns mapping of page UUID -> page number (0-indexed).
    """
    page_order = {}
    try:
        with open(content_path) as f:
            data = json.load(f)

        # Try new simple format first: pages = ["uuid1", "uuid2", ...]
        if "pages" in data and isinstance(data["pages"], list):
            pages = data["pages"]
            if pages and isinstance(pages[0], str):
                for i, page_id in enumerate(pages):
                    page_order[page_id] = i
                return page_order

        # Fall back to old cPages format: cPages.pages[].id
        pages = data.get("cPages", {}).get("pages", [])
        for i, page in enumerate(pages):
            page_id = page.get("id", "")
            if page_id:
                redir = page.get("redir", {})
                if isinstance(redir, dict):
                    page_num = redir.get("value", i)
                else:
                    page_num = i
                page_order[page_id] = page_num
    except (json.JSONDecodeError, IOError):
        pass

    return page_order
