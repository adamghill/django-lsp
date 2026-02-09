#!/usr/bin/env python3
"""
parse_settings.py

Parses Django's settings.txt (RST format) and generates a JSON file
that can be imported into settingsData.ts.

Usage:
    python scripts/parse_settings.py settings.txt > settings.json
    # or
    python scripts/parse_settings.py settings.txt -o settings.json
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
    download_file,
    extract_code_example,
    slugify,
    strip_trailing_pointers,
)

SETTINGS_URL = (
    "https://raw.githubusercontent.com/django/django/main/docs/ref/settings.txt"
)


@dataclass
class DjangoSetting:
    label: str
    rst_name: str = ""
    description: str = ""
    example: str = ""
    default: str = ""
    docs_url: str = ""
    nested_in: Optional[str] = None
    parent_labels: list[str] = field(default_factory=list)
    deprecated: bool = False
    category: str = "Core"
    children: Optional[list["DjangoSetting"]] = None
    name: str = ""


def determine_category(label: str, nested_in: Optional[str]) -> str:
    """Determine the category for a setting."""
    label_upper = label.upper()

    if nested_in:
        if nested_in == "DATABASES":
            return "Databases"
        if nested_in == "CACHES":
            return "Caching"
        if nested_in == "TEMPLATES":
            return "Templates"

    category_map = {
        "AUTH_": "Auth",
        "LOGIN_": "Auth",
        "LOGOUT_": "Auth",
        "PASSWORD_": "Auth",
        "SESSION_": "Auth",
        "CSRF_": "Security",
        "SECURE_": "Security",
        "SECRET_": "Security",
        "ALLOWED_": "Security",
        "X_FRAME_": "Security",
        "DATABASE": "Databases",
        "CACHE": "Caching",
        "EMAIL_": "Email",
        "DEFAULT_FROM_EMAIL": "Email",
        "SERVER_EMAIL": "Email",
        "STATIC_": "Static Files",
        "STATICFILES_": "Static Files",
        "MEDIA_": "Static Files",
        "STORAGES": "Static Files",
        "TEMPLATE": "Templates",
        "LANGUAGE_": "i18n",
        "TIME_ZONE": "i18n",
        "USE_I18N": "i18n",
        "USE_L10N": "i18n",
        "USE_TZ": "i18n",
        "LOCALE_": "i18n",
        "LANGUAGES": "i18n",
        "DATE_": "i18n",
        "DATETIME_": "i18n",
        "TIME_": "i18n",
        "INSTALLED_APPS": "Apps",
        "MIDDLEWARE": "Apps",
        "ROOT_URLCONF": "Apps",
        "WSGI_": "Apps",
        "ASGI_": "Apps",
        "LOGGING": "Logging",
        "DEBUG": "Project",
        "DEFAULT_AUTO_FIELD": "Project",
    }

    for prefix, category in category_map.items():
        if label_upper.startswith(prefix) or label_upper == prefix.rstrip("_"):
            return category

    return "Core"


def parse_settings_rst(content: str) -> list[DjangoSetting]:
    """Parse the RST content and extract settings."""
    settings = []

    # Split by setting markers
    # Pattern: .. setting:: SETTING_NAME
    setting_pattern = re.compile(r"^\.\. setting:: (\S+)\s*$", re.MULTILINE)

    # Find all setting markers and their positions
    markers = list(setting_pattern.finditer(content))

    # Track parent settings for nested detection
    # Stack stores (rst_name, label)
    parent_stack = []

    for i, marker in enumerate(markers):
        setting_name = marker.group(1)
        start_pos = marker.end()

        # Find end position (next marker or end of content)
        if i + 1 < len(markers):
            end_pos = markers[i + 1].start()
        else:
            end_pos = len(content)

        section = content[start_pos:end_pos].strip()

        # Skip if section is too short
        if len(section) < 20:
            continue

        # Determine depth by checking the underline
        underline_match = re.search(r"\n(-{3,}|~{3,}|\^{3,})\s*\n", section)

        nested_in = None
        if underline_match:
            underline = underline_match.group(1)[0]
            underline_chars = ["-", "~", "^"]
            depth = (
                underline_chars.index(underline) if underline in underline_chars else 0
            )

            # Pop stack down to the current depth
            parent_stack = parent_stack[:depth]

            # The current immediate parent is the top of the stack
            if parent_stack:
                nested_in = parent_stack[-1][0]

        # name will be calculated below based on nesting depth

        # Extract default value
        default_match = re.search(
            r"Default:\s*(.+?)(?:\n\n|\n[A-Z])", section, re.DOTALL
        )
        default_value = ""
        if default_match:
            default_value = default_match.group(1).strip()
            # Clean up multi-line defaults
            default_value = re.sub(r"\s+", " ", default_value)
            # Remove RST code blocks
            default_value = re.sub(r"``([^`]+)``", r"\1", default_value)

        # Extract description (text after default until next heading or code block)
        desc_match = re.search(
            r"Default:[^\n]*\n\n(.+?)(?:\n\n\.\. |\n[A-Z][a-z]+ [a-z]+::|$)",
            section,
            re.DOTALL,
        )
        description = ""
        if desc_match:
            description = strip_trailing_pointers(clean_rst_markup(desc_match.group(1)))

        # Extract code example
        example = extract_code_example(section)

        # Generate docs URL
        docs_url = f"https://docs.djangoproject.com/en/stable/ref/settings/#{slugify(setting_name)}"

        # Determine category
        category = determine_category(setting_name, nested_in)

        # Create the setting object
        label = setting_name
        name = setting_name

        if parent_stack:
            parent_rst, parent_label = parent_stack[-1]

            # Prepare potential prefixes to strip
            parent_prefixes = [
                parent_rst.upper().replace("-", "_") + "_",
                parent_rst.upper().replace("-", "_") + "-",
                parent_label.upper().replace(".", "_") + "_",
                parent_label.upper().replace(".", "_") + "-",
            ]

            # Add short versions of parent names as prefixes
            if "." in parent_label:
                short_parent = parent_label.split(".")[-1]
                parent_prefixes.append(short_parent.upper() + "_")
                parent_prefixes.append(short_parent.upper() + "-")

            # Special case for DATABASES
            if "DATABASES" in [p[0].upper() for p in parent_stack]:
                parent_prefixes.append("DATABASE_")
                parent_prefixes.append("DATABASE-")

            # Strip prefixes from the current setting name to get its short name
            s_clean = setting_name.upper().replace("-", "_")
            for prefix in parent_prefixes:
                if s_clean.startswith(prefix):
                    s_clean = s_clean[len(prefix) :]

            # Ensure we remove any remaining leading underscores/dashes after prefix stripping
            name = s_clean.strip("_ -")
            label = f"{parent_label}.{name}"
        else:
            label = setting_name
            name = setting_name

        # Update parent stack for NEXT settings
        if underline_match:
            parent_stack.append((setting_name, label))

        setting = DjangoSetting(
            label=label,
            rst_name=setting_name,
            description=description,
            example=example,
            default=default_value,
            docs_url=docs_url,
            nested_in=nested_in,
            parent_labels=[p[1] for p in parent_stack[:-1]],
            deprecated=False,
            category=category,
            name=name,
        )

        settings.append(setting)

    return settings


def main():
    parser = argparse.ArgumentParser(
        description="Parse Django settings.txt (RST) to JSON"
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="settings.txt",
        help="Path to settings.txt RST file (default: settings.txt)",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output JSON file",
        default="src/django_lsp/data/settings.json",
    )
    parser.add_argument(
        "--pretty", action="store_true", help="Pretty print JSON output", default=True
    )
    parser.add_argument(
        "--download",
        "-d",
        action="store_true",
        help="Download settings.txt from Django GitHub repo",
    )

    args = parser.parse_args()

    # Download or read input file
    if args.download:
        content = download_file(SETTINGS_URL, Path(args.input))
    else:
        if not Path(args.input).exists():
            print(
                f"Error: {args.input} not found. Use --download to fetch it.",
                file=sys.stderr,
            )
            sys.exit(1)
        with open(args.input, "r", encoding="utf-8") as f:
            content = f.read()

    # Parse settings
    settings = parse_settings_rst(content)

    # Create a dictionary for easy lookup
    settings_map = {s.rst_name: s for s in settings}
    top_level_settings = []

    # Nest settings
    for s in settings:
        if s.nested_in and s.nested_in in settings_map:
            parent = settings_map[s.nested_in]
            if parent.children is None:
                parent.children = []
            parent.children.append(s)
        else:
            top_level_settings.append(s)

    def get_container_type(setting: DjangoSetting) -> str:
        """Determine if a setting is a list of dicts, dict of dicts, or simple dict."""
        desc = setting.description.lower()
        example = setting.example

        # Heuristics for common Django patterns
        if "list" in desc or "[" in example:
            return "list"
        if (
            "alias" in desc
            or "alias" in setting.label.lower()
            or setting.label in ("DATABASES", "CACHES", "STORAGES", "TASKS")
        ) and "{" in example:
            return "dict_with_alias"
        if "dictionary" in desc or "{" in example:
            return "dict"
        return "other"

    def update_tree_labels(setting: DjangoSetting, current_label: str):
        """Recursively update labels to show container types."""
        setting.label = current_label

        if not setting.children:
            return

        container_type = get_container_type(setting)
        sep = "."
        if container_type == "list":
            sep = ".[]."
        elif container_type == "dict_with_alias":
            sep = ".{}."

        for child in setting.children:
            update_tree_labels(child, f"{current_label}{sep}{child.name}")

    # Update labels starting from top-level
    for s in top_level_settings:
        update_tree_labels(s, s.label)

    # Convert to JSON-serializable format
    def to_dict(s: DjangoSetting) -> dict:
        d = asdict(s)
        # Remove internal fields from output
        del d["nested_in"]
        del d["rst_name"]
        del d["parent_labels"]

        # Rename docs_url to docsUrl for JSON output
        d["docsUrl"] = d.pop("docs_url")

        if d["children"] is None:
            del d["children"]
        else:
            # Need to use the ACTUAL children objects to recurse correctly
            d["children"] = [to_dict(c) for c in s.children]

        # Remove deprecated if False
        if not d["deprecated"]:
            del d["deprecated"]

        return d

    output = [to_dict(s) for s in top_level_settings]

    # Merge extra settings if the file exists
    extra_settings_path = Path(args.input).parent / "extra_settings.json"
    if extra_settings_path.exists():
        print(f"Merging extra settings from {extra_settings_path}...", file=sys.stderr)
        extra_settings = json.loads(extra_settings_path.read_text(encoding="utf-8"))
        output = output + extra_settings
        # Sort alphabetically by label
        output.sort(key=lambda s: s["label"])

    # Output JSON
    json_str = json.dumps(output, indent=2 if args.pretty else None, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_str)
        print(f"Wrote {len(settings)} settings to {args.output}", file=sys.stderr)
    else:
        print(json_str)


if __name__ == "__main__":
    main()
