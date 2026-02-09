#!/usr/bin/env python3
"""
parse_meta.py

Parses Django's models/options.txt (RST format)
and generates a JSON file containing documentation for model Meta options.
"""

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from django_lsp.generator.common import (
    clean_rst_markup,
    extract_code_example,
    slugify,
)


@dataclass
class DjangoMetaOption:
    name: str
    description: str = ""
    example: str = ""
    docs_url: str = ""


def parse_meta_rst(content: str) -> list[DjangoMetaOption]:
    """Parse the RST content and extract Meta options."""
    options = []

    # Pattern: .. attribute:: Options.abstract
    pattern = re.compile(r"^\.\. attribute:: Options\.(\w+)\s*$", re.MULTILINE)
    markers = list(pattern.finditer(content))

    for i, marker in enumerate(markers):
        name = marker.group(1)
        start_pos = marker.end()

        # Find end position
        if i + 1 < len(markers):
            end_pos = markers[i + 1].start()
        else:
            end_pos = len(content)

        section = content[start_pos:end_pos].strip()

        # Extract description
        desc_lines = []
        for line in section.split("\n"):
            if (
                line.strip().startswith(".. attribute::")
                or line.strip().startswith(".. note::")
                or line.strip().startswith(".. admonition::")
                or line.strip().startswith(".. warning::")
            ):
                break
            desc_lines.append(line)

        description_text = "\n".join(desc_lines).strip()
        description = clean_rst_markup(description_text)
        example = extract_code_example(section)

        # Generate docs URL
        docs_url = f"https://docs.djangoproject.com/en/stable/ref/models/options/#{slugify(name)}"

        options.append(
            DjangoMetaOption(
                name=name,
                description=description,
                example=example,
                docs_url=docs_url,
            )
        )

    return options


def run(
    input_path: Path,
    output_path: Optional[Path] = None,
    metadata: Optional[dict] = None,
):
    """Run the Meta options parser with given input and output paths."""
    if not input_path.exists():
        print(f"Error: {input_path} not found.", file=sys.stderr)
        return

    with open(input_path, "r", encoding="utf-8") as f:
        content = f.read()

    options = parse_meta_rst(content)
    data = [asdict(o) for o in options]

    # Structure final output with metadata
    output = {
        "sha": metadata.get("sha") if metadata else "unknown",
        "date": metadata.get("date") if metadata else "unknown",
        "url": metadata.get("url") if metadata else "unknown",
        "data": data,
    }

    json_str = json.dumps(output, indent=2, ensure_ascii=False)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json_str, encoding="utf-8")
        print(f"Wrote {len(options)} Meta options to {output_path}", file=sys.stderr)
    else:
        print(json_str)


def main():
    parser = argparse.ArgumentParser(
        description="Parse Django model Meta options to JSON"
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="docs_cache/models/options.txt",
        help="Path to options.txt",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="src/django_lsp/data/meta_options.json",
        help="Output JSON file",
    )
    args = parser.parse_args()
    run(Path(args.input), Path(args.output) if args.output else None)


if __name__ == "__main__":
    main()
