from unittest.mock import MagicMock, patch

from django_lsp.server import _analyze_orm, completions
from lsprotocol import types


# Mock ORMOperation since it might need to receive dicts
class MockORMOperation:
    def __init__(self, **kwargs):
        pass


def test_completions_delegates_to_orm_feature():
    """Test that completions delegate to ORM feature for non-settings files."""

    # Setup mocks
    with (
        patch("django_lsp.server.is_settings_file", return_value=False),
        patch("django_lsp.server.ORM_FEATURES_AVAILABLE", True),
        patch("django_lsp.server.orm_completion") as mock_orm_completion,
        patch("django_lsp.server.server") as mock_server,
    ):
        # Mock document
        mock_doc = MagicMock()
        mock_doc.source = "Model.objects.filter("
        mock_server.workspace.get_text_document.return_value = mock_doc

        # Mock expected return
        expected_item = types.CompletionItem(label="test_field")
        mock_orm_completion.get_completions.return_value = [expected_item]

        # Call completions
        params = types.CompletionParams(
            text_document=types.TextDocumentIdentifier(uri="file:///views.py"),
            position=types.Position(line=0, character=20),
        )

        result = completions(params)

        # Verify
        assert result.items == [expected_item]
        mock_orm_completion.get_completions.assert_called_once_with(
            "file:///views.py", 0, 20, "Model.objects.filter("
        )


def test_completions_skips_orm_if_disabled():
    """Test that completions return empty list if ORM features disabled."""

    with (
        patch("django_lsp.server.is_settings_file", return_value=False),
        patch("django_lsp.server.ORM_FEATURES_AVAILABLE", False),
        patch("django_lsp.server.server") as mock_server,
    ):
        # Mock document
        mock_doc = MagicMock()
        mock_server.workspace.get_text_document.return_value = mock_doc

        params = types.CompletionParams(
            text_document=types.TextDocumentIdentifier(uri="file:///views.py"),
            position=types.Position(line=0, character=0),
        )

        result = completions(params)

        assert result.items == []


def test_analyze_orm_updates_cache():
    """Test that _analyze_orm extracts operations and updates cache."""

    with (
        patch("django_lsp.server.ORM_FEATURES_AVAILABLE", True),
        patch("django_lsp.server.parso_parser") as mock_parser,
        patch("django_lsp.server.document_cache") as mock_cache,
        patch("django_lsp.server.ORMOperation", MockORMOperation),
        patch("django_lsp.server.server") as mock_server,
    ):
        # Mock document
        mock_doc = MagicMock()
        mock_doc.source = "content"
        mock_server.workspace.get_text_document.return_value = mock_doc

        # Mock parser output
        mock_parser.extract_orm_operations_with_ranges.return_value = [
            {"model_name": "Test", "operation_name": "filter"}
        ]

        # Call function
        _analyze_orm("file:///views.py")

        # Verify
        mock_parser.extract_orm_operations_with_ranges.assert_called_once_with(
            "content"
        )
        mock_cache.cache_orm_operations.assert_called_once()

        # Verify dict was converted
        call_args = mock_cache.cache_orm_operations.call_args
        assert call_args[0][0] == "file:///views.py"
        assert len(call_args[0][1]) == 1
        assert isinstance(call_args[0][1][0], MockORMOperation)
