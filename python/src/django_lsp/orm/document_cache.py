"""
Document cache manager for ORM operations.

This module provides intelligent caching of Django models and document
information to avoid reloading on every completion request.
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ORMOperation:
    """Represents an ORM operation with its position and context."""

    range_start_line: int
    range_start_character: int
    range_end_line: int
    range_end_character: int
    model_name: str
    manager_name: str
    operation_name: str
    context_type: str
    field_name: Optional[str] = None
    lookup_name: Optional[str] = None
    is_self: bool = False


class DocumentCache:
    """
    Cache manager for documents and Django models.

    Provides:
    - Models loaded once per workspace and cached
    - Document information cached with proper invalidation
    - ORM operations cached with position ranges
    - Thread-safe access
    """

    def __init__(self, model_loader: Any) -> None:
        self.model_loader = model_loader

        # Cache for Django models
        self._model_cache: Dict[str, Dict[str, Any]] = {}
        self._model_cache_timestamps: Dict[str, float] = {}
        self._model_cache_lock = threading.RLock()

        # Cache for document information
        self._document_cache: Dict[str, Dict[str, Any]] = {}
        self._document_cache_timestamps: Dict[str, float] = {}
        self._document_cache_lock = threading.RLock()

        # Cache for document source
        self._document_source_cache: Dict[str, str] = {}
        self._document_source_lock = threading.RLock()

        # Cache for ORM operations
        self._orm_operations_cache: Dict[str, List[ORMOperation]] = {}
        self._orm_operations_timestamps: Dict[str, float] = {}
        self._orm_operations_lock = threading.RLock()

        # Track loaded workspaces
        self._loaded_workspaces: Set[str] = set()
        self._workspace_lock = threading.RLock()

        # Cache TTL settings
        self._model_cache_ttl = 300  # 5 minutes
        self._document_cache_ttl = 60  # 1 minute
        self._orm_operations_ttl = 30  # 30 seconds

    def get_models_for_workspace(self, workspace_root: str) -> Dict[str, Any]:
        """Get Django models for a workspace with caching."""
        with self._model_cache_lock:
            current_time = time.time()

            if workspace_root in self._model_cache:
                cache_time = self._model_cache_timestamps.get(workspace_root, 0)
                if current_time - cache_time < self._model_cache_ttl:
                    return self._model_cache[workspace_root]
                else:
                    self._model_cache.pop(workspace_root, None)
                    self._model_cache_timestamps.pop(workspace_root, None)

            try:
                models = self.model_loader.load_models(workspace_root)
                if not models:
                    return {}

                self._model_cache[workspace_root] = models
                self._model_cache_timestamps[workspace_root] = current_time

                with self._workspace_lock:
                    self._loaded_workspaces.add(workspace_root)

                return models

            except Exception as e:
                logger.error("Failed to load models for %s: %s", workspace_root, e)
                return {}

    def invalidate_workspace_models(self, workspace_root: str) -> None:
        """Invalidate cached models for a workspace."""
        with self._model_cache_lock:
            self._model_cache.pop(workspace_root, None)
            self._model_cache_timestamps.pop(workspace_root, None)

        with self._workspace_lock:
            self._loaded_workspaces.discard(workspace_root)

    def cache_document_source(self, document_uri: str, source: str) -> None:
        """Cache document source code."""
        with self._document_source_lock:
            self._document_source_cache[document_uri] = source

    def get_document_source(self, document_uri: str) -> Optional[str]:
        """Get cached document source code."""
        with self._document_source_lock:
            return self._document_source_cache.get(document_uri)

    def cache_orm_operations(
        self, document_uri: str, orm_operations: List[ORMOperation]
    ) -> None:
        """Cache ORM operations with position ranges."""
        with self._orm_operations_lock:
            self._orm_operations_cache[document_uri] = orm_operations
            self._orm_operations_timestamps[document_uri] = time.time()

    def get_orm_context_at_position(
        self, document_uri: str, line: int, character: int
    ) -> Optional[ORMOperation]:
        """Get ORM context at a specific position."""
        with self._orm_operations_lock:
            current_time = time.time()

            if document_uri in self._orm_operations_cache:
                cache_time = self._orm_operations_timestamps.get(document_uri, 0)
                if current_time - cache_time < self._orm_operations_ttl:
                    orm_operations = self._orm_operations_cache[document_uri]

                    for orm_op in orm_operations:
                        if orm_op.range_start_line <= line <= orm_op.range_end_line:
                            if (
                                line == orm_op.range_start_line
                                and character < orm_op.range_start_character
                            ):
                                continue
                            if (
                                line == orm_op.range_end_line
                                and character > orm_op.range_end_character
                            ):
                                continue
                            return orm_op
                else:
                    self._orm_operations_cache.pop(document_uri, None)
                    self._orm_operations_timestamps.pop(document_uri, None)

            return None

    def get_all_orm_operations(self, document_uri: str) -> List[ORMOperation]:
        """Get all cached ORM operations for a document."""
        with self._orm_operations_lock:
            current_time = time.time()

            if document_uri in self._orm_operations_cache:
                cache_time = self._orm_operations_timestamps.get(document_uri, 0)
                if current_time - cache_time < self._orm_operations_ttl:
                    return self._orm_operations_cache[document_uri]
                else:
                    self._orm_operations_cache.pop(document_uri, None)
                    self._orm_operations_timestamps.pop(document_uri, None)

            return []

    def invalidate_document(self, document_uri: str) -> None:
        """Invalidate cached information for a document."""
        with self._document_cache_lock:
            self._document_cache.pop(document_uri, None)
            self._document_cache_timestamps.pop(document_uri, None)

        with self._document_source_lock:
            self._document_source_cache.pop(document_uri, None)

        with self._orm_operations_lock:
            self._orm_operations_cache.pop(document_uri, None)
            self._orm_operations_timestamps.pop(document_uri, None)

    def clear_all(self) -> None:
        """Clear all cached data."""
        with self._model_cache_lock:
            self._model_cache.clear()
            self._model_cache_timestamps.clear()

        with self._document_cache_lock:
            self._document_cache.clear()
            self._document_cache_timestamps.clear()

        with self._document_source_lock:
            self._document_source_cache.clear()

        with self._orm_operations_lock:
            self._orm_operations_cache.clear()
            self._orm_operations_timestamps.clear()

        with self._workspace_lock:
            self._loaded_workspaces.clear()
