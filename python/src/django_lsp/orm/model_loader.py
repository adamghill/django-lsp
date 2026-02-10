"""
Model loading and caching.

This module handles loading Django models from the project and caching
them for efficient access by LSP features.

Django is an optional dependency - this module gracefully handles
cases where Django is not installed.
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type

if TYPE_CHECKING:
    from django_lsp.orm.field_analyzer import FieldAnalysis

logger = logging.getLogger(__name__)

# Check for Django availability
DJANGO_AVAILABLE = False
_apps: Any = None
_Model: Any = None

try:
    import django
    from django.apps import apps
    from django.db.models import Model

    DJANGO_AVAILABLE = True
    _apps = apps
    _Model = Model
except ImportError:
    django = None
    logger.debug("Django not available - model loading disabled")

def _ensure_django_ready() -> bool:
    """Ensure Django is set up before accessing app configs."""
    if not DJANGO_AVAILABLE or django is None or _apps is None:
        return False

    if _apps.ready:
        return True

    try:
        django.setup()
        return _apps.ready
    except Exception as e:
        logger.error("Failed to setup Django before loading models: %s", e)
        return False


def _get_field_analyzer():
    """Lazy import for FieldAnalyzer to avoid circular imports."""
    from django_lsp.orm.field_analyzer import FieldAnalyzer

    return FieldAnalyzer


def _get_field_analysis():
    """Lazy import for FieldAnalysis to avoid circular imports."""
    from django_lsp.orm.field_analyzer import FieldAnalysis

    return FieldAnalysis


@dataclass
class ManagerInfo:
    """Information about a Django model manager."""

    name: str
    type: str  # "DefaultManager" or "CustomManager"
    manager_class: str
    manager_module: str
    is_default: bool
    description: str
    instance: Any = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "name": self.name,
            "type": self.type,
            "manager_class": self.manager_class,
            "manager_module": self.manager_module,
            "is_default": self.is_default,
            "description": self.description,
        }


@dataclass
class ModelInfo:
    """Comprehensive information about a Django model."""

    app_label: str
    model_name: str
    verbose_name: str
    verbose_name_plural: Optional[str]
    fields: Dict[str, "FieldAnalysis"] = field(default_factory=dict)
    managers: Dict[str, ManagerInfo] = field(default_factory=dict)
    docstring: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        result = {
            "app_label": self.app_label,
            "model_name": self.model_name,
            "verbose_name": self.verbose_name,
            "fields": {
                name: field_info.to_dict() for name, field_info in self.fields.items()
            },
            "managers": {
                name: manager_info.to_dict()
                for name, manager_info in self.managers.items()
            },
        }
        if self.verbose_name_plural:
            result["verbose_name_plural"] = self.verbose_name_plural
        if self.docstring:
            result["docstring"] = self.docstring
        return result


class ModelLoader:
    """Loads and caches Django models for LSP features."""

    def __init__(self) -> None:
        self.workspace_models_cache: Dict[str, Dict[str, ModelInfo]] = {}
        self.workspace_loaded: Dict[str, bool] = {}
        self.models_cache: Dict[str, ModelInfo] = {}
        self.is_loaded: bool = False
        logger.debug("ModelLoader initialized")

    def load_models(self, workspace_root: Optional[str] = None) -> Dict[str, ModelInfo]:
        """
        Load all Django models from the project.

        Args:
            workspace_root: Optional workspace root

        Returns:
            Dictionary mapping model names to ModelInfo
        """
        if not DJANGO_AVAILABLE:
            logger.warning("Django not available - cannot load models")
            return {}

        if not _ensure_django_ready():
            logger.error("Django apps are not ready - cannot load models")
            return {}

        if self._is_cache_valid(workspace_root):
            logger.debug("Returning cached models for: %s", workspace_root or "global")
            return self._get_cache(workspace_root)

        models_info: Dict[str, ModelInfo] = {}

        try:
            logger.info("Loading Django models for: %s", workspace_root or "global")

            for app_config in _apps.get_app_configs():
                try:
                    app_models_list = list(app_config.get_models())
                except Exception as e:
                    logger.debug("Failed to get models for %s: %s", app_config.label, e)
                    continue

                for model in app_models_list:
                    model_name = model.__name__
                    try:
                        model_info = self._analyze_model(model, app_config.label)
                        models_info[model_name] = model_info
                    except Exception as e:
                        logger.debug("Failed to analyze model %s: %s", model_name, e)
                        continue

            self._update_cache(models_info, workspace_root)
            logger.info("Loaded %d models", len(models_info))

            return models_info

        except Exception as e:
            logger.error("Error loading Django models: %s", e)
            return {}

    def _is_cache_valid(self, workspace_root: Optional[str] = None) -> bool:
        """Check if cache is valid."""
        if workspace_root is None:
            return self.is_loaded and bool(self.models_cache)
        return (
            self.workspace_loaded.get(workspace_root, False)
            and workspace_root in self.workspace_models_cache
        )

    def _get_cache(self, workspace_root: Optional[str] = None) -> Dict[str, ModelInfo]:
        """Get the cache for workspace."""
        if workspace_root is None:
            return self.models_cache
        return self.workspace_models_cache.get(workspace_root, {})

    def _update_cache(
        self, models_info: Dict[str, ModelInfo], workspace_root: Optional[str] = None
    ) -> None:
        """Update cache with new model information."""
        if workspace_root:
            self.workspace_models_cache[workspace_root] = models_info
            self.workspace_loaded[workspace_root] = True
        else:
            self.models_cache = models_info
            self.is_loaded = True

    def _analyze_model(self, model: Type[Any], app_label: str) -> ModelInfo:
        """Analyze a Django model."""
        opts = model._meta
        model_info = ModelInfo(
            app_label=app_label,
            model_name=model.__name__,
            verbose_name=getattr(opts, "verbose_name", model.__name__),
            verbose_name_plural=str(getattr(opts, "verbose_name_plural", "")),
            docstring=str(getattr(model, "__doc__", "")) if model.__doc__ else None,
        )

        # Analyze managers
        self._analyze_managers(model, model_info)

        # Get all forward fields
        for django_field in model._meta.get_fields():
            field_name = django_field.name
            try:
                from django.db.models import Field as DjangoField

                if isinstance(django_field, DjangoField):
                    FieldAnalyzer = _get_field_analyzer()
                    field_analysis = FieldAnalyzer.analyze_field(django_field)
                    model_info.fields[field_name] = field_analysis
            except Exception as e:
                logger.debug("Error analyzing field %s: %s", field_name, e)
                FieldAnalysisCls = _get_field_analysis()
                model_info.fields[field_name] = FieldAnalysisCls(
                    type=django_field.__class__.__name__,
                    name=field_name,
                    verbose_name=field_name,
                    help_text="",
                    null=False,
                    blank=False,
                    default=None,
                    lookups=[],
                )

        # Add reverse relations
        self._add_reverse_relations(model, model_info)

        return model_info

    def _add_reverse_relations(self, model: Type[Any], model_info: ModelInfo) -> None:
        """Add reverse relations to model info."""
        for related_object in model._meta.related_objects:
            if hasattr(related_object, "get_accessor_name"):
                accessor_name = related_object.get_accessor_name()
                if accessor_name:
                    FieldAnalysisCls = _get_field_analysis()
                    field_analysis = FieldAnalysisCls(
                        type="RelatedManager",
                        name=accessor_name,
                        verbose_name=accessor_name,
                        help_text="",
                        null=False,
                        blank=False,
                        default=None,
                        lookups=[],
                        related_model=related_object.related_model.__name__,
                        related_app=related_object.related_model._meta.app_label,
                    )
                    model_info.fields[accessor_name] = field_analysis

    def _analyze_managers(self, model: Type[Any], model_info: ModelInfo) -> None:
        """Analyze managers on a model."""
        default_manager_name = getattr(model._meta, "default_manager_name", "objects")

        if default_manager_name is None and model._meta.managers_map:
            default_manager_name = next(iter(model._meta.managers_map.keys()))

        for manager_name, manager_instance in model._meta.managers_map.items():
            is_default = manager_name == default_manager_name
            manager_type = "DefaultManager" if is_default else "CustomManager"

            manager_info = ManagerInfo(
                name=manager_name,
                type=manager_type,
                manager_class=manager_instance.__class__.__name__,
                manager_module=manager_instance.__class__.__module__,
                is_default=is_default,
                description=f"{'Default' if is_default else 'Custom'} manager for {model.__name__}",
                instance=manager_instance,
            )
            model_info.managers[manager_name] = manager_info

    def get_model_info(
        self, model_name: str, workspace_root: Optional[str] = None
    ) -> Optional[ModelInfo]:
        """Get model info from cache."""
        cache = self._ensure_cache_loaded(workspace_root)
        return cache.get(model_name)

    def _ensure_cache_loaded(
        self, workspace_root: Optional[str] = None
    ) -> Dict[str, ModelInfo]:
        """Ensure cache is loaded."""
        if not self._is_cache_valid(workspace_root):
            self.load_models(workspace_root)
        return self._get_cache(workspace_root)

    def get_all_models(self, workspace_root: Optional[str] = None) -> List[str]:
        """Get list of all model names."""
        cache = self._ensure_cache_loaded(workspace_root)
        return list(cache.keys())

    def clear_cache(self, workspace_root: Optional[str] = None) -> None:
        """Clear the model cache."""
        if workspace_root:
            self.workspace_models_cache.pop(workspace_root, None)
            self.workspace_loaded.pop(workspace_root, None)
        else:
            self.models_cache.clear()
            self.is_loaded = False
        logger.debug("Model cache cleared")

    def reload_models(
        self, workspace_root: Optional[str] = None
    ) -> Dict[str, ModelInfo]:
        """Force reload models."""
        self.clear_cache(workspace_root)
        return self.load_models(workspace_root)

    def get_model_by_name(
        self, model_name: str, workspace_root: Optional[str] = None
    ) -> Optional[Any]:
        """Get actual Django model class by name."""
        model_info = self.get_model_info(model_name, workspace_root)
        if model_info and DJANGO_AVAILABLE:
            try:
                return _apps.get_model(model_info.app_label, model_info.model_name)
            except Exception as e:
                logger.debug("Could not get model class for %s: %s", model_name, e)
        return None


# Module-level singleton
_model_loader_instance: Optional[ModelLoader] = None


def get_model_loader() -> ModelLoader:
    """Get the shared ModelLoader instance."""
    global _model_loader_instance
    if _model_loader_instance is None:
        _model_loader_instance = ModelLoader()
    return _model_loader_instance
