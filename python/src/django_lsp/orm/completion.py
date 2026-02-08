"""
ORM completion feature for Django LSP.

This module provides completions for Django ORM operations
including filter(), exclude(), get(), annotate(), etc.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from lsprotocol.types import (
    CompletionItem,
    CompletionItemKind,
    InsertTextFormat,
    MarkupContent,
    MarkupKind,
)

from django_lsp.orm.documentation import DocumentationGenerator

logger = logging.getLogger(__name__)


@dataclass
class FieldCompletionData:
    """Data structure for field completion information."""

    name: str
    field_type: str
    is_related: bool = False
    related_model: Optional[str] = None
    documentation: Optional[str] = None
    verbose_name: Optional[str] = None
    insert_text: Optional[str] = None


class ORMCompletionFeature:
    """Provides ORM completions for Django models."""

    def __init__(
        self,
        model_loader: Any = None,
        document_cache: Any = None,
    ) -> None:
        self.model_loader = model_loader
        self.document_cache = document_cache
        self.operation_provider = None
        self.doc_generator = DocumentationGenerator()

        if self.model_loader:
            from django_lsp.orm.operation_provider import OperationProvider

            self.operation_provider = OperationProvider(self.model_loader)

    def get_completions(
        self,
        document_uri: str,
        line: int,
        character: int,
        document_source: Optional[str] = None,
    ) -> List[CompletionItem]:
        """
        Get ORM completions at the specified position.

        Args:
            document_uri: URI of the document
            line: 0-based line number
            character: 0-based character position
            document_source: Optional document source text

        Returns:
            List of completion items
        """
        if not self.model_loader or not self.operation_provider:
            return []

        try:
            # Get ORM context from cache
            orm_context = self._get_orm_context(document_uri, line, character)
            if not orm_context:
                return []

            # Get available models
            available_models = self.model_loader.load_models()
            if not available_models:
                return []

            # Extract current argument
            typed_content = self._extract_current_argument(
                document_source or "", line, character
            )

            # Get completion data
            completion_data = self.operation_provider.get_operation_data(
                model_name=orm_context.model_name,
                manager_name=orm_context.manager_name,
                operation_name=orm_context.operation_name,
                typed_content=typed_content,
                available_models=available_models,
            )

            return self._create_completion_items(completion_data)

        except Exception as e:
            logger.error("Error getting ORM completions: %s", e)
            return []

    def _get_orm_context(
        self, document_uri: str, line: int, character: int
    ) -> Optional[Any]:
        """Get ORM context from document cache."""
        if not self.document_cache:
            return None

        try:
            return self.document_cache.get_orm_context_at_position(
                document_uri, line, character
            )
        except Exception as e:
            logger.error("Error getting ORM context: %s", e)
            return None

    def _extract_current_argument(
        self, document_source: str, line: int, character: int
    ) -> str:
        """Extract the current argument at cursor position."""
        try:
            lines = document_source.split("\n")
            if line >= len(lines):
                return ""

            current_line = lines[line]
            cursor_col = min(character, len(current_line))

            # Look backwards to find the start of the current argument
            start_pos = cursor_col
            while start_pos > 0 and (
                current_line[start_pos - 1].isalnum()
                or current_line[start_pos - 1] == "_"
            ):
                start_pos -= 1

            return current_line[start_pos:cursor_col]

        except Exception as e:
            logger.error("Error extracting current argument: %s", e)
            return ""

    def _create_completion_items(
        self, completion_data: Dict[str, Any]
    ) -> List[CompletionItem]:
        """Create LSP CompletionItem objects from completion data."""
        items: List[CompletionItem] = []

        # Add field completions
        for field in completion_data.get("fields", []):
            documentation = self.doc_generator.generate_field_documentation(
                {
                    "type": field.field_type,
                    "help_text": field.documentation or "",
                    "verbose_name": field.verbose_name or field.name,
                },
                field.name,
            )

            items.append(
                CompletionItem(
                    label=field.name,
                    kind=CompletionItemKind.Field,
                    detail=f"Field: {field.field_type}",
                    documentation=documentation,
                    sort_text=f"0_{field.name}",
                    insert_text=field.insert_text
                    if field.insert_text
                    else f"{field.name}=",
                    insert_text_format=InsertTextFormat.PlainText,
                )
            )

        # Add lookup completions
        for lookup in completion_data.get("lookups", []):
            doc = lookup.documentation
            if doc:
                # Format lookup documentation nicely
                doc_parts = [f"### Lookup: {lookup.lookup_type}"]
                if lookup.field_name:
                    doc_parts.append(f"**Field**: `{lookup.field_name}`")
                doc_parts.append(doc)

                documentation = MarkupContent(
                    kind=MarkupKind.Markdown, value="\n\n".join(doc_parts)
                )
            else:
                documentation = None

            items.append(
                CompletionItem(
                    label=lookup.name,
                    kind=CompletionItemKind.Keyword,
                    detail=f"Lookup: {lookup.lookup_type}",
                    documentation=documentation,
                    sort_text=f"1_{lookup.name}",
                    insert_text=f"{lookup.name}=",
                    insert_text_format=InsertTextFormat.PlainText,
                )
            )

        return items
