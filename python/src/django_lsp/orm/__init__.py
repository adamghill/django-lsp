"""
ORM module for Django LSP.

This module provides Language Server Protocol features for Django ORM operations,
including completions and hover documentation for model fields and lookups.
"""

from django_lsp.orm.completion import ORMCompletionFeature
from django_lsp.orm.document_cache import DocumentCache
from django_lsp.orm.feature_detection import (
    DJANGO_AVAILABLE,
    ORM_FEATURES_AVAILABLE,
    PARSO_AVAILABLE,
)
from django_lsp.orm.field_analyzer import FieldAnalysis, FieldAnalyzer
from django_lsp.orm.hover import ORMHoverFeature
from django_lsp.orm.manager_analyzer import ManagerCapabilityAnalyzer
from django_lsp.orm.model_loader import ModelInfo, ModelLoader
from django_lsp.orm.operation_provider import OperationProvider
from django_lsp.orm.parso_parser import ParsoParser, get_parser

__all__ = [
    "DJANGO_AVAILABLE",
    "ORM_FEATURES_AVAILABLE",
    "PARSO_AVAILABLE",
    "ParsoParser",
    "ModelLoader",
    "FieldAnalyzer",
    "FieldAnalysis",
    "ModelInfo",
    "ManagerCapabilityAnalyzer",
    "OperationProvider",
    "ORMCompletionFeature",
    "ORMHoverFeature",
    "DocumentCache",
    "get_parser",
]

_model_loader = None
_document_cache = None
_orm_completion = None
_orm_hover = None


def get_model_loader() -> ModelLoader:
    """Get the shared ModelLoader instance."""
    global _model_loader
    if _model_loader is None:
        _model_loader = ModelLoader()
    return _model_loader


def create_document_cache(model_loader: ModelLoader) -> DocumentCache:
    """Create a new DocumentCache instance."""
    return DocumentCache(model_loader)


def get_orm_completion_feature(
    model_loader: ModelLoader, document_cache: DocumentCache
) -> ORMCompletionFeature:
    """Get the ORM completion feature instance."""
    global _orm_completion
    if _orm_completion is None:
        _orm_completion = ORMCompletionFeature(model_loader, document_cache)
    return _orm_completion


def get_orm_hover_feature(
    model_loader: ModelLoader, document_cache: DocumentCache
) -> ORMHoverFeature:
    """Get the ORM hover feature instance."""
    global _orm_hover
    if _orm_hover is None:
        _orm_hover = ORMHoverFeature(model_loader, document_cache)
    return _orm_hover
