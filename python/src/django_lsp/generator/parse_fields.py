#!/usr/bin/env python3
"""
parse_fields.py

Parses Django's models/fields.txt and models/relations.txt (RST format)
and generates a JSON file containing documentation for model fields.
"""

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from django_lsp.generator.common import (
    clean_rst_markup,
    extract_code_example,
    slugify,
)


@dataclass
class DjangoFieldArgument:
    name: str
    description: str = ""
    default: str = ""


@dataclass
class DjangoField:
    name: str
    description: str = ""
    example: str = ""
    docs_url: str = ""
    arguments: list[DjangoFieldArgument] = field(default_factory=list)


def parse_fields_rst(content: str) -> list[DjangoField]:
    """Parse the RST content and extract model fields."""
    fields = []

    # Pattern for field class: .. class:: CharField(max_length=None, **options)
    # We want to catch the field name and optionally the arguments
    field_pattern = re.compile(r"^\.\. class:: (\w+)\((.*)\)\s*$", re.MULTILINE)
    markers = list(field_pattern.finditer(content))

    for i, marker in enumerate(markers):
        field_name = marker.group(1)
        # Skip internal or base classes if any (e.g., Field)
        if field_name == "Field":
            continue

        marker.group(2)
        start_pos = marker.end()

        # Find end position (next marker or start of next big section)
        if i + 1 < len(markers):
            end_pos = markers[i + 1].start()
        else:
            end_pos = len(content)

        section = content[start_pos:end_pos].strip()

        # Extract description (text before any attributes or notes)
        desc_lines = []
        for line in section.split("\n"):
            if (
                line.strip().startswith(".. attribute::")
                or line.strip().startswith(".. note::")
                or line.strip().startswith(".. admonition::")
            ):
                break
            desc_lines.append(line)

        description_text = "\n".join(desc_lines).strip()
        description = clean_rst_markup(description_text)
        example = extract_code_example(section)

        # Generate docs URL
        docs_url = f"https://docs.djangoproject.com/en/stable/ref/models/fields/#{slugify(field_name)}"

        dj_field = DjangoField(
            name=field_name,
            description=description,
            example=example,
            docs_url=docs_url,
        )

        # Parse specific arguments for this field
        # Pattern: .. attribute:: FieldName.arg_name
        arg_pattern = re.compile(
            rf"^\.\. attribute:: {field_name}\.(\w+)\s*$", re.MULTILINE
        )
        for arg_match in arg_pattern.finditer(section):
            arg_name = arg_match.group(1)
            arg_start = arg_match.end()

            # Find end of this argument description (next attribute or significant break)
            arg_section = section[arg_start:].split(".. attribute::")[0].strip()

            arg_desc = clean_rst_markup(
                arg_section.split("\n\n")[0]
            )  # Take first paragraph

            dj_field.arguments.append(
                DjangoFieldArgument(name=arg_name, description=arg_desc)
            )

        fields.append(dj_field)

    return fields


def parse_common_options(content: str) -> list[DjangoFieldArgument]:
    """Parse common field options (null, blank, etc.)"""
    options = []

    # Common options start after "Field options" heading
    start_match = re.search(r"Field options\n=+", content)
    if not start_match:
        return []

    end_match = re.search(r"Field types\n=+", content)
    options_content = (
        content[start_match.end() : end_match.start()]
        if end_match
        else content[start_match.end() :]
    )

    # Pattern: .. attribute:: Field.arg_name
    opt_pattern = re.compile(r"^\.\. attribute:: Field\.(\w+)\s*$", re.MULTILINE)
    for match in opt_pattern.finditer(options_content):
        opt_name = match.group(1)
        opt_start = match.end()

        # Get description
        opt_section = options_content[opt_start:].split(".. attribute::")[0].strip()
        opt_desc = clean_rst_markup(opt_section.split("\n\n")[0])

        options.append(DjangoFieldArgument(name=opt_name, description=opt_desc))

    return options


def run(
    input_path: Path,
    output_path: Optional[Path] = None,
    metadata: Optional[dict] = None,
):
    """Run the fields parser with given input and output paths."""
    if not input_path.exists():
        print(f"Error: {input_path} not found.", file=sys.stderr)
        return

    with open(input_path, "r", encoding="utf-8") as f:
        content = f.read()

    fields = parse_fields_rst(content)
    common_options = parse_common_options(content)

    data = {
        "fields": [asdict(f) for f in fields],
        "common_options": [asdict(o) for o in common_options],
    }

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
            f"Wrote {len(fields)} fields and {len(common_options)} common options to {output_path}",
            file=sys.stderr,
        )
    else:
        print(json_str)


def main():
    parser = argparse.ArgumentParser(description="Parse Django model fields to JSON")
    parser.add_argument(
        "input",
        nargs="?",
        default="docs_cache/models/fields.txt",
        help="Path to fields.txt",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="src/django_lsp/data/fields.json",
        help="Output JSON file",
    )
    args = parser.parse_args()
    run(Path(args.input), Path(args.output) if args.output else None)


if __name__ == "__main__":
    main()
