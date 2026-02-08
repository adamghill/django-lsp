from unittest.mock import MagicMock

from django_lsp.orm.completion import ORMCompletionFeature
from django_lsp.orm.field_analyzer import FieldAnalysis
from django_lsp.orm.hover import ORMHoverFeature
from django_lsp.orm.model_loader import ModelInfo


def test_completion_has_help_text():
    # Mock model loader and document cache
    model_loader = MagicMock()
    document_cache = MagicMock()

    # Setup field with help_text
    field_analysis = FieldAnalysis(
        type="CharField",
        name="name",
        verbose_name="Name",
        help_text="The model's name",
        null=False,
        blank=False,
        default=None,
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

    # Setup ORM context
    orm_context = MagicMock()
    orm_context.model_name = "MyModel"
    orm_context.manager_name = "objects"
    orm_context.operation_name = "filter"
    document_cache.get_orm_context_at_position.return_value = orm_context

    feature = ORMCompletionFeature(model_loader, document_cache)

    # Trigger completion
    completions = feature.get_completions("test.py", 0, 0, "MyModel.objects.filter()")

    # Verify help_text is in documentation
    name_completion = next(c for c in completions if c.label == "name")
    assert "The model's name" in name_completion.documentation.value
    assert "# name" in name_completion.documentation.value
    assert (
        "[Django Documentation](https://docs.djangoproject.com/en/stable/ref/models/fields/#django.db.models.CharField)"
        in name_completion.documentation.value
    )


def test_isnull_boolean_completions():
    model_loader = MagicMock()
    document_cache = MagicMock()

    field_analysis = FieldAnalysis(
        type="CharField",
        name="name",
        verbose_name="Name",
        help_text="",
        null=False,
        blank=False,
        default=None,
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

    orm_context = MagicMock()
    orm_context.model_name = "MyModel"
    orm_context.manager_name = "objects"
    orm_context.operation_name = "filter"
    document_cache.get_orm_context_at_position.return_value = orm_context

    feature = ORMCompletionFeature(model_loader, document_cache)

    # Trigger completion after name__isnull
    completions = feature.get_completions(
        "test.py", 0, 0, "MyModel.objects.filter(name__isnull)"
    )

    # Manual check for typed_content if needed, but here we assume OperationProvider handles based on document_source
    # Since our internal mock and logic depend on OperationProvider.get_operation_data
    # and ORMCompletionFeature._extract_current_argument

    # Force the current argument extraction to be '__isnull'
    # 'MyModel.objects.filter(name__isnull' is 34 characters long
    source = "MyModel.objects.filter(name__isnull"
    completions = feature.get_completions("test.py", 0, len(source), source)

    # Check for True/False
    true_comp = next((c for c in completions if c.label == "True"), None)
    assert true_comp is not None
    assert true_comp.insert_text == "True"

    false_comp = next((c for c in completions if c.label == "False"), None)
    assert false_comp is not None
    assert false_comp.insert_text == "False"


def test_completion_with_underscore_prefix():
    model_loader = MagicMock()
    document_cache = MagicMock()

    field_analysis = FieldAnalysis(
        type="CharField",
        name="thread_id",
        verbose_name="Thread ID",
        help_text="Gmail thread ID",
        null=False,
        blank=False,
        default=None,
    )
    model_info = ModelInfo(
        app_label="myapp",
        model_name="Thread",
        verbose_name="Thread",
        verbose_name_plural="Threads",
        fields={"thread_id": field_analysis},
        managers={"objects": MagicMock()},
    )

    model_loader.get_model_info.return_value = model_info
    model_loader.load_models.return_value = {"Thread": model_info}

    orm_context = MagicMock()
    orm_context.model_name = "Thread"
    orm_context.manager_name = "objects"
    orm_context.operation_name = "get"
    document_cache.get_orm_context_at_position.return_value = orm_context

    feature = ORMCompletionFeature(model_loader, document_cache)

    # Simulate user typing "thread_"
    source = "Thread.objects.get(thread_)"
    completions = feature.get_completions("test.py", 0, 26, source)

    # Check that thread_id is suggested with documentation
    thread_id_comp = next((c for c in completions if c.label == "thread_id"), None)
    assert thread_id_comp is not None
    assert "Gmail thread ID" in thread_id_comp.documentation.value
    assert "# thread_id" in thread_id_comp.documentation.value
    assert (
        "[Django Documentation](https://docs.djangoproject.com/en/stable/ref/models/fields/#django.db.models.CharField)"
        in thread_id_comp.documentation.value
    )


def test_hover_has_model_docstring():
    model_loader = MagicMock()
    document_cache = MagicMock()

    model_info = ModelInfo(
        app_label="myapp",
        model_name="MyModel",
        verbose_name="My Model",
        verbose_name_plural="My Models",
        fields={},
        managers={},
        docstring="This is MyModel's docstring",
    )

    model_loader.get_model_info.return_value = model_info

    orm_context = MagicMock()
    orm_context.model_name = "MyModel"
    orm_context.field_name = None  # Hovering over the model itself
    orm_context.range_start_line = 0
    orm_context.range_start_character = 0
    orm_context.range_end_line = 0
    orm_context.range_end_character = 7
    document_cache.get_orm_context_at_position.return_value = orm_context

    feature = ORMHoverFeature(model_loader, document_cache)
    hover = feature.get_hover("test.py", 0, 0)

    assert hover is not None
    assert "This is MyModel's docstring" in hover.contents.value
