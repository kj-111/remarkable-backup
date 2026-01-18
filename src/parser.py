"""
reMarkable v6 .rm file parser

Clean-room implementation based on reverse engineering.
The v6 format uses a "tagged block" protocol where each value is prefixed
with an index and type tag.

Format Overview:
- Header: 44 bytes "reMarkable .lines file, version=6          "
- Blocks: length-prefixed chunks with type info
- Tags: varuint where index = tag >> 4, type = tag & 0xF
- Points: 14 bytes each (x, y, speed, width, direction, pressure)
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import BinaryIO, Iterator, Optional


# =============================================================================
# Constants
# =============================================================================

HEADER_V6 = b"reMarkable .lines file, version=6          "


class TagType(IntEnum):
    """Tag types indicate what kind of data follows."""
    Byte1 = 0x1     # 1-byte value (bool, u8)
    Byte4 = 0x4     # 4-byte value (float32, u32)
    Byte8 = 0x8     # 8-byte value (float64)
    Length4 = 0xC   # Length-prefixed subblock
    ID = 0xF        # CRDT ID (u8 + varuint)


class BlockType(IntEnum):
    """Top-level block types in v6 format."""
    MigrationInfo = 0x00
    SceneTree = 0x01
    TreeNode = 0x02
    GlyphItem = 0x03
    GroupItem = 0x04
    LineItem = 0x05      # This is what we want - stroke data!
    TextItem = 0x06
    RootText = 0x07
    TombstoneItem = 0x08
    AuthorIds = 0x09
    PageInfo = 0x0A
    SceneInfo = 0x0D


class Pen(IntEnum):
    """Pen/tool types."""
    PAINTBRUSH = 0
    PENCIL = 1
    BALLPOINT = 2
    MARKER = 3
    FINELINER = 4
    HIGHLIGHTER = 5
    ERASER = 6
    MECHANICAL_PENCIL = 7
    ERASER_AREA = 8
    PAINTBRUSH_2 = 12
    MECHANICAL_PENCIL_2 = 13
    PENCIL_2 = 14
    BALLPOINT_2 = 15
    MARKER_2 = 16
    FINELINER_2 = 17
    HIGHLIGHTER_2 = 18
    CALIGRAPHY = 21
    SHADER = 23


class PenColor(IntEnum):
    """Pen colors."""
    BLACK = 0
    GRAY = 1
    WHITE = 2
    YELLOW = 3
    GREEN = 4
    PINK = 5
    BLUE = 6
    RED = 7
    GRAY_OVERLAP = 8
    HIGHLIGHT = 9
    GREEN_2 = 10
    CYAN = 11
    MAGENTA = 12
    YELLOW_2 = 13


# =============================================================================
# Data Classes
# =============================================================================

@dataclass(frozen=True)
class CrdtId:
    """CRDT identifier (part1, part2)."""
    part1: int
    part2: int

    def __repr__(self) -> str:
        return f"CrdtId({self.part1}, {self.part2})"


@dataclass
class Point:
    """A single point in a stroke."""
    x: float
    y: float
    speed: int
    width: int
    direction: int
    pressure: int


@dataclass
class Stroke:
    """A stroke (line) with pen settings and points."""
    pen: Pen | int  # Unknown pen types returned as int
    color: PenColor | int  # Unknown colors returned as int
    thickness_scale: float
    points: list[Point] = field(default_factory=list)


@dataclass
class Layer:
    """A layer containing strokes."""
    name: str = ""
    visible: bool = True
    strokes: list[Stroke] = field(default_factory=list)


@dataclass
class Document:
    """Parsed .rm document."""
    layers: list[Layer] = field(default_factory=list)

    def all_strokes(self) -> Iterator[Stroke]:
        """Iterate over all strokes in all layers."""
        for layer in self.layers:
            yield from layer.strokes


# =============================================================================
# Binary Stream Reader
# =============================================================================

class BinaryReader:
    """Low-level binary reading utilities."""

    def __init__(self, data: BinaryIO):
        self.data = data

    def tell(self) -> int:
        return self.data.tell()

    def seek(self, pos: int) -> None:
        self.data.seek(pos)

    def read_bytes(self, n: int) -> bytes:
        """Read exactly n bytes, raise EOFError if not enough."""
        result = self.data.read(n)
        if len(result) != n:
            raise EOFError(f"Expected {n} bytes, got {len(result)}")
        return result

    def read_bool(self) -> bool:
        return struct.unpack("<?", self.read_bytes(1))[0]

    def read_uint8(self) -> int:
        return struct.unpack("<B", self.read_bytes(1))[0]

    def read_uint16(self) -> int:
        return struct.unpack("<H", self.read_bytes(2))[0]

    def read_uint32(self) -> int:
        return struct.unpack("<I", self.read_bytes(4))[0]

    def read_float32(self) -> float:
        return struct.unpack("<f", self.read_bytes(4))[0]

    def read_float64(self) -> float:
        return struct.unpack("<d", self.read_bytes(8))[0]

    def read_varuint(self) -> int:
        """Read a variable-length unsigned integer."""
        result = 0
        shift = 0
        while True:
            byte = self.read_uint8()
            result |= (byte & 0x7F) << shift
            if not (byte & 0x80):
                break
            shift += 7
        return result

    def read_crdt_id(self) -> CrdtId:
        """Read a CRDT ID (u8 + varuint)."""
        part1 = self.read_uint8()
        part2 = self.read_varuint()
        return CrdtId(part1, part2)


# =============================================================================
# Tagged Block Reader
# =============================================================================

class TaggedBlockReader:
    """Reader for the v6 tagged block format."""

    def __init__(self, data: BinaryIO):
        self.stream = BinaryReader(data)
        self._block_end: Optional[int] = None

    def read_header(self) -> None:
        """Read and validate the file header."""
        header = self.stream.read_bytes(len(HEADER_V6))
        if header != HEADER_V6:
            raise ValueError(f"Invalid header: {header!r}")

    def bytes_remaining(self) -> float:
        """Bytes remaining in current block."""
        if self._block_end is None:
            return float('inf')
        return self._block_end - self.stream.tell()

    # -------------------------------------------------------------------------
    # Tag Reading
    # -------------------------------------------------------------------------

    def _read_tag(self) -> tuple[int, TagType]:
        """Read a tag and return (index, type)."""
        tag = self.stream.read_varuint()
        index = tag >> 4
        tag_type = TagType(tag & 0xF)
        return index, tag_type

    def _expect_tag(self, expected_index: int, expected_type: TagType) -> None:
        """Read a tag and verify it matches expectations."""
        pos = self.stream.tell()
        index, tag_type = self._read_tag()
        if index != expected_index or tag_type != expected_type:
            self.stream.seek(pos)  # Rewind
            raise ValueError(
                f"Expected tag ({expected_index}, {expected_type.name}), "
                f"got ({index}, {tag_type.name}) at position {pos}"
            )

    def _check_tag(self, expected_index: int, expected_type: TagType) -> bool:
        """Check if next tag matches, without consuming it."""
        if self.bytes_remaining() <= 0:
            return False
        pos = self.stream.tell()
        try:
            index, tag_type = self._read_tag()
            return index == expected_index and tag_type == expected_type
        except (EOFError, ValueError):
            return False
        finally:
            self.stream.seek(pos)

    # -------------------------------------------------------------------------
    # Value Reading
    # -------------------------------------------------------------------------

    def read_bool(self, index: int) -> bool:
        """Read a tagged boolean."""
        self._expect_tag(index, TagType.Byte1)
        return self.stream.read_bool()

    def read_byte(self, index: int) -> int:
        """Read a tagged byte."""
        self._expect_tag(index, TagType.Byte1)
        return self.stream.read_uint8()

    def read_int(self, index: int) -> int:
        """Read a tagged 4-byte integer."""
        self._expect_tag(index, TagType.Byte4)
        return self.stream.read_uint32()

    def read_float(self, index: int) -> float:
        """Read a tagged 4-byte float."""
        self._expect_tag(index, TagType.Byte4)
        return self.stream.read_float32()

    def read_double(self, index: int) -> float:
        """Read a tagged 8-byte double."""
        self._expect_tag(index, TagType.Byte8)
        return self.stream.read_float64()

    def read_id(self, index: int) -> CrdtId:
        """Read a tagged CRDT ID."""
        self._expect_tag(index, TagType.ID)
        return self.stream.read_crdt_id()

    # -------------------------------------------------------------------------
    # Block Reading
    # -------------------------------------------------------------------------

    def read_block_header(self) -> Optional[tuple[int, int, int, int]]:
        """
        Read a main block header.
        Returns (block_type, length, min_version, current_version) or None at EOF.
        """
        try:
            length = self.stream.read_uint32()
        except EOFError:
            return None

        _unknown = self.stream.read_uint8()  # Always 0
        min_version = self.stream.read_uint8()
        current_version = self.stream.read_uint8()
        block_type = self.stream.read_uint8()

        return block_type, length, min_version, current_version

    def read_subblock(self, index: int) -> int:
        """Read a subblock tag and return its length."""
        self._expect_tag(index, TagType.Length4)
        return self.stream.read_uint32()

    def has_subblock(self, index: int) -> bool:
        """Check if a subblock with given index is next."""
        return self._check_tag(index, TagType.Length4)


# =============================================================================
# Document Parser
# =============================================================================

def read_point(stream: BinaryReader) -> Point:
    """Read a single point (14 bytes in v2 format)."""
    x = stream.read_float32()
    y = stream.read_float32()
    speed = stream.read_uint16()
    width = stream.read_uint16()
    direction = stream.read_uint8()
    pressure = stream.read_uint8()
    return Point(x, y, speed, width, direction, pressure)


def read_line_data(reader: TaggedBlockReader) -> Optional[Stroke]:
    """Read stroke data from a LineItem block's value subblock."""
    # Read line properties
    tool_id = reader.read_int(1)
    color_id = reader.read_int(2)
    thickness_scale = reader.read_double(3)
    _starting_length = reader.read_float(4)

    # Read points
    points_length = reader.read_subblock(5)
    point_size = 14  # v2 format
    num_points = points_length // point_size
    
    points = [read_point(reader.stream) for _ in range(num_points)]

    # Read timestamp (required but we don't use it)
    _timestamp = reader.read_id(6)

    # Try to create Pen/Color enums, fallback to raw values
    try:
        pen = Pen(tool_id)
    except ValueError:
        pen = tool_id  # Unknown pen type
    
    try:
        color = PenColor(color_id)
    except ValueError:
        color = color_id  # Unknown color

    return Stroke(pen=pen, color=color, thickness_scale=thickness_scale, points=points)


