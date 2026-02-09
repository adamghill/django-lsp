import json
from pathlib import Path
from typing import Any, Dict, Optional

from lsprotocol.types import MarkupContent, MarkupKind


class DocumentationGenerator:
    """Generates documentation for Django fields and lookups."""

    def __init__(self, django_version: str = "stable"):
        self.django_version = django_version
        self._data_dir = Path(__file__).parent.parent / "data"
        self._lookups = self._load_catalog("lookups.json")
        self._fields = self._load_catalog("fields.json")
        self._functions = self._load_catalog("functions.json")
        self._meta_options = self._load_catalog("meta_options.json")

    def _load_catalog(self, filename: str) -> Dict[str, Any]:
        """Load a JSON catalog from the data directory."""
        try:
            path = self._data_dir / filename
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    content = json.load(f)

                    # Extract the data array/dict from the new metadata-enriched structure
                    if isinstance(content, dict) and "data" in content:
                        data = content["data"]
                    else:
                        data = content

                    if isinstance(data, list):
                        return {item["name"]: item for item in data}
                    elif isinstance(data, dict):
                        # Handle cases like fields.json which has nested keys
                        if "fields" in data:
                            # Merge fields and common_options for lookup
                            combined = {item["name"]: item for item in data["fields"]}
                            if "common_options" in data:
                                for opt in data["common_options"]:
                                    combined[opt["name"]] = opt
                            return combined
                        return data
        except Exception:
            pass
        return {}

    def generate_model_documentation(self, model_info: Dict[str, Any]) -> MarkupContent:
        """
        Generate documentation for a Django model.

        Args:
            model_info: Model information dictionary

        Returns:
            MarkupContent with model documentation
        """
        model_name = model_info.get("model_name", "Unknown Model")
        app_label = model_info.get("app_label", "")
        verbose_name = model_info.get("verbose_name", model_name)

        doc_parts = [f"## 🏗️ {model_name}", "---"]

        details = []
        if app_label:
            details.append(f"- **App:** `{app_label}`")
        if verbose_name and verbose_name.lower() != model_name.lower():
            details.append(f"- **Verbose name:** {verbose_name}")

        if details:
            doc_parts.append("\n".join(details))

        if model_info.get("docstring"):
            doc_parts.append(f"\n{model_info['docstring']}")

        # Summary of fields
        fields = model_info.get("fields", {})
        if fields:
            field_list = sorted(fields.keys())
            doc_parts.append("\n**Fields**: " + ", ".join(f"`{f}`" for f in field_list))

        # Add documentation link
        if app_label:
            doc_parts.append(
                f"\n[Django Documentation](https://docs.djangoproject.com/en/{self.django_version}/ref/models/options/)"
            )

        return MarkupContent(kind=MarkupKind.Markdown, value="\n\n".join(doc_parts))

    def generate_field_documentation(
        self, field_info: Dict[str, Any], field_name: str
    ) -> MarkupContent:
        """
        Generate documentation for a Django field.
        """
        field_type = field_info.get("type", "Unknown")

        doc_parts = [f"## 🏷️ {field_name}", "---"]

        # 1. Start with help_text or docstring from code analysis
        help_text = field_info.get("help_text")
        if help_text:
            doc_parts.append(help_text)

        # 2. Add rich description from catalog
        if field_type in self._fields:
            field_data = self._fields[field_type]
            description = field_data.get("description", "")
            example = field_data.get("example", "")

            if description:
                doc_parts.append(description)
            if example:
                doc_parts.append(f"**Example**:\n```python\n{example}\n```")

        # 3. Structural details
        details = [f"- **Type:** `{field_type}`"]

        if field_info.get("verbose_name") and field_info["verbose_name"] != field_name:
            details.append(f"- **Verbose name:** {field_info['verbose_name']}")

        for attr in ["max_length", "null", "blank", "default", "related_model"]:
            val = field_info.get(attr)
            if val is not None:
                label = attr.replace("_", " ").capitalize()
                details.append(f"- **{label}:** `{val}`")

        doc_parts.append("\n".join(details))

        # 4. Add link to documentation
        docs_url = self._fields.get(field_type, {}).get("docs_url")
        if not docs_url:
            docs_url = f"https://docs.djangoproject.com/en/{self.django_version}/ref/models/fields/#django.db.models.{field_type}"

        doc_parts.append(f"\n[Django Documentation]({docs_url})")

        return MarkupContent(kind=MarkupKind.Markdown, value="\n\n".join(doc_parts))

    def generate_field_lookup_documentation(
        self,
        field_info: Dict[str, Any],
        field_name: str,
        lookup_name: str,
        model_name: str,
    ) -> MarkupContent:
        """
        Generate documentation for a field lookup combination.

        Args:
            field_info: Field information dictionary
            field_name: Name of the field
            lookup_name: Name of the lookup
            model_name: Name of the model

        Returns:
            MarkupContent with field and lookup documentation
        """
        field_type = field_info.get("type", "Unknown")
        verbose_name = field_info.get("verbose_name", field_name)

        doc_parts = [f"## 🔍 {field_name}__{lookup_name}", "---"]

        details = []
        details.append(f"- **Field:** `{field_name}` ({field_type})")
        if verbose_name and verbose_name != field_name:
            details.append(f"- **Verbose name:** {verbose_name}")
        details.append(f"- **Lookup:** `{lookup_name}`")

        doc_parts.append("\n".join(details))

        # Lookup description
        lookup_description = self._get_lookup_description(
            lookup_name, field_type, field_info
        )
        doc_parts.append(lookup_description)

        # Add documentation link
        doc_parts.append(
            f"\n[Django Documentation](https://docs.djangoproject.com/en/{self.django_version}/ref/models/querysets/#{lookup_name})"
        )

        return MarkupContent(kind=MarkupKind.Markdown, value="\n\n".join(doc_parts))

    def _get_lookup_description(
        self,
        lookup_name: str,
        field_type: str,
        field_info: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Get description for a lookup."""
        # 1. Check field_info (pre-analyzed data from ModelLoader)
        if field_info and "lookups" in field_info:
            lookups = field_info["lookups"]
            for lookup in lookups:
                # lookup can be FieldLookup dataclass or dict
                l_name = getattr(lookup, "name", None) or lookup.get("name")
                if l_name == lookup_name:
                    doc = getattr(lookup, "doc", None) or lookup.get("doc")
                    if doc:
                        return str(doc)
                    break

        # 2. Check the catalog for rich documentation
        if lookup_name in self._lookups:
            lookup_data = self._lookups[lookup_name]
            description = lookup_data.get("description", "")
            example = lookup_data.get("example", "")

            doc_parts = []
            if description:
                doc_parts.append(description)
            if example:
                doc_parts.append(f"**Example**:\n```python\n{example}\n```")

            if doc_parts:
                return "\n\n".join(doc_parts)

        # 3. Fallback
        return f"Applies the `{lookup_name}` lookup to the `{field_type}` field."

    def generate_function_documentation(self, name: str) -> MarkupContent:
        """
        Generate documentation for a Django database function or aggregate.
        """
        doc_parts = [f"## 🧩 {name}", "---"]

        if name in self._functions:
            func_data = self._functions[name]
            description = func_data.get("description", "")
            example = func_data.get("example", "")
            docs_url = func_data.get("docs_url", "")
            func_type = func_data.get("type", "expression")

            if description:
                doc_parts.append(description)

            if example:
                doc_parts.append(f"**Example**:\n```python\n{example}\n```")

            doc_parts.append(f"- **Type:** {func_type.capitalize()}")

            if docs_url:
                doc_parts.append(f"\n[Django Documentation]({docs_url})")
        else:
            doc_parts.append(f"Django database function or aggregate: `{name}`.")

        return MarkupContent(kind=MarkupKind.Markdown, value="\n\n".join(doc_parts))

    def generate_meta_option_documentation(self, name: str) -> MarkupContent:
        """
        Generate documentation for a model Meta option.
        """
        doc_parts = [f"## ⚙️ Meta.{name}", "---"]

        if name in self._meta_options:
            meta_data = self._meta_options[name]
            description = meta_data.get("description", "")
            example = meta_data.get("example", "")
            docs_url = meta_data.get("docs_url", "")

            if description:
                doc_parts.append(description)

            if example:
                doc_parts.append(f"**Example**:\n```python\n{example}\n```")

            if docs_url:
                doc_parts.append(f"\n[Django Documentation]({docs_url})")
        else:
            doc_parts.append(f"Django model Meta option: `{name}`.")

        return MarkupContent(kind=MarkupKind.Markdown, value="\n\n".join(doc_parts))
