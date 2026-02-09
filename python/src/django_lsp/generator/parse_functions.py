#!/usr/bin/env python3
"""
parse_functions.py

Parses Django's database functions and aggregations (RST format)
and generates a JSON file containing documentation for them.
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
class DjangoFunction:
    name: str
    description: str = ""
    example: str = ""
    docs_url: str = ""
    type: str = "function"  # or "aggregate"


def parse_functions_rst(
    content: str, func_type: str = "function"
) -> list[DjangoFunction]:
    """Parse the RST content and extract functions/aggregates."""
    functions = []

    # Pattern: .. class:: FunctionName(*args)
    pattern = re.compile(r"^\.\. class:: (\w+)\(.*\)\s*$", re.MULTILINE)
    markers = list(pattern.finditer(content))

    for i, marker in enumerate(markers):
        name = marker.group(1)
        # Skip generic classes
        if name in ("Func", "Aggregate", "RelatedManager"):
            continue

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
        category = "functions" if func_type == "function" else "aggregation"
        docs_url = f"https://docs.djangoproject.com/en/stable/ref/models/{category}/#{slugify(name)}"

        functions.append(
            DjangoFunction(
                name=name,
                description=description,
                example=example,
                docs_url=docs_url,
                type=func_type,
            )
        )

    return functions


def run(
    docs_dir: Path, output_path: Optional[Path] = None, metadata: Optional[dict] = None
):
    """Run the functions parser with given docs directory and output path."""
    functions = []

    # Process database functions
    func_file = docs_dir / "database-functions.txt"
    if func_file.exists():
        with open(func_file, "r", encoding="utf-8") as f:
            functions.extend(parse_functions_rst(f.read(), "function"))

    # Process aggregates from querysets.txt
    qs_file = docs_dir / "querysets.txt"
    if qs_file.exists():
        with open(qs_file, "r", encoding="utf-8") as f:
            qs_content = f.read()
            # Find the aggregation section
            agg_match = re.search(r"Aggregation functions\n-+\n", qs_content)
            if agg_match:
                agg_content = qs_content[agg_match.end() :]
                functions.extend(parse_functions_rst(agg_content, "aggregate"))

    data = [asdict(f) for f in functions]

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
        print(
            f"Wrote {len(functions)} functions/aggregates to {output_path}",
            file=sys.stderr,
        )
    else:
        print(json_str)


def main():
    parser = argparse.ArgumentParser(
        description="Parse Django database functions to JSON"
    )
    parser.add_argument(
        "--docs-dir",
        default="docs_cache/models",
        help="Directory containing RST files",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="src/django_lsp/data/functions.json",
        help="Output JSON file",
    )
    args = parser.parse_args()
    run(Path(args.docs_dir), Path(args.output) if args.output else None)


if __name__ == "__main__":
    main()
