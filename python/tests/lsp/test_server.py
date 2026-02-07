from unittest.mock import MagicMock

from django_lsp.server import (
    _fetch_configuration,
    _validate_document,
    completions,
    get_current_context,
    is_value_context,
    server,
    server_settings,
)
from lsprotocol import types


class MockDocument:
    def __init__(self, source):
        self.source = source
        self.lines = source.splitlines(keepends=True)

    def offset_at_position(self, position: types.Position):
        offset = 0
        for i in range(position.line):
            offset += len(self.lines[i])
        offset += position.character
        return offset


def test_get_current_context_toplevel():
    doc = MockDocument("DEBUG = True\n")
    pos = types.Position(line=0, character=5)
    context, depth = get_current_context(doc, pos)
    assert context is None
    assert depth == 0


def test_get_current_context_databases_nested():
    source = """
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "db.sqlite3",
        ""
    }
}
"""
    doc = MockDocument(source)
    # Inside the empty string on line 5 (1-based line 6)
    # DATABASES = { (line 1)
    #     "default": { (line 2)
    #         "ENGINE": ... (line 3)
    #         "NAME": ... (line 4)
    #         "" (line 5)
    pos = types.Position(line=5, character=9)
    context, depth = get_current_context(doc, pos)

    assert context == "DATABASES"
    assert depth == 2


def test_get_current_context_templates_nested():
    source = """
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        ""
    }
]
"""
    doc = MockDocument(source)
    # Inside the empty string on line 4
    pos = types.Position(line=4, character=9)
    context, depth = get_current_context(doc, pos)

    assert context == "TEMPLATES"
    assert depth == 2


def test_get_current_context_deeply_nested_alias_skipped():
    source = """
DATABASES = {
    "default": {
        "OPTIONS": {
            ""
        }
    }
}
"""
    doc = MockDocument(source)
    # Inside OPTIONS on line 4
    pos = types.Position(line=4, character=13)
    context, depth = get_current_context(doc, pos)

    # "OPTIONS" is in the skip list, so context should still be "DATABASES"
    assert context == "DATABASES"
    assert depth == 3


def test_get_current_context_sibling_dicts():
    source = """
DATABASES = {
    "default": {}
}
TEMPLATES = [
    {
        ""
    }
]
"""
    doc = MockDocument(source)
    # Inside TEMPLATES on line 6 (0-indexed)
    pos = types.Position(line=6, character=9)
    context, depth = get_current_context(doc, pos)

    assert context == "TEMPLATES"
    assert depth == 2


def test_get_current_context_databases_templates_siblings():
    source = """
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
    }
}

TEMPLATES = [
    {
        ""
    }
]
"""
    doc = MockDocument(source)
    # Inside TEMPLATES on line 9 (0-indexed)
    pos = types.Position(line=9, character=9)
    context, depth = get_current_context(doc, pos)

    assert context == "TEMPLATES"
    assert depth == 2


def test_completions_not_in_value_context():
    # Context: inside TEMPLATES dictionary, but after a colon (value context)
    source = 'TEMPLATES = [{"NAME": ""}]'
    doc = MockDocument(source)
    # Position inside the second set of quotes for NAME value
    # TEMPLATES = [{"NAME": " (line 0, char 23)
    pos = types.Position(line=0, character=23)

    assert is_value_context(doc, pos) is True

    # And verify it is NOT a value context when we ARE supposed to get completions
    source2 = 'TEMPLATES = [{"": ""}]'
    doc2 = MockDocument(source2)
    # Position inside the first set of quotes for the key
    pos2 = types.Position(line=0, character=15)
    assert is_value_context(doc2, pos2) is False


def test_is_value_context_assignment():
    source = 'DEBUG = "'
    doc = MockDocument(source)
    pos = types.Position(line=0, character=9)
    assert is_value_context(doc, pos) is True


def test_diagnostics_disabled():
    server_settings["ignoreUnknownSettings"] = True
    server.text_document_publish_diagnostics = MagicMock()

    _validate_document("file:///settings.py")

    # Capture the call to publish_diagnostics
    args, _ = server.text_document_publish_diagnostics.call_args
    params = args[0]
    # Should publish empty diagnostics to clear existing ones
    assert len(params.diagnostics) == 0


