"""
Export reMarkable backup to SVG with readable names.

Reads the xochitl backup directory structure and exports
all annotations as SVG files organized by document name.
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

from .parser import parse_file
from .renderer import render_to_file, RM_TO_PDF_SCALE
from .folders import MetadataCache, slugify, get_page_order


def export_backup(
    backup_dir: Path,
    output_dir: Path,
    verbose: bool = True
) -> dict[str, int]:
    """
    Export all annotations from a reMarkable backup to SVG.

    Args:
        backup_dir: Path to xochitl backup directory
        output_dir: Path to output directory for SVGs
        verbose: Print progress

    Returns:
        Dict with export statistics
    """
    backup_dir = Path(backup_dir)
    output_dir = Path(output_dir)

    if not backup_dir.exists():
        raise ValueError(f"Backup directory not found: {backup_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    stats = {
        "documents": 0,
        "pages": 0,
        "skipped": 0,
    }

    # Load metadata cache
    cache = MetadataCache(backup_dir)

    # Iterate over documents (skips trash automatically)
    for doc in cache.documents():
        doc_uuid = doc.uuid
        rm_dir = backup_dir / doc_uuid
        content_path = backup_dir / f"{doc_uuid}.content"

        # Get page order
        page_order = get_page_order(content_path)

        # Open PDF for per-page dimensions (if present)
        pdf_path = backup_dir / f"{doc_uuid}.pdf"
        pdf = None
        if pdf_path.exists():
            try:
                pdf = fitz.open(pdf_path)
            except Exception:
                pass

        # Find all .rm files in this document
        rm_files = list(rm_dir.glob("*.rm")) if rm_dir.exists() else []
        if not rm_files:
            if pdf:
                pdf.close()
            continue

        stats["documents"] += 1

        # Determine output directory with folder structure
        folder_path = cache.get_folder_path(doc_uuid)
        if folder_path:
            doc_output_dir = output_dir / folder_path / slugify(doc.name)
        else:
            doc_output_dir = output_dir / slugify(doc.name)
        doc_output_dir.mkdir(parents=True, exist_ok=True)
        
        if verbose:
            print(f"📄 {doc.name}")
        
        for rm_file in rm_files:
            page_uuid = rm_file.stem
            page_num = page_order.get(page_uuid, -1)

            # Generate output filename (1-indexed for readability)
            if page_num >= 0:
                output_name = f"page-{page_num + 1:03d}.svg"
            else:
                output_name = f"{page_uuid}.svg"

            output_path = doc_output_dir / output_name

            try:
                rm_doc = parse_file(rm_file)
                stroke_count = sum(len(layer.strokes) for layer in rm_doc.layers)

                if stroke_count == 0:
                    stats["skipped"] += 1
                    continue

                # Get PDF dimensions for this specific page
                pdf_width = 595.0  # default
                pdf_height = 842.0  # default
                if pdf and page_num >= 0 and page_num < len(pdf):
                    pdf_page = pdf[page_num]
                    pdf_width = pdf_page.rect.width
                    pdf_height = pdf_page.rect.height
                elif pdf and len(pdf) > 0:
                    # Fallback to first page
                    pdf_width = pdf[0].rect.width
                    pdf_height = pdf[0].rect.height
                x_offset = (pdf_width / 2) * RM_TO_PDF_SCALE

                render_to_file(rm_doc, output_path, x_offset=x_offset, width=pdf_width, height=pdf_height)
                stats["pages"] += 1

                if verbose:
                    print(f"   ✓ {output_name} ({stroke_count} strokes)")

            except Exception as e:
                if verbose:
                    print(f"   ✗ {output_name}: {e}")
                stats["skipped"] += 1

        # Close PDF after processing this document
        if pdf:
            pdf.close()

    return stats


def main():
    """CLI entry point for export."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Export reMarkable backup annotations to SVG"
    )
    # Project root is parent of src/
    project_root = Path(__file__).parent.parent

    parser.add_argument(
        "backup_dir",
        type=Path,
        nargs="?",
        default=project_root / "xochitl",
        help="Path to xochitl backup directory"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=project_root / "output/svg-tool",
        help="Output directory for SVGs"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress output"
    )
    
    args = parser.parse_args()
    
    print()
    print("📓 reMarkable SVG Export")
    print("=" * 40)
    print()
    
    stats = export_backup(
        args.backup_dir,
        args.output,
        verbose=not args.quiet
    )
    
    print()
    print(f"✓ Exported {stats['pages']} pages from {stats['documents']} documents")
    print(f"  Output: {args.output}")
    if stats["skipped"]:
        print(f"  Skipped: {stats['skipped']} (empty or errors)")
    print()


if __name__ == "__main__":
    main()
