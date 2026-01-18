"""
reMarkable Annotations CLI

Convert reMarkable v6 .rm files to SVG.

Usage:
    python -m src <input.rm> [-o output.svg]
    python -m src samples/*.rm -o output/
"""

import argparse
import sys
from pathlib import Path

from .parser import parse_file, analyze_file
from .renderer import render_to_file


def main():
    parser = argparse.ArgumentParser(
        description="Convert reMarkable v6 .rm files to SVG",
        prog="remarkable-annotations"
    )
    parser.add_argument(
        "input",
        nargs="+",
        type=Path,
        help="Input .rm file(s)"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output file or directory (default: same name as input with .svg extension)"
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Analyze file(s) without converting"
    )
    
    args = parser.parse_args()
    
    # Expand glob patterns
    input_files = []
    for pattern in args.input:
        if pattern.exists():
            input_files.append(pattern)
        else:
            # Might be a glob pattern
            matches = list(Path(".").glob(str(pattern)))
            if matches:
                input_files.extend(matches)
            else:
                print(f"Warning: No files matching '{pattern}'", file=sys.stderr)
    
    if not input_files:
        print("Error: No input files found", file=sys.stderr)
        sys.exit(1)
    
    # Analyze mode
    if args.analyze:
        for input_file in input_files:
            analyze_file(input_file)
            print()
        return
    
    # Convert mode
    multiple_inputs = len(input_files) > 1
    
    if multiple_inputs:
        # Multiple inputs - output must be a directory
        if args.output:
            output_dir = args.output
            output_dir.mkdir(parents=True, exist_ok=True)
        else:
            output_dir = Path(".")
    else:
        output_dir = None
    
    for input_file in input_files:
        if output_dir:
            output_file = output_dir / input_file.with_suffix(".svg").name
        elif args.output:
            output_file = args.output
        else:
            output_file = input_file.with_suffix(".svg")
        
        print(f"Converting {input_file.name}...", end=" ", flush=True)
        
        try:
            doc = parse_file(input_file)
            render_to_file(doc, output_file)
            
            stroke_count = sum(len(layer.strokes) for layer in doc.layers)
            print(f"OK ({stroke_count} strokes)")
        except Exception as e:
            print(f"FAILED: {e}", file=sys.stderr)
            if not multiple_inputs:
                sys.exit(1)
    
    print(f"\nDone! Output in: {output_dir or output_file}")


if __name__ == "__main__":
    main()