def test_diagnostics_enabled():
    server_settings["ignoreUnknownSettings"] = False
    # Mock the internal protocol workspace to avoid the property setter error
    server.protocol._workspace = MagicMock()
    server.protocol._workspace.get_text_document = MagicMock(
        return_value=MockDocument("UNKNOWN_SETTING = True")
    )
    server.text_document_publish_diagnostics = MagicMock()

    _validate_document("file:///settings.py")

    args, _ = server.text_document_publish_diagnostics.call_args
    params = args[0]
    # Should find 1 diagnostic for UNKNOWN_SETTING
    assert len(params.diagnostics) == 1
    assert "Unknown setting 'UNKNOWN_SETTING'" in params.diagnostics[0].message


def test_completion_inside_quotes_nested_no_double_quotes():
    """
    Test that when completing inside an empty string like {""},
    the resulting insert_text doesn't cause double quotes.
    """
    source = 'DATABASES = {"default": {""}}'

    # Cursor is at line 0, character 26 (between the last two quotes)
    pos = types.Position(line=0, character=26)
    doc = MockDocument(source)

    # Mock protocol workspace
    server.protocol._workspace = MagicMock()
    server.protocol._workspace.get_text_document = MagicMock(return_value=doc)

    # Mock params
    params = types.CompletionParams(
        text_document=types.TextDocumentIdentifier(uri="file:///settings.py"),
        position=pos,
    )

    # Trigger completions
    result = completions(params)

    # Find "NAME" completion
    name_item = next((item for item in result.items if item.label == "NAME"), None)

    assert name_item is not None

    # Verify that text_edit is used and covers the surrounding quotes
    assert name_item.text_edit is not None
    assert name_item.text_edit.range.start.character == 25
    assert name_item.text_edit.range.end.character == 27
    assert name_item.text_edit.new_text == '"NAME": ${1}'


def test_filter_existing_keys_in_templates():
    source = """
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        ""
    },
]
"""
    # Cursor is at line 5, char 9 (inside the empty string "")
    pos = types.Position(line=5, character=9)
    doc = MockDocument(source)

    # Mock protocol workspace
    server.protocol._workspace = MagicMock()
    server.protocol._workspace.get_text_document = MagicMock(return_value=doc)

    params = types.CompletionParams(
        text_document=types.TextDocumentIdentifier(uri="file:///settings.py"),
        position=pos,
    )

    result = completions(params)

    # Check that BACKEND and APP_DIRS are NOT in the completion items
    labels = [item.label for item in result.items]
    assert "BACKEND" not in labels
    assert "APP_DIRS" not in labels

    # Other items like "OPTIONS" or "NAME" should still be there if they exist in catalog
    assert "OPTIONS" in labels
    assert "NAME" in labels
    assert "DIRS" in labels


def test_no_filter_when_editing_existing_key():
    source = """
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
    },
]
"""
    # Cursor is inside "BACKEND" (line 3, char 12)
    pos = types.Position(line=3, character=12)
    doc = MockDocument(source)

    # Mock protocol workspace
    server.protocol._workspace = MagicMock()
    server.protocol._workspace.get_text_document = MagicMock(return_value=doc)

    params = types.CompletionParams(
        text_document=types.TextDocumentIdentifier(uri="file:///settings.py"),
        position=pos,
    )

    result = completions(params)

    # Check that BACKEND IS in the completion items because we are currently editing it
    labels = [item.label for item in result.items]
    assert "BACKEND" in labels


def test_fetch_configuration_handles_tuple_response():
    """
    Regression test: pygls returns configuration as a tuple, not a list.
    The callback must handle both tuple and list responses.
    """
    # Reset to default state
    server_settings["ignoreUnknownSettings"] = True

    # Mock workspace_configuration to call the callback with a TUPLE (like pygls does)
    def mock_workspace_config(params, callback):
        # pygls returns a tuple, not a list!
        callback(({"ignoreUnknownSettings": False},))

    server.workspace_configuration = mock_workspace_config

    # Call _fetch_configuration
    _fetch_configuration(revalidate=False)

    # Verify the setting was updated from the tuple response
    assert server_settings["ignoreUnknownSettings"] is False


def test_fetch_configuration_handles_list_response():
    """
    Ensure _fetch_configuration also handles list responses for compatibility.
    """
    # Reset to default state
    server_settings["ignoreUnknownSettings"] = True

    # Mock workspace_configuration to call the callback with a LIST
    def mock_workspace_config(params, callback):
        callback([{"ignoreUnknownSettings": False}])

    server.workspace_configuration = mock_workspace_config

    # Call _fetch_configuration
    _fetch_configuration(revalidate=False)

    # Verify the setting was updated from the list response
    assert server_settings["ignoreUnknownSettings"] is False
