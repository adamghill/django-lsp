from unittest.mock import MagicMock

from django_lsp.orm.completion import ORMCompletionFeature
from django_lsp.orm.field_analyzer import FieldAnalysis, FieldLookup
from django_lsp.orm.model_loader import ModelInfo


def test_lookup_completion_has_documentation():
    # Mock model loader and document cache
    model_loader = MagicMock()
    document_cache = MagicMock()

    # Setup field with lookups
    lookups = [
        FieldLookup(name="exact", doc="Exact match lookup documentation."),
        FieldLookup(name="icontains", doc="Case-insensitive containment test."),
    ]
    field_analysis = FieldAnalysis(
        type="CharField",
        name="name",
        verbose_name="Name",
        help_text="The model's name",
        null=False,
        blank=False,
        default=None,
        lookups=lookups,
    )

    model_info = ModelInfo(
        app_label="myapp",
        model_name="MyModel",
        verbose_name="My Model",
        verbose_name_plural="My Models",
        fields={"name": field_analysis},
        managers={"objects": MagicMock()},
    )

    model_loader.get_model_info.return_value = model_info
    model_loader.load_models.return_value = {"MyModel": model_info}

    # Setup ORM context for a lookup completion
    orm_context = MagicMock()
    orm_context.model_name = "MyModel"
    orm_context.manager_name = "objects"
    orm_context.operation_name = "filter"
    document_cache.get_orm_context_at_position.return_value = orm_context

    feature = ORMCompletionFeature(model_loader, document_cache)

    # Trigger completion after name__
    source = "MyModel.objects.filter(name__"
    completions = feature.get_completions("test.py", 0, len(source), source)

    # Verify lookups have documentation
    exact_completion = next((c for c in completions if c.label == "name__exact"), None)
    assert exact_completion is not None
    assert exact_completion.documentation is not None
    assert "## 🔍 name__exact" in exact_completion.documentation.value
    # It should contain the lookup description from the catalog
    assert "Exact match" in exact_completion.documentation.value
    assert "Entry.objects.get(id__exact=14)" in exact_completion.documentation.value

    icontains_completion = next(
        (c for c in completions if c.label == "name__icontains"), None
    )
    assert icontains_completion is not None
    assert icontains_completion.documentation is not None
    assert "## 🔍 name__icontains" in icontains_completion.documentation.value
    assert (
        "Case-insensitive containment test" in icontains_completion.documentation.value
    )
    assert (
        'Entry.objects.get(headline__icontains="Lennon")'
        in icontains_completion.documentation.value
    )