def parse_file(path: Path) -> Document:
    """
    Parse a .rm file and extract all strokes.
    
    This is a simplified parser that focuses on extracting stroke data
    for rendering. It skips text, metadata, and other block types.
    """
    doc = Document()
    # We'll collect strokes and group them later
    # For now, put everything in a single layer
    default_layer = Layer(name="Layer 1")
    doc.layers.append(default_layer)

    with open(path, "rb") as f:
        reader = TaggedBlockReader(f)
        reader.read_header()

        while True:
            header = reader.read_block_header()
            if header is None:
                break

            block_type, length, min_version, current_version = header
            block_start = reader.stream.tell()
            block_end = block_start + length

            # We only care about LineItem blocks (strokes)
            if block_type == BlockType.LineItem:
                try:
                    # Skip the SceneItem header (parent_id, item_id, etc.)
                    _parent_id = reader.read_id(1)
                    _item_id = reader.read_id(2)
                    _left_id = reader.read_id(3)
                    _right_id = reader.read_id(4)
                    deleted_length = reader.read_int(5)

                    # Skip deleted items (CRDT tombstones)
                    if deleted_length > 0:
                        continue

                    # Read the value subblock containing actual line data
                    if reader.has_subblock(6):
                        value_length = reader.read_subblock(6)
                        item_type = reader.stream.read_uint8()
                        
                        if item_type == 0x03:  # Line item type
                            stroke = read_line_data(reader)
                            if stroke and stroke.points:
                                default_layer.strokes.append(stroke)
                except Exception as e:
                    # Skip problematic blocks
                    pass

            # Skip to end of block
            reader.stream.seek(block_end)

    return doc


