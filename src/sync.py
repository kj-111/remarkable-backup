"""
Sync annotated PDFs to Obsidian vault.

Copies PDFs matching patterns in sync.toml to configured destinations.
"""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Optional

import tomli


def parse_config(config_path: Path) -> dict[str, Path]:
    """Parse sync.toml."""
    with open(config_path, "rb") as f:
        data = tomli.load(f)
    return {k: Path(v) for k, v in data.get("sync", {}).items()}


def find_pdf(pdf_dir: Path, pattern: str) -> Optional[Path]:
    """Find PDF matching pattern (substring)."""
    for pdf in pdf_dir.rglob("*.pdf"):
        if pattern in pdf.stem:
            return pdf
    return None


def sync_pdfs(pdf_dir: Path, config_path: Path, verbose: bool = True) -> dict[str, int]:
    """Copy matching PDFs to Obsidian."""
    stats = {"synced": 0, "not_found": 0}

    for pattern, dest in parse_config(config_path).items():
        pdf = find_pdf(pdf_dir, pattern)
        if not pdf:
            if verbose:
                print(f"  ! Not found: {pattern}")
            stats["not_found"] += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pdf, dest)
        if verbose:
            print(f"  {pdf.name} -> {dest}")
        stats["synced"] += 1

    return stats


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Sync annotated PDFs to Obsidian"
    )
    project_root = Path(__file__).parent.parent

    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=project_root / "sync.toml",
        help="Path to sync.toml config"
    )
    parser.add_argument(
        "-d", "--pdf-dir",
        type=Path,
        default=project_root / "output/pdf-tool",
        help="Directory with annotated PDFs"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress output"
    )

    args = parser.parse_args()

    if not args.config.exists():
        if not args.quiet:
            print(f"Config not found: {args.config}")
        return

    if not args.quiet:
        print()
        print("Syncing PDFs to Obsidian...")
        print()

    stats = sync_pdfs(args.pdf_dir, args.config, verbose=not args.quiet)

    if not args.quiet:
        print()
        print(f"Synced {stats['synced']} PDFs")
        if stats["not_found"]:
            print(f"Not found: {stats['not_found']}")
        print()


if __name__ == "__main__":
    main()
