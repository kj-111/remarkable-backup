"""
PDF Export for reMarkable annotations.

Overlays annotations on the original PDF.
"""

from __future__ import annotations

from multiprocessing import Pool, cpu_count
from pathlib import Path

import fitz  # PyMuPDF

from .parser import parse_file, Stroke, Pen, PenColor
from .constants import (
    RM_TO_PDF_SCALE,
    COLOR_MAP_RGB,
    TRANSPARENT_PENS,
    ERASER_PENS,
)
from .folders import MetadataCache, slugify, get_page_order


def get_color(stroke: Stroke) -> tuple[float, float, float]:
    """Get RGB color (0-1 range) for stroke."""
    if isinstance(stroke.color, PenColor):
        rgb = COLOR_MAP_RGB.get(stroke.color, (0, 0, 0))
    else:
        rgb = (0, 0, 0)
    return (rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)


def is_eraser(stroke: Stroke) -> bool:
    """Check if stroke is an eraser."""
    if isinstance(stroke.pen, Pen):
        return stroke.pen in ERASER_PENS
    return False


def is_highlighter(stroke: Stroke) -> bool:
    """Check if stroke is a highlighter."""
    if isinstance(stroke.pen, Pen):
        return stroke.pen in TRANSPARENT_PENS
    return False


def draw_stroke_on_page(shape: fitz.Shape, stroke: Stroke, page_width: float):
    """Draw a stroke using Shape for batched rendering."""
    if is_eraser(stroke) or len(stroke.points) < 2:
        return

    color = get_color(stroke)

    # Calculate width from point data (formula: w / RM_TO_PDF_SCALE / 4.0)
    avg_width = sum(p.width for p in stroke.points) / len(stroke.points)
    width = max(0.5, avg_width / RM_TO_PDF_SCALE / 4.0)

    # Calculate dynamic X_OFFSET based on PDF page width
    x_offset = (page_width / 2) * RM_TO_PDF_SCALE

    # Transform coordinates
    pdf_points = [fitz.Point((p.x + x_offset) / RM_TO_PDF_SCALE, p.y / RM_TO_PDF_SCALE)
                  for p in stroke.points]
    
    # Draw each line segment individually (avoids polyline spaghetti issue)
    for i in range(len(pdf_points) - 1):
        shape.draw_line(pdf_points[i], pdf_points[i + 1])
    
    # Finish this stroke with styling (closePath=False prevents extra line)
    opacity = 0.4 if is_highlighter(stroke) else 1.0
    shape.finish(color=color, width=width, lineCap=1, lineJoin=1,
                 stroke_opacity=opacity, closePath=False)


def export_annotated_pdf(
    backup_dir: Path,
    doc_uuid: str,
    output_path: Path,
    verbose: bool = True
) -> bool:
    """
    Export a document with annotations overlaid on the original PDF.
    
    Args:
        backup_dir: Path to xochitl backup directory
        doc_uuid: Document UUID
        output_path: Output PDF path
        verbose: Print progress
    
    Returns:
        True if successful
    """
    backup_dir = Path(backup_dir)
    
    # Find original PDF
    pdf_path = backup_dir / f"{doc_uuid}.pdf"
    if not pdf_path.exists():
        if verbose:
            print(f"  No PDF found for {doc_uuid}")
        return False
    
    # Find annotation files
    rm_dir = backup_dir / doc_uuid
    if not rm_dir.exists():
        if verbose:
            print(f"  No annotations for {doc_uuid}")
        return False
    
    # Get page order
    content_path = backup_dir / f"{doc_uuid}.content"
    page_order = get_page_order(content_path)
    
    # Reverse mapping: page_num -> uuid
    page_to_uuid = {v: k for k, v in page_order.items()}
    
    # Open PDF
    pdf = fitz.open(pdf_path)
    annotations_added = 0

    try:
        for page_num in range(len(pdf)):
            page = pdf[page_num]

            # Find annotation file for this page
            page_uuid = page_to_uuid.get(page_num)
            if not page_uuid:
                continue

            rm_file = rm_dir / f"{page_uuid}.rm"
            if not rm_file.exists():
                continue

            # Parse annotations
            try:
                doc = parse_file(rm_file)
            except Exception as e:
                if verbose:
                    print(f"  Error parsing page {page_num + 1}: {e}")
                continue

            # Draw strokes using batched Shape
            shape = page.new_shape()
            page_width = page.rect.width
            for layer in doc.layers:
                for stroke in layer.strokes:
                    draw_stroke_on_page(shape, stroke, page_width)
                    annotations_added += 1
            shape.commit()  # Single commit per page for performance

        # Save with ez_save for optimal compression
        output_path.parent.mkdir(parents=True, exist_ok=True)
        page_count = len(pdf)
        pdf.ez_save(output_path)
    except Exception as e:
        if verbose:
            print(f"  Failed to save: {e}")
        return False
    finally:
        pdf.close()

    if verbose:
        print(f"  ✓ {output_path.name} ({annotations_added} strokes on {page_count} pages)")

    return True


