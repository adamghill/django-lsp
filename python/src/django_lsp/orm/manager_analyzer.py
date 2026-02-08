"""
Manager analysis and capability discovery.

This module analyzes Django model managers to determine what operations
they support and what arguments they accept.

Django is an optional dependency.
"""

import logging
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)

# Check for Django availability
DJANGO_AVAILABLE = False
_Manager: Any = None
_QuerySet: Any = None

try:
    from django.db.models import Manager, QuerySet

    DJANGO_AVAILABLE = True
    _Manager = Manager
    _QuerySet = QuerySet
except ImportError:
    logger.debug("Django not available - manager analysis disabled")


class ManagerCapabilityAnalyzer:
    """Analyzes Django model managers to determine their capabilities."""

    def analyze_manager_capabilities(self, manager: Any) -> Dict[str, Any]:
        """
        Analyze what operations a manager supports.

        Args:
            manager: Django manager instance

        Returns:
            Dictionary containing manager capabilities
        """
        if not DJANGO_AVAILABLE:
            return {
                "operations": set(),
                "manager_type": "Unknown",
            }

        try:
            capabilities = {
                "operations": self._discover_operations(manager),
                "custom_methods": self._discover_custom_methods(manager),
                "queryset_methods": self._discover_queryset_methods(manager),
                "manager_type": self._classify_manager(manager),
                "supports_filtering": self._supports_filtering(manager),
                "supports_annotation": self._supports_annotation(manager),
                "supports_related_loading": self._supports_related_loading(manager),
            }

            return capabilities

        except Exception as e:
            logger.warning("Error analyzing manager: %s", e)
            return {
                "operations": {"filter", "exclude", "get", "all"},
                "custom_methods": [],
                "queryset_methods": set(),
                "manager_type": "Unknown",
                "supports_filtering": True,
                "supports_annotation": False,
                "supports_related_loading": False,
            }

    def _discover_operations(self, manager: Any) -> Set[str]:
        """Discover what ORM operations this manager supports."""
        operations = set()

        try:
            if hasattr(manager, "get_queryset"):
                queryset = manager.get_queryset()

                # Core operations
                core_operations = {"filter", "exclude", "get", "all", "first", "last"}
                operations.update(core_operations)

                # Additional operations based on queryset type
                optional_methods = [
                    "annotate",
                    "select_related",
                    "prefetch_related",
                    "order_by",
                    "values",
                    "values_list",
                    "distinct",
                    "only",
                    "defer",
                ]
                for method in optional_methods:
                    if hasattr(queryset, method):
                        operations.add(method)

            # Add custom operations
            custom_operations = self._discover_custom_methods(manager)
            operations.update(custom_operations)

        except Exception as e:
            logger.warning("Error discovering operations: %s", e)
            operations.update({"filter", "exclude", "get", "all"})

        return operations

    def _discover_custom_methods(self, manager: Any) -> List[str]:
        """Discover custom methods defined on the manager."""
        custom_methods = []

        if not DJANGO_AVAILABLE:
            return custom_methods

        try:
            manager_methods = set(dir(manager))
            base_manager_methods = set(dir(_Manager()))
            base_queryset_methods = set(dir(_QuerySet()))

            custom = manager_methods - base_manager_methods - base_queryset_methods

            for method_name in custom:
                method = getattr(manager, method_name)
                if callable(method) and not method_name.startswith("_"):
                    custom_methods.append(method_name)

        except Exception as e:
            logger.warning("Error discovering custom methods: %s", e)

        return custom_methods

    def _discover_queryset_methods(self, manager: Any) -> Set[str]:
        """Discover available QuerySet methods."""
        queryset_methods = set()

        try:
            if hasattr(manager, "get_queryset"):
                queryset = manager.get_queryset()
                for attr_name in dir(queryset):
                    if not attr_name.startswith("_") and callable(
                        getattr(queryset, attr_name)
                    ):
                        queryset_methods.add(attr_name)

        except Exception as e:
            logger.warning("Error discovering queryset methods: %s", e)

        return queryset_methods

    def _classify_manager(self, manager: Any) -> str:
        """Classify the type of manager."""
        if not DJANGO_AVAILABLE:
            return "Unknown"

        try:
            if hasattr(manager, "get_queryset"):
                return "QuerySetManager"
            elif hasattr(manager, "_queryset_class"):
                return "CustomQuerySetManager"
            elif hasattr(manager, "__class__") and manager.__class__ != _Manager:
                return "CustomManager"
            else:
                return "BaseManager"
        except Exception:
            return "Unknown"

    def _supports_filtering(self, manager: Any) -> bool:
        """Check if the manager supports filtering operations."""
        try:
            return hasattr(manager, "filter") and callable(manager.filter)
        except Exception:
            return False

    def _supports_annotation(self, manager: Any) -> bool:
        """Check if the manager supports annotation operations."""
        try:
            if hasattr(manager, "get_queryset"):
                queryset = manager.get_queryset()
                return hasattr(queryset, "annotate") and callable(queryset.annotate)
            return False
        except Exception:
            return False

    def _supports_related_loading(self, manager: Any) -> bool:
        """Check if the manager supports related field loading."""
        try:
            if hasattr(manager, "get_queryset"):
                queryset = manager.get_queryset()
                return hasattr(queryset, "select_related") and hasattr(
                    queryset, "prefetch_related"
                )
            return False
        except Exception:
            return False
