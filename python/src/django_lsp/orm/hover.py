"""
ORM hover feature for Django LSP.

This module provides hover documentation for Django ORM operations,
including field documentation and lookup information.
"""

import logging
from typing import Any, Optional

from lsprotocol import types

from django_lsp.orm.documentation import DocumentationGenerator

logger = logging.getLogger(__name__)


class ORMHoverFeature:
    """Handles hover requests for Django ORM operations."""

    def __init__(
        self,
        model_loader: Any = None,
        document_cache: Any = None,
    ) -> None:
        self.model_loader = model_loader
        self.document_cache = document_cache
        self.doc_generator = DocumentationGenerator()
        logger.debug("ORMHoverFeature initialized")

    def get_hover(
        self,
        document_uri: str,
        line: int,
        character: int,
    ) -> Optional[types.Hover]:
        """
        Get ORM hover information at the specified position.

        Args:
            document_uri: URI of the document
            line: 0-based line number
            character: 0-based character position

        Returns:
            Hover information or None
        """
        if not self.model_loader or not self.document_cache:
            return None

        try:
            # Get ORM context from cache
            orm_context = self.document_cache.get_orm_context_at_position(
                document_uri, line, character
            )
            if not orm_context:
                return None

            # Get model info
            model_info = self.model_loader.get_model_info(orm_context.model_name)
            if not model_info:
                return None

            # Get field info
            field_name = orm_context.field_name
            word_range = None
            if not field_name:
                word_info = self._get_word_at_position(document_uri, line, character)
                if word_info:
                    field_name, word_range = word_info
                    if field_name in {
                        orm_context.model_name,
                        orm_context.manager_name,
                        orm_context.operation_name,
                    }:
                        field_name = None
                        word_range = None

            # If no field name, show model documentation
            if not field_name:
                documentation = self.doc_generator.generate_model_documentation(
                    model_info.to_dict()
                    if hasattr(model_info, "to_dict")
                    else vars(model_info)
                )
                return types.Hover(
                    contents=documentation,
                    range=types.Range(
                        start=types.Position(
                            line=orm_context.range_start_line,
                            character=orm_context.range_start_character,
                        ),
                        end=types.Position(
                            line=orm_context.range_end_line,
                            character=orm_context.range_end_character,
                        ),
                    ),
                )

            # 2. Check if it's a field
            base_field_name = field_name
            lookup_name = None
            if "__" in field_name:
                base_field_name, lookup_name = field_name.split("__", 1)

            if base_field_name in model_info.fields:
                field_analysis = model_info.fields[base_field_name]
                field_dict = (
                    field_analysis.to_dict()
                    if hasattr(field_analysis, "to_dict")
                    else vars(field_analysis)
                )

                if lookup_name:
                    documentation = (
                        self.doc_generator.generate_field_lookup_documentation(
                            field_dict,
                            base_field_name,
                            lookup_name,
                            orm_context.model_name,
                        )
                    )
                else:
                    documentation = self.doc_generator.generate_field_documentation(
                        field_dict, base_field_name
                    )

                return types.Hover(contents=documentation, range=word_range)

            # 3. Check if it is a function or aggregate
            if field_name in self.doc_generator._functions:
                documentation = self.doc_generator.generate_function_documentation(
                    field_name
                )
                return types.Hover(contents=documentation, range=word_range)

            # 4. Check if it is a Meta option
            # Note: This is a bit optimistic as we don't have full Meta context yet,
            # but we can try if it's in the catalog
            if field_name in self.doc_generator._meta_options:
                documentation = self.doc_generator.generate_meta_option_documentation(
                    field_name
                )
                return types.Hover(contents=documentation, range=word_range)

            return None

        except Exception as e:
            logger.exception("Error in ORMHoverFeature.get_hover: %s", e)
            return None

    def _get_word_at_position(
        self, document_uri: str, line: int, character: int
    ) -> Optional[tuple[str, types.Range]]:
        """Get the word and range at the given position."""
        if not self.document_cache:
            return None

        source = self.document_cache.get_document_source(document_uri)
        if not source:
            return None

        lines = source.split("\n")
        if line >= len(lines):
            return None

        current_line = lines[line]
        if not current_line:
            return None

        start = min(character, len(current_line))
        end = start

        while start > 0 and (
            current_line[start - 1].isalnum() or current_line[start - 1] == "_"
        ):
            start -= 1

        while end < len(current_line) and (
            current_line[end].isalnum() or current_line[end] == "_"
        ):
            end += 1

        if start == end:
            return None

        return (
            current_line[start:end],
            types.Range(
                start=types.Position(line=line, character=start),
                end=types.Position(line=line, character=end),
            ),
        )
