import json
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional


@dataclass
class DjangoSetting:
    """Represents a Django setting from the catalog."""

    label: str
    category: str
    description: str
    example: str
    default: str
    docs_url: str
    nested_in: Optional[str] = None
    deprecated: bool = False
    children: list["DjangoSetting"] = field(default_factory=list)
    name: str = ""

    def get_markdown_docs(self, django_version: str = "stable") -> str:
        """Return formatted markdown documentation for hover."""
        parts = [f"## ⚙️ {self.label}", "---"]

        details = []
        if self.default:
            details.append(f"- **Default:** `{self.default}`")
        if self.category:
            details.append(f"- **Category:** {self.category}")
        if self.deprecated:
            details.append("- **Status:** ⚠️ Deprecated")

        if details:
            parts.append("\n".join(details))

        if self.description:
            parts.append(f"\n{self.description}")

        if self.example:
            parts.append(f"\n**Example:**\n```python\n{self.example}\n```")

        if self.docs_url:
            url = self.docs_url
            if django_version != "stable":
                url = url.replace("/stable/", f"/{django_version}/")
            parts.append(f"\n[Django Documentation]({url})")

        return "\n\n".join(parts)

    @property
    def markdown_docs(self) -> str:
        """Deprecated: use get_markdown_docs(version) instead."""
        return self.get_markdown_docs()


class SettingsCatalog:
    """Manages the Django settings catalog."""

    def __init__(self, catalog_path: Optional[Path] = None):
        if catalog_path is None:
            # Try to find settings.json in common locations
            current_dir = Path(__file__).parent

            # 1. New consolidated layout: ./data/settings.json
            p1 = current_dir / "data" / "settings.json"

            # 2. Legacy extension layout: ../catalog/settings.json
            p2 = current_dir.parent / "catalog" / "settings.json"

            if p1.exists():
                catalog_path = p1
            elif p2.exists():
                catalog_path = p2
            else:
                # Fallback to current dir if nothing else matches
                catalog_path = p1

        self.settings: dict[str, DjangoSetting] = {}
        self._load_catalog(catalog_path)

    def _load_catalog(self, path: Path) -> None:
        """Load settings from JSON catalog."""
        if not path.exists():
            return

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        def process_setting(
            data: dict, parent: Optional[DjangoSetting] = None
        ) -> DjangoSetting:
            children_data = data.pop("children", [])

            setting = DjangoSetting(
                label=data.get("label", ""),
                category=data.get("category", "Core"),
                description=data.get("description", ""),
                example=data.get("example", ""),
                default=data.get("default", ""),
                docs_url=data.get("docsUrl", ""),
                nested_in=parent.label if parent else None,
                deprecated=data.get("deprecated", False),
                name=data.get("name", ""),
            )

            # Register in flat map
            self.settings[setting.label] = setting

            # Process children
            for child_data in children_data:
                child = process_setting(child_data, parent=setting)
                setting.children.append(child)

            return setting

        for item in data:
            process_setting(item)

    def get(self, name: str) -> Optional[DjangoSetting]:
        """Get a setting by name."""
        return self.settings.get(name)

    def get_all(
        self, include_nested: bool = True, include_deprecated: bool = False
    ) -> list[DjangoSetting]:
        """Get all settings, optionally filtering nested/deprecated."""
        result = []
        for setting in self.settings.values():
            if not include_deprecated and setting.deprecated:
                continue
            if not include_nested and setting.nested_in:
                continue
            result.append(setting)
        return result

    def get_nested(self, parent: str) -> list[DjangoSetting]:
        """Get settings that are nested inside a parent setting."""
        parent_setting = self.settings.get(parent)
        if parent_setting:
            return parent_setting.children
        return []

    def find_similar(self, name: str, threshold: float = 0.6) -> list[DjangoSetting]:
        """Find settings with names similar to the given name (for typo detection)."""
        results = []
        name_upper = name.upper()

        for setting in self.settings.values():
            # Skip nested settings for top-level typo detection
            if setting.nested_in:
                continue

            ratio = SequenceMatcher(None, name_upper, setting.label).ratio()
            if ratio >= threshold and name_upper != setting.label:
                results.append((ratio, setting))

        # Sort by similarity (highest first)
        results.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in results[:3]]  # Return top 3
