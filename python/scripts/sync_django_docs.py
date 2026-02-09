#!/usr/bin/env python3
"""
sync_django_docs.py

Syncs Django documentation (RST files) from GitHub to a local cache.
This avoids needing a full Git submodule while keeping doc versions consistent.
"""

import argparse
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Files to sync from Django's GitHub
# Format: {local_rel_path: remote_rel_path_from_docs_ref}
DOCS_MAP = {
    "settings.txt": "settings.txt",
    "models/querysets.txt": "models/querysets.txt",
    "models/fields.txt": "models/fields.txt",
    "models/relations.txt": "models/relations.txt",
    "models/options.txt": "models/options.txt",
    "models/database-functions.txt": "models/database-functions.txt",
    "templates/builtins.txt": "templates/builtins.txt",
}

DEFAULT_VERSION = "7c54fee7760b1c61fd7f9cb7cc6a2965f4236137"


def download_file(url: str, dest: Path):
    """Download a file from a URL to a destination."""
    print(f"Downloading {url} -> {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)

    with urllib.request.urlopen(url) as response:
        content = response.read().decode("utf-8")
        dest.write_text(content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Sync Django docs for LSP")
    parser.add_argument(
        "--version",
        default=DEFAULT_VERSION,
        help=f"Django version or commit hash (default: {DEFAULT_VERSION})",
    )
    parser.add_argument(
        "--cache-dir",
        default="docs_cache",
        help="Directory to store cached docs (default: docs_cache)",
    )

    parser.add_argument(
        "--no-gen",
        action="store_true",
        help="Do not regenerate JSON catalogs after syncing",
    )

    args = parser.parse_args()
    cache_dir = Path(args.cache_dir)

    base_url = (
        f"https://raw.githubusercontent.com/django/django/{args.version}/docs/ref/"
    )
    retrieved_at = datetime.now(timezone.utc).isoformat()

    count = 0
    for local_path, remote_path in DOCS_MAP.items():
        url = base_url + remote_path
        dest = cache_dir / local_path
        try:
            download_file(url, dest)
            count += 1
        except Exception as e:
            print(f"Error downloading {url}: {e}", file=sys.stderr)

    print(f"\nSynced {count} documentation files to {cache_dir}")

    if args.no_gen:
        print("Skipping JSON generation.")
        return

    print("\nGenerating JSON catalogs...")

    try:
        from django_lsp.generator import (
            parse_fields,
            parse_functions,
            parse_lookups,
            parse_meta,
            parse_settings,
        )

        data_dir = Path("src/django_lsp/data")

        def create_metadata(remote_path: str) -> dict:
            return {
                "sha": args.version,
                "date": retrieved_at,
                "url": base_url + remote_path,
            }

        # 1. Settings
        parse_settings.run(
            cache_dir / "settings.txt",
            data_dir / "settings.json",
            metadata=create_metadata(DOCS_MAP["settings.txt"]),
        )

        # 2. Lookups
        parse_lookups.run(
            cache_dir / "models/querysets.txt",
            data_dir / "lookups.json",
            metadata=create_metadata(DOCS_MAP["models/querysets.txt"]),
        )

        # 3. Fields
        parse_fields.run(
            cache_dir / "models/fields.txt",
            data_dir / "fields.json",
            metadata=create_metadata(DOCS_MAP["models/fields.txt"]),
        )

        # 4. Functions & Aggregates
        parse_functions.run(
            cache_dir / "models",
            data_dir / "functions.json",
            metadata=create_metadata(DOCS_MAP["models/database-functions.txt"]),
        )

        # 5. Meta Options
        parse_meta.run(
            cache_dir / "models/options.txt",
            data_dir / "meta_options.json",
            metadata=create_metadata(DOCS_MAP["models/options.txt"]),
        )

        print("\nAll JSON catalogs regenerated successfully.")

    except ImportError as e:
        print(f"Error importing parsers: {e}", file=sys.stderr)
        print("Make sure you are running from the 'python' directory.", file=sys.stderr)


if __name__ == "__main__":
    main()
