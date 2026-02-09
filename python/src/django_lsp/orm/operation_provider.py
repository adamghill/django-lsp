"""
Operation provider for Django ORM completions.

This module provides field and lookup completions for ORM operations
using pre-analyzed data from the ModelLoader.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

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


@dataclass
class LookupCompletionData:
    """Data structure for lookup completion information."""

    name: str
    lookup_type: str = ""
    field_name: str = ""
    field_type: str = "Unknown"
    documentation: Optional[str] = None


class OperationProvider:
    """Provides field/lookup completions for ORM operations."""

    def __init__(self, model_loader: Any) -> None:
        self.model_loader = model_loader
        from django_lsp.orm.manager_analyzer import ManagerCapabilityAnalyzer

        self.manager_analyzer = ManagerCapabilityAnalyzer()

    def get_operation_data(
        self,
        model_name: str,
        manager_name: str,
        operation_name: str,
        typed_content: str = "",
        available_models: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Get completion data for a specific operation."""
        try:
            model_info = self.model_loader.get_model_info(model_name)
            if not model_info:
                return {"fields": [], "lookups": []}

            manager_info = model_info.managers.get(manager_name)
            if not manager_info:
                return {"fields": [], "lookups": []}

            capabilities = self._analyze_manager_capabilities(manager_info)

            if operation_name not in capabilities.get("operations", set()):
                return {"fields": [], "lookups": []}

            normalized_typed = (typed_content or "").strip()
            if operation_name in {"select_related", "prefetch_related", "annotate"}:
                if not normalized_typed or "(" in normalized_typed:
                    return self.get_model_fields(model_name, "", available_models)

            return self.get_model_fields(model_name, normalized_typed, available_models)

        except Exception as e:
            logger.error("Error getting operation data: %s", e)
            return {"fields": [], "lookups": []}

    def _analyze_manager_capabilities(self, manager_info: Any) -> Dict[str, Any]:
        """Analyze manager capabilities."""
        try:
            if hasattr(manager_info, "instance") and manager_info.instance:
                return self.manager_analyzer.analyze_manager_capabilities(
                    manager_info.instance
                )
            return {"operations": set(), "manager_type": "Unknown"}
        except Exception as e:
            logger.error("Error analyzing manager: %s", e)
            return {"operations": set(), "manager_type": "Unknown"}

    def get_model_fields(
        self,
        model_name: str,
        field_path: str = "",
        available_models: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Get model fields for completion."""
        try:
            base_model = self.model_loader.get_model_info(model_name)
            if not base_model:
                return {"fields": [], "lookups": []}

            # Case 1: Empty input - return all base model fields
            if not field_path:
                return self._get_base_model_fields(base_model, available_models)

            # Case 2b: Value completions for certain lookups
            if field_path.endswith("__isnull"):
                return {
                    "fields": [
                        FieldCompletionData(
                            name="True", field_type="bool", insert_text="True"
                        ),
                        FieldCompletionData(
                            name="False", field_type="bool", insert_text="False"
                        ),
                    ],
                    "lookups": [],
                }

            # Case 3: Related field path ending with "__"
            if field_path.endswith("__") and field_path.count("__") == 1:
                base_field_name = field_path[:-2]
                if base_field_name in base_model.fields:
                    field_analysis = base_model.fields[base_field_name]
                    if field_analysis.related_model:
                        return self._get_related_model_fields(
                            base_model, field_path, available_models
                        )
                    else:
                        return {
                            "fields": [],
                            "lookups": self._get_field_lookups(
                                field_analysis, base_field_name
                            ),
                        }

            # Case 4: Exact field match
            if field_path in base_model.fields:
                field_analysis = base_model.fields[field_path]
                return {
                    "fields": [
                        FieldCompletionData(
                            name=field_path,
                            field_type=field_analysis.type,
                            is_related=field_analysis.related_model is not None,
                            related_model=field_analysis.related_model,
                            documentation=field_analysis.help_text,
                            verbose_name=field_analysis.verbose_name,
                        )
                    ],
                    "lookups": self._get_field_lookups(field_analysis, field_path),
                }

            # Case 5: Nested field path
            if "__" in field_path:
                actual_field_path = field_path.removesuffix("__")
                path_parts = actual_field_path.split("__")

                if len(path_parts) >= 2:
                    current_model = base_model

                    for i, field_name in enumerate(path_parts):
                        if field_name not in current_model.fields:
                            return {"fields": [], "lookups": []}

                        field_analysis = current_model.fields[field_name]

                        if (
                            i == len(path_parts) - 1
                            and not field_analysis.related_model
                        ):
                            return {
                                "fields": [],
                                "lookups": self._get_field_lookups(
                                    field_analysis, field_path
                                ),
                            }

                        if not field_analysis.related_model:
                            return {"fields": [], "lookups": []}

                        if available_models:
                            related_model = available_models.get(
                                field_analysis.related_model
                            )
                            if related_model:
                                current_model = related_model
                            else:
                                return {"fields": [], "lookups": []}
                        else:
                            return {"fields": [], "lookups": []}

                    # Return fields from the final related model
                    fields = []
                    for fname, fanalysis in current_model.fields.items():
                        fields.append(
                            FieldCompletionData(
                                name=f"{field_path.removesuffix('__')}__{fname}",
                                field_type=fanalysis.type,
                                is_related=fanalysis.related_model is not None,
                                related_model=fanalysis.related_model,
                                documentation=fanalysis.help_text,
                                verbose_name=fanalysis.verbose_name,
                            )
                        )
                    return {"fields": fields, "lookups": []}

            return self._get_base_model_fields(base_model, available_models)

        except Exception as e:
            logger.error("Error getting model fields: %s", e)
            return {"fields": [], "lookups": []}

    def _get_field_lookups(
        self, field_analysis: Any, field_path: str = ""
    ) -> List[LookupCompletionData]:
        """Get lookups for a field."""
        lookups = []
        try:
            clean_field_path = field_path.rstrip("_")

            for lookup in field_analysis.lookups:
                full_lookup_name = (
                    f"{clean_field_path}__{lookup.name}"
                    if clean_field_path
                    else lookup.name
                )
                lookups.append(
                    LookupCompletionData(
                        name=full_lookup_name,
                        lookup_type=lookup.name,
                        field_name=getattr(field_analysis, "name", "unknown"),
                        field_type=getattr(field_analysis, "type", "Unknown"),
                        documentation=lookup.doc,
                    )
                )
        except Exception as e:
            logger.error("Error getting lookups: %s", e)

        return lookups

    def _get_base_model_fields(
        self,
        model_info: Any,
        available_models: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Get base model fields and lookups."""
        fields = []
        lookups = []

        for field_name, field_analysis in model_info.fields.items():
            fields.append(
                FieldCompletionData(
                    name=field_name,
                    field_type=field_analysis.type,
                    is_related=field_analysis.related_model is not None,
                    related_model=field_analysis.related_model,
                    documentation=field_analysis.help_text,
                    verbose_name=field_analysis.verbose_name,
                )
            )

            field_lookups = self._get_field_lookups(field_analysis, field_name)
            lookups.extend(field_lookups)

            # Expand foreign key fields
            if field_analysis.related_model and available_models:
                related_model = available_models.get(field_analysis.related_model)
                if related_model:
                    for rfield_name, rfield_analysis in related_model.fields.items():
                        fields.append(
                            FieldCompletionData(
                                name=f"{field_name}__{rfield_name}",
                                field_type=rfield_analysis.type,
                                is_related=rfield_analysis.related_model is not None,
                                related_model=rfield_analysis.related_model,
                                documentation=rfield_analysis.help_text,
                                verbose_name=rfield_analysis.verbose_name,
                            )
                        )

        return {"fields": fields, "lookups": lookups}

    def _get_related_model_fields(
        self,
        base_model: Any,
        field_path: str,
        available_models: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Get fields from a related model."""
        if not field_path.endswith("__"):
            return {"fields": [], "lookups": []}

        path_parts = field_path[:-2].split("__")
        if not path_parts:
            return {"fields": [], "lookups": []}

        current_model = base_model
        for part in path_parts:
            if part not in current_model.fields:
                return {"fields": [], "lookups": []}

            analysis = current_model.fields[part]
            if not analysis.related_model or not available_models:
                return {"fields": [], "lookups": []}

            if analysis.related_model not in available_models:
                return {"fields": [], "lookups": []}

            current_model = available_models[analysis.related_model]

        fields = []
        clean_field_path = field_path.rstrip("_")
        for fname, fanalysis in current_model.fields.items():
            fields.append(
                FieldCompletionData(
                    name=f"{clean_field_path}__{fname}",
                    field_type=fanalysis.type,
                    is_related=fanalysis.related_model is not None,
                    related_model=fanalysis.related_model,
                    documentation=fanalysis.help_text,
                    verbose_name=fanalysis.verbose_name,
                )
            )
        return {"fields": fields, "lookups": []}
