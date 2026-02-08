"""
Field analysis and lookup generation.

This module handles analyzing Django model fields and generating
available lookups for different field types.

Django is an optional dependency - this module gracefully handles
cases where Django is not installed.
"""

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Check for Django availability
DJANGO_AVAILABLE = False
_Field: Any = None
_RelatedField: Any = None

try:
    from django.db.models import Field
    from django.db.models.fields.related import RelatedField

    DJANGO_AVAILABLE = True
    _Field = Field
    _RelatedField = RelatedField
except ImportError:
    logger.debug("Django not available - field analysis disabled")


@dataclass
class FieldLookup:
    """Represents a Django field lookup with documentation."""

    name: str
    doc: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        """Convert to dictionary format."""
        return {"name": self.name, "doc": self.doc}


@dataclass
class FieldAnalysis:
    """Comprehensive analysis of a Django field."""

    type: str
    name: str
    verbose_name: str
    help_text: str
    null: bool
    blank: bool
    default: Optional[Any]
    lookups: List[FieldLookup] = field(default_factory=list)
    max_length: Optional[int] = None
    choices: Optional[Any] = None
    related_model: Optional[str] = None
    related_app: Optional[str] = None
    docstring: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        result = {
            "type": self.type,
            "name": self.name,
            "verbose_name": self.verbose_name,
            "help_text": self.help_text,
            "docstring": self.docstring,
            "null": self.null,
            "blank": self.blank,
            "default": self.default,
            "lookups": [lookup.to_dict() for lookup in self.lookups],
        }

        if self.max_length is not None:
            result["max_length"] = self.max_length
        if self.choices is not None:
            result["choices"] = self.choices
        if self.related_model is not None:
            result["related_model"] = self.related_model
        if self.related_app is not None:
            result["related_app"] = self.related_app

        return result


class FieldAnalyzer:
    """Analyzes Django model fields and generates lookups."""

    @staticmethod
    @lru_cache(maxsize=128)
    def get_field_lookups(field_obj: Any) -> List[FieldLookup]:
        """
        Get available lookups for a Django field.

        Args:
            field_obj: Django field instance

        Returns:
            List of FieldLookup objects
        """
        lookups: List[FieldLookup] = []

        if not DJANGO_AVAILABLE:
            return lookups

        if hasattr(field_obj, "get_lookups"):
            try:
                lookup_dict = field_obj.get_lookups()
                for lookup_name, lookup_class in lookup_dict.items():
                    doc = getattr(lookup_class, "__doc__", None)
                    if doc:
                        doc = doc.strip()
                        # Clean up documentation
                        if doc.startswith("Return a"):
                            doc = doc[8:]
                        elif doc.startswith("Returns a"):
                            doc = doc[9:]

                    lookups.append(FieldLookup(name=lookup_name, doc=doc))

            except Exception as e:
                logger.warning(
                    "Error getting lookups for %s: %s", type(field_obj).__name__, e
                )

        return lookups

    @staticmethod
    def analyze_field(field_obj: Any) -> FieldAnalysis:
        """
        Analyze a Django field and return comprehensive information.

        Args:
            field_obj: Django field instance

        Returns:
            FieldAnalysis object
        """
        if not DJANGO_AVAILABLE:
            raise RuntimeError("Django not available")

        if not isinstance(field_obj, _Field):
            raise ValueError("Expected Django Field, got %s" % type(field_obj).__name__)

        lookups = FieldAnalyzer.get_field_lookups(field_obj)

        field_analysis = FieldAnalysis(
            type=field_obj.__class__.__name__,
            name=field_obj.name,
            verbose_name=getattr(field_obj, "verbose_name", field_obj.name),
            help_text=getattr(field_obj, "help_text", ""),
            docstring=_get_field_docstring(field_obj),
            null=getattr(field_obj, "null", False),
            blank=getattr(field_obj, "blank", False),
            default=getattr(field_obj, "default", None),
            lookups=lookups,
        )

        if hasattr(field_obj, "max_length") and field_obj.max_length:
            field_analysis.max_length = field_obj.max_length

        if hasattr(field_obj, "choices") and field_obj.choices:
            field_analysis.choices = field_obj.choices

        # Handle related fields
        if isinstance(field_obj, _RelatedField):
            if hasattr(field_obj, "related_model") and field_obj.related_model:
                field_analysis.related_model = field_obj.related_model.__name__
                field_analysis.related_app = field_obj.related_model._meta.app_label

        return field_analysis

    @staticmethod
    def clear_cache() -> None:
        """Clear the lookup cache."""
        FieldAnalyzer.get_field_lookups.cache_clear()
        logger.debug("Field lookup cache cleared")


def _get_field_docstring(field_obj: Any) -> Optional[str]:
    """Extract a meaningful docstring for the field."""
    doc = getattr(field_obj, "__doc__", None) or getattr(
        field_obj.__class__, "__doc__", None
    )
    if not doc:
        return None
    doc = doc.strip()
    return doc or None
