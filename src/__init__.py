"""
reMarkable Annotations Parser

Convert reMarkable v6 .rm files to SVG.

Usage:
    from src import parse_file, render_to_file

    doc = parse_file("file.rm")
    render_to_file(doc, "output.svg")

CLI:
    python -m src <input.rm> -o <output.svg>
"""

from .parser import (
    Document,
    Layer,
    Stroke,
    Point,
    Pen,
    PenColor,
    parse_file,
)
from .renderer import (
    render_svg,
    render_to_file,
)
from .export import (
    export_backup,
)

__all__ = [
    "Document",
    "Layer", 
    "Stroke",
    "Point",
    "Pen",
    "PenColor",
    "parse_file",
    "render_svg",
    "render_to_file",
    "export_backup",
]

__version__ = "0.1.0"
