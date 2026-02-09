"""
Documentation generation utilities for ORM features.
"""

from typing import Any, Dict, Optional

from lsprotocol.types import MarkupContent, MarkupKind


class DocumentationGenerator:
    """Generates documentation for Django fields and lookups."""

    def __init__(self, django_version: str = "stable"):
        self.django_version = django_version

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

        Args:
            field_info: Field information dictionary
            field_name: Name of the field

        Returns:
            MarkupContent with field documentation
        """
        field_type = field_info.get("type", "Unknown")

        doc_parts = [f"## 🏷️ {field_name}", "---"]

        # Add field-specific information from FieldAnalysis dict
        help_text = field_info.get("help_text")
        docstring = field_info.get("docstring")
        if help_text:
            doc_parts.append(help_text)
        elif docstring:
            doc_parts.append(docstring)

        details = [f"- **Type:** `{field_type}`"]

        if field_info.get("verbose_name") and field_info["verbose_name"] != field_name:
            details.append(f"- **Verbose name:** {field_info['verbose_name']}")

        if field_info.get("max_length"):
            details.append(f"- **Max length:** {field_info['max_length']}")

        if field_info.get("null"):
            details.append("- **Nullable:** Yes")
        else:
            details.append("- **Nullable:** No")

        if field_info.get("blank"):
            details.append("- **Blank allowed:** Yes")
        else:
            details.append("- **Blank allowed:** No")

        if field_info.get("default") is not None:
            details.append(f"- **Default:** `{field_info['default']}`")

        if field_info.get("related_model"):
            details.append(f"- **Related model:** `{field_info['related_model']}`")

        doc_parts.append("\n".join(details))

        # Add documentation link
        doc_parts.append(
            f"\n[Django Documentation](https://docs.djangoproject.com/en/{self.django_version}/ref/models/fields/#django.db.models.{field_type})"
        )

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

        return f"Applies the `{lookup_name}` lookup to the `{field_type}` field."
