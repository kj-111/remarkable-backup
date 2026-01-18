"""
SVG Renderer for reMarkable annotations.

Converts parsed strokes to SVG format.
"""

from __future__ import annotations

from pathlib import Path
from typing import TextIO
import xml.etree.ElementTree as ET

from .parser import Document, Stroke, Point, Pen, PenColor
from .constants import (
    RM_TO_PDF_SCALE,
    COLOR_MAP_HEX,
    PEN_BASE_WIDTH,
    TRANSPARENT_PENS,
    ERASER_PENS,
)


# =============================================================================
# Constants
# =============================================================================

# reMarkable screen dimensions
REMARKABLE_WIDTH = 1404
REMARKABLE_HEIGHT = 1872

# Default X offset - for PDFs ~595 pts wide (A4-ish)
# Formula: X_OFFSET = (PDF_width_pts / 2) * RM_TO_PDF_SCALE
DEFAULT_X_OFFSET = 938.0

# Output dimensions (PDF points, ~A4 size)
OUTPUT_WIDTH = REMARKABLE_WIDTH / RM_TO_PDF_SCALE   # ~445
OUTPUT_HEIGHT = REMARKABLE_HEIGHT / RM_TO_PDF_SCALE  # ~594


# =============================================================================
# SVG Path Generation
# =============================================================================

def points_to_path(points: list[Point], x_offset: float = DEFAULT_X_OFFSET) -> str:
    """
    Convert a list of points to an SVG path string.
    Uses quadratic bezier curves for smooth lines.

    Applies same transformation as PDF export:
    x_svg = (raw_x + x_offset) / RM_TO_PDF_SCALE
    y_svg = raw_y / RM_TO_PDF_SCALE
    """
    if len(points) < 1:
        return ""

    # Transform points using same formula as PDF export
    def tx(x: float) -> float:
        return (x + x_offset) / RM_TO_PDF_SCALE

    def ty(y: float) -> float:
        return y / RM_TO_PDF_SCALE
    
    if len(points) == 1:
        # Single point - draw a small circle
        p = points[0]
        return f"M {tx(p.x):.2f} {ty(p.y):.2f} l 0.1 0.1"
    
    # Start at first point
    path = f"M {tx(points[0].x):.2f} {ty(points[0].y):.2f}"
    
    if len(points) == 2:
        # Two points - straight line
        path += f" L {tx(points[1].x):.2f} {ty(points[1].y):.2f}"
        return path
    
    # For smoother curves, use quadratic beziers through midpoints
    for i in range(1, len(points)):
        p0 = points[i - 1]
        p1 = points[i]
        
        if i == 1:
            # First segment: line to midpoint
            mid_x = (tx(p0.x) + tx(p1.x)) / 2
            mid_y = (ty(p0.y) + ty(p1.y)) / 2
            path += f" L {mid_x:.2f} {mid_y:.2f}"
        elif i == len(points) - 1:
            # Last segment: curve to end point
            path += f" Q {tx(p0.x):.2f} {ty(p0.y):.2f} {tx(p1.x):.2f} {ty(p1.y):.2f}"
        else:
            # Middle segments: curve through midpoint
            mid_x = (tx(p0.x) + tx(p1.x)) / 2
            mid_y = (ty(p0.y) + ty(p1.y)) / 2
            path += f" Q {tx(p0.x):.2f} {ty(p0.y):.2f} {mid_x:.2f} {mid_y:.2f}"
    
    return path


def get_stroke_color(stroke: Stroke) -> str:
    """Get the hex color for a stroke."""
    if isinstance(stroke.color, PenColor):
        return COLOR_MAP_HEX.get(stroke.color, "#000000")
    return "#000000"


def get_stroke_width(stroke: Stroke) -> float:
    """Calculate stroke width using same formula as PDF export."""
    # Use average point width (same as pdf_export.py)
    if stroke.points:
        avg_width = sum(p.width for p in stroke.points) / len(stroke.points)
        return max(0.5, avg_width / RM_TO_PDF_SCALE / 4.0)
    # Fallback to pen-based width
    if isinstance(stroke.pen, Pen):
        base_width = PEN_BASE_WIDTH.get(stroke.pen, 1.0)
    else:
        base_width = 1.0
    return base_width * stroke.thickness_scale / RM_TO_PDF_SCALE


def get_stroke_opacity(stroke: Stroke) -> float:
    """Get opacity for the stroke."""
    if isinstance(stroke.pen, Pen) and stroke.pen in TRANSPARENT_PENS:
        return 0.4
    return 1.0


def is_eraser(stroke: Stroke) -> bool:
    """Check if stroke is an eraser."""
    if isinstance(stroke.pen, Pen):
        return stroke.pen in ERASER_PENS
    return False


# =============================================================================
# SVG Document Generation
# =============================================================================

def render_svg(doc: Document, output: TextIO, width: float = OUTPUT_WIDTH,
               height: float = OUTPUT_HEIGHT, x_offset: float = DEFAULT_X_OFFSET) -> None:
    """
    Render a Document to SVG format.

    Args:
        doc: Parsed document with strokes
        output: File-like object to write SVG to
        width: SVG width (default: PDF-scale width ~445pt)
        height: SVG height (default: PDF-scale height ~594pt)
        x_offset: X offset for coordinate transformation (default: 938.0 for ~595pt PDFs)
    """
    # Create SVG root
    svg = ET.Element("svg")
    svg.set("xmlns", "http://www.w3.org/2000/svg")
    svg.set("viewBox", f"0 0 {width:.2f} {height:.2f}")
    svg.set("width", f"{width:.2f}")
    svg.set("height", f"{height:.2f}")
    
    # Optional: add white background
    bg = ET.SubElement(svg, "rect")
    bg.set("width", "100%")
    bg.set("height", "100%")
    bg.set("fill", "#ffffff")
    
    # Render each layer
    for i, layer in enumerate(doc.layers):
        g = ET.SubElement(svg, "g")
        g.set("id", f"layer-{i}")
        if layer.name:
            g.set("data-name", layer.name)
        if not layer.visible:
            g.set("visibility", "hidden")
        
        # Render strokes
        for stroke in layer.strokes:
            # Skip erasers in output
            if is_eraser(stroke):
                continue
            
            if not stroke.points:
                continue
            
            path = ET.SubElement(g, "path")
            path.set("d", points_to_path(stroke.points, x_offset))
            path.set("stroke", get_stroke_color(stroke))
            path.set("stroke-width", f"{get_stroke_width(stroke):.2f}")
            path.set("stroke-linecap", "round")
            path.set("stroke-linejoin", "round")
            path.set("fill", "none")
            
            opacity = get_stroke_opacity(stroke)
            if opacity < 1.0:
                path.set("opacity", f"{opacity:.2f}")
    
    # Write to output
    tree = ET.ElementTree(svg)
    ET.indent(tree, space="  ")
    tree.write(output, encoding="unicode", xml_declaration=True)
    output.write("\n")


def render_to_file(doc: Document, path: Path, **kwargs) -> None:
    """Render document to an SVG file."""
    with open(path, "w", encoding="utf-8") as f:
        render_svg(doc, f, **kwargs)


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys
    from .parser import parse_file
    
    if len(sys.argv) < 2:
        print("Usage: python -m src.renderer <input.rm> [output.svg]")
        sys.exit(1)
    
    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print(f"File not found: {input_path}")
        sys.exit(1)
    
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else input_path.with_suffix(".svg")
    
    print(f"Parsing {input_path}...")
    doc = parse_file(input_path)
    
    print(f"Rendering to {output_path}...")
    render_to_file(doc, output_path)
    
    print("Done!")
