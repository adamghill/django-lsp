#!/usr/bin/env python3
"""
parse_lookups.py

Parses Django's querysets.txt (RST format) and generates a JSON file
containing documentation for field lookups.

Usage:
    python scripts/parse_lookups.py querysets.txt > lookups.json
"""

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from django_lsp.generator.common import (
    clean_rst_markup,
    download_file,
    extract_code_example,
)

QUERYSETS_URL = (
    "https://raw.githubusercontent.com/django/django/main/docs/ref/models/querysets.txt"
)


@dataclass
class DjangoLookup:
    name: str
    description: str = ""
    example: str = ""
    docs_url: str = ""


def parse_querysets_rst(content: str) -> list[DjangoLookup]:
    """Parse the RST content and extract field lookups."""
    lookups = []

    # Pattern: .. fieldlookup:: LOOKUP_NAME
    lookup_pattern = re.compile(r"^\.\. fieldlookup:: (\S+)\s*$", re.MULTILINE)
    markers = list(lookup_pattern.finditer(content))

    for i, marker in enumerate(markers):
        lookup_name = marker.group(1)
        start_pos = marker.end()

        # Find end position (next marker or start of next big section)
        if i + 1 < len(markers):
            end_pos = markers[i + 1].start()
        else:
            # Look for next major section if it's the last lookup
            next_sec = content.find("\n\nQuery-related tools", start_pos)
            end_pos = next_sec if next_sec != -1 else len(content)

        section = content[start_pos:end_pos].strip()

        # Extract heading (usually lookup_name underlined)
        # Skip the heading part to get to the description
        lines = section.split("\n")
        desc_start_idx = 0
        for idx, line in enumerate(lines):
            if line.strip() == lookup_name or line.strip() == f"``{lookup_name}``":
                if idx + 1 < len(lines) and (
                    lines[idx + 1].startswith("~~~") or lines[idx + 1].startswith("---")
                ):
                    desc_start_idx = idx + 2
                    break

        description_text = "\n".join(lines[desc_start_idx:]).strip()

        # Extract example before cleaning description
        example = extract_code_example(description_text)

        # Clean description: remove examples and other directives
        # Split by the first occurrence of common example markers
        clean_desc = description_text
        for marker_str in ["Example::", ".. code-block::", "SQL equivalent:"]:
            if marker_str in clean_desc:
                clean_desc = clean_desc.split(marker_str)[0]

        description = clean_rst_markup(clean_desc)
        docs_url = f"https://docs.djangoproject.com/en/stable/ref/models/querysets/#{lookup_name}"

        lookup = DjangoLookup(
            name=lookup_name,
            description=description,
            example=example,
            docs_url=docs_url,
        )
        lookups.append(lookup)

    return lookups


def main():
    parser = argparse.ArgumentParser(
        description="Parse Django querysets.txt (RST) to JSON"
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="querysets.txt",
        help="Path to querysets.txt RST file",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output JSON file",
        default="src/django_lsp/data/lookups.json",
    )
    parser.add_argument(
        "--download",
        "-d",
        action="store_true",
        help="Download querysets.txt from Django GitHub repo",
    )

    args = parser.parse_args()

    if args.download:
        content = download_file(QUERYSETS_URL, Path(args.input))
    else:
        if not Path(args.input).exists():
            print(
                f"Error: {args.input} not found. Use --download to fetch it.",
                file=sys.stderr,
            )
            sys.exit(1)
        with open(args.input, "r", encoding="utf-8") as f:
            content = f.read()

    lookups = parse_querysets_rst(content)
    output = [asdict(lookup) for lookup in lookups]

    json_str = json.dumps(output, indent=2, ensure_ascii=False)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json_str, encoding="utf-8")
        print(f"Wrote {len(lookups)} lookups to {args.output}", file=sys.stderr)
    else:
        print(json_str)


if __name__ == "__main__":
    main()
