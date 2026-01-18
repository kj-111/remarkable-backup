"""
Shared constants for reMarkable export tools.
"""

from .parser import Pen, PenColor

# DPI-based scaling
RM_DPI = 227
PDF_DPI = 72.0
RM_TO_PDF_SCALE = RM_DPI / PDF_DPI  # ~3.1528

# Color mapping - RGB tuples (0-255)
COLOR_MAP_RGB = {
    PenColor.BLACK: (0, 0, 0),
    PenColor.GRAY: (125, 125, 125),
    PenColor.WHITE: (255, 255, 255),
    PenColor.YELLOW: (255, 235, 59),
    PenColor.GREEN: (76, 175, 80),
    PenColor.PINK: (233, 30, 99),
    PenColor.BLUE: (48, 74, 224),  # reMarkable uses #304AE0
    PenColor.RED: (244, 67, 54),
    PenColor.GRAY_OVERLAP: (158, 158, 158),
    PenColor.HIGHLIGHT: (255, 235, 59),
    PenColor.GREEN_2: (139, 195, 74),
    PenColor.CYAN: (0, 188, 212),
    PenColor.MAGENTA: (156, 39, 176),
    PenColor.YELLOW_2: (255, 193, 7),
}

# Color mapping - hex strings (for SVG)
COLOR_MAP_HEX = {
    color: f"#{r:02x}{g:02x}{b:02x}"
    for color, (r, g, b) in COLOR_MAP_RGB.items()
}

# Base stroke widths for different pen types
PEN_BASE_WIDTH = {
    Pen.PAINTBRUSH: 3.0,
    Pen.PENCIL: 1.5,
    Pen.BALLPOINT: 1.2,
    Pen.MARKER: 4.0,
    Pen.FINELINER: 0.8,
    Pen.HIGHLIGHTER: 12.0,
    Pen.ERASER: 5.0,
    Pen.MECHANICAL_PENCIL: 0.6,
    Pen.ERASER_AREA: 5.0,
    Pen.PAINTBRUSH_2: 3.0,
    Pen.MECHANICAL_PENCIL_2: 0.6,
    Pen.PENCIL_2: 1.5,
    Pen.BALLPOINT_2: 1.2,
    Pen.MARKER_2: 4.0,
    Pen.FINELINER_2: 0.8,
    Pen.HIGHLIGHTER_2: 12.0,
    Pen.CALIGRAPHY: 2.5,
    Pen.SHADER: 8.0,
}

# Pens that should render as semi-transparent
TRANSPARENT_PENS = {Pen.HIGHLIGHTER, Pen.HIGHLIGHTER_2, Pen.SHADER}

# Eraser pens
ERASER_PENS = {Pen.ERASER, Pen.ERASER_AREA}
