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
    extract_code_example,
    slugify,
    strip_trailing_pointers,
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


def run(
    input_path: Path,
    output_path: Optional[Path] = None,
    pretty: bool = True,
    metadata: Optional[dict] = None,
):
    """Run the settings parser with given input and output paths."""
    if not input_path.exists():
        print(f"Error: {input_path} not found.", file=sys.stderr)
        return

    with open(input_path, "r", encoding="utf-8") as f:
        content = f.read()

    settings = parse_settings_rst(content)
    settings_map = {s.rst_name: s for s in settings}
    top_level_settings = []

    for s in settings:
        if s.nested_in and s.nested_in in settings_map:
            parent = settings_map[s.nested_in]
            if parent.children is None:
                parent.children = []
            parent.children.append(s)
        else:
            top_level_settings.append(s)

    def get_container_type(setting: DjangoSetting) -> str:
        desc = setting.description.lower()
        example = setting.example
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

    for s in top_level_settings:
        update_tree_labels(s, s.label)

    def to_dict(s: DjangoSetting) -> dict:
        d = asdict(s)
        del d["nested_in"], d["rst_name"], d["parent_labels"]
        d["docsUrl"] = d.pop("docs_url")
        if d["children"] is None:
            del d["children"]
        else:
            d["children"] = [to_dict(c) for c in s.children]
        if not d["deprecated"]:
            del d["deprecated"]
        return d

    data = [to_dict(s) for s in top_level_settings]

    # Look for extra_settings.json in the data directory
    extra_settings_path = None
    if output_path:
        extra_settings_path = output_path.parent / "extra_settings.json"
    else:
        # Fallback to current directory or input parent
        extra_settings_path = input_path.parent / "extra_settings.json"

    if extra_settings_path and extra_settings_path.exists():
        print(f"Merging extra settings from {extra_settings_path}", file=sys.stderr)
        extra_settings = json.loads(extra_settings_path.read_text(encoding="utf-8"))
        data = data + extra_settings
        data.sort(key=lambda s: s["label"])

    # Structure final output with metadata
    output = {
        "sha": metadata.get("sha") if metadata else "unknown",
        "date": metadata.get("date") if metadata else "unknown",
        "url": metadata.get("url") if metadata else "unknown",
        "data": data,
    }

    json_str = json.dumps(output, indent=2 if pretty else None, ensure_ascii=False)
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json_str, encoding="utf-8")
        print(f"Wrote {len(settings)} settings to {output_path}", file=sys.stderr)
    else:
        print(json_str)


def main():
    parser = argparse.ArgumentParser(description="Parse Django settings.txt to JSON")
    parser.add_argument(
        "input",
        nargs="?",
        default="docs_cache/settings.txt",
        help="Path to settings.txt",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="src/django_lsp/data/settings.json",
        help="Output JSON file",
    )
    args = parser.parse_args()
    run(Path(args.input), Path(args.output) if args.output else None)


if __name__ == "__main__":
    main()