# =============================================================================
# CLI
# =============================================================================

def analyze_file(path: Path) -> None:
    """Analyze a .rm file and print summary."""
    print(f"File: {path.name}")
    print(f"Size: {path.stat().st_size} bytes")
    print()

    doc = parse_file(path)
    
    total_strokes = sum(len(layer.strokes) for layer in doc.layers)
    total_points = sum(
        len(stroke.points) 
        for layer in doc.layers 
        for stroke in layer.strokes
    )

    print(f"Layers: {len(doc.layers)}")
    print(f"Strokes: {total_strokes}")
    print(f"Points: {total_points}")

    if total_strokes > 0:
        print("\nPen types used:")
        pens = set()
        for layer in doc.layers:
            for stroke in layer.strokes:
                pens.add(stroke.pen)
        for pen in sorted(pens, key=lambda p: p.value if isinstance(p, Pen) else p):
            name = pen.name if isinstance(pen, Pen) else f"Unknown({pen})"
            print(f"  - {name}")

        print("\nColors used:")
        colors = set()
        for layer in doc.layers:
            for stroke in layer.strokes:
                colors.add(stroke.color)
        for color in sorted(colors, key=lambda c: c.value if isinstance(c, PenColor) else c):
            name = color.name if isinstance(color, PenColor) else f"Unknown({color})"
            print(f"  - {name}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python parser.py <file.rm>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    analyze_file(path)
