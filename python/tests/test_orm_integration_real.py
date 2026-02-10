import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from lsprotocol import types

# Add mock project to sys.path
MOCK_PROJECT_PATH = os.path.join(os.path.dirname(__file__), "mock_project")
sys.path.insert(0, MOCK_PROJECT_PATH)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mock_project.settings")

# Add src to sys.path
SRC_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src")
sys.path.insert(0, SRC_PATH)


def test_orm_completion_with_real_django():
    """
    Test that ORM completion works when Django is actually set up.
    This test will only run if Django is installed in the environment.
    """
    from django_lsp.orm import ORM_FEATURES_AVAILABLE

    if not ORM_FEATURES_AVAILABLE:
        pytest.skip("Django not available")

    import django
    from django_lsp.orm import (
        create_document_cache,
        get_model_loader,
        get_orm_completion_feature,
        get_parser,
    )
    from django_lsp.server import _analyze_orm, completions

    # Initialize Django
    django.setup()

    # Initialize ORM features
    model_loader = get_model_loader()
    document_cache = create_document_cache(model_loader)
    orm_completion = get_orm_completion_feature(model_loader, document_cache)

    # Patch the server state
    with (
        patch("django_lsp.server.ORM_FEATURES_AVAILABLE", True),
        patch("django_lsp.server.model_loader", model_loader),
        patch("django_lsp.server.document_cache", document_cache),
        patch("django_lsp.server.orm_completion", orm_completion),
        patch("django_lsp.server.is_settings_file", return_value=False),
        patch("django_lsp.server.server") as mock_server,
    ):
        # Mock workspace
        uri = "file:///tests/mock_project/myapp/views.py"
        source = "from .models import MyModel\nMyModel.objects.filter("
        mock_doc = MagicMock()
        mock_doc.source = source
        mock_server.workspace.get_text_document.return_value = mock_doc

        # Analyze the document first to populate cache
        parser = get_parser()
        with patch("django_lsp.server.parso_parser", parser):
            _analyze_orm(uri)

            # Request completions at the end of the filter(
            params = types.CompletionParams(
                text_document=types.TextDocumentIdentifier(uri=uri),
                position=types.Position(line=1, character=23),
            )

            result = completions(params)

            # Verify we got completions for MyModel fields
            labels = [item.label for item in result.items]
            assert "name" in labels
            assert "is_active" in labels
            assert "created_at" in labels
            print(f"Integration test passed! Found {len(labels)} completions.")


if __name__ == "__main__":
    test_orm_completion_with_real_django()