def _export_worker(args: tuple) -> tuple[str, bool]:
    """Worker function for multiprocessing. PyMuPDF is not thread-safe, hence process pool."""
    backup_dir, doc_uuid, output_path, doc_name = args
    success = export_annotated_pdf(Path(backup_dir), doc_uuid, Path(output_path), verbose=False)
    return (doc_name, success)


def export_all_pdfs(
    backup_dir: Path,
    output_dir: Path,
    verbose: bool = True,
    force: bool = False,
) -> dict[str, int]:
    """Export all documents with annotations to PDF."""
    backup_dir = Path(backup_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load metadata cache and gather work (sequential, fast)
    cache = MetadataCache(backup_dir)
    work_items = []
    stats = {"exported": 0, "skipped": 0}

    for doc in cache.documents():
        pdf_path = backup_dir / f"{doc.uuid}.pdf"
        if not pdf_path.exists():
            continue

        folder_path = cache.get_folder_path(doc.uuid)
        if folder_path:
            output_path = output_dir / folder_path / f"{slugify(doc.name)}.pdf"
        else:
            output_path = output_dir / f"{slugify(doc.name)}.pdf"

        # Incremental: skip if not modified
        if not force and output_path.exists():
            output_mtime_ms = int(output_path.stat().st_mtime * 1000)
            if output_mtime_ms >= doc.last_modified:
                stats["skipped"] += 1
                continue

        work_items.append((str(backup_dir), doc.uuid, str(output_path), doc.name))

    # Show summary with red for changes
    if verbose:
        changed = len(work_items)
        if changed > 0:
            print(f"  \033[91m{changed} changed\033[0m, {stats['skipped']} unchanged")
        else:
            print(f"  {stats['skipped']} unchanged")
        print()

    if not work_items:
        return stats

    # Parallel export with multiprocessing
    num_workers = max(1, cpu_count() - 1)
    if verbose:
        print(f"Exporting {changed} PDFs using {num_workers} workers...")

    with Pool(num_workers) as pool:
        for doc_name, success in pool.imap_unordered(_export_worker, work_items):
            if success:
                stats["exported"] += 1
                if verbose:
                    print(f"  [{stats['exported'] + stats['skipped']}/{len(work_items)}] {doc_name}")
            else:
                stats["skipped"] += 1

    return stats


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Export reMarkable annotations overlaid on PDFs"
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
        default=project_root / "output/pdf-tool",
        help="Output directory"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress output"
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Force export all (ignore timestamps)"
    )

    args = parser.parse_args()

    if not args.quiet:
        print()
        print("📓 reMarkable PDF Export")
        print("=" * 40)
        print()

    stats = export_all_pdfs(
        args.backup_dir,
        args.output,
        verbose=not args.quiet,
        force=args.force,
    )

    if not args.quiet:
        print()
        print(f"Exported {stats['exported']}, skipped {stats['skipped']} PDFs")
        print(f"  Output: {args.output}")
        print()


if __name__ == "__main__":
    main()
