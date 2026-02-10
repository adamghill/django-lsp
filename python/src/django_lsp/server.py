"""
server.py - Main LSP server implementation for Django settings.
"""

import logging
import os
import re
from pathlib import Path

from lsprotocol import types
from pygls.lsp.server import LanguageServer
from pygls.workspace import TextDocument

from django_lsp.catalog import DjangoSetting, SettingsCatalog
from django_lsp.orm import (
    ORM_FEATURES_AVAILABLE,
    PARSO_AVAILABLE,
    create_document_cache,
    get_model_loader,
    get_orm_completion_feature,
    get_orm_hover_feature,
    get_parser,
)
from django_lsp.orm.document_cache import ORMOperation
from django_lsp.orm.feature_detection import DJANGO_AVAILABLE

# Set up logging - messages go to stderr which VS Code captures
logging.basicConfig(level=logging.DEBUG, format="[django-lsp] %(message)s")
logger = logging.getLogger(__name__)

# Create the language server
server = LanguageServer("django-lsp", "v0.1.0")

# Load the settings catalog
catalog = SettingsCatalog()

# ORM State
model_loader = None
document_cache = None
orm_completion = None
orm_hover = None
parso_parser = None

# Pattern to match Python assignment: SETTING_NAME = ...
SETTING_PATTERN = re.compile(r"^([A-Z][A-Z0-9_]*)\s*=", re.MULTILINE)

# Global settings state
server_settings = {
    "ignoreUnknownSettings": True,
    "djangoVersion": "stable",
}


# NOTE: pygls v2 uses workspace_configuration(), NOT get_configuration()
def _fetch_configuration(revalidate: bool = False) -> None:
    """Fetch configuration from the client and update server_settings.

    Args:
        revalidate: If True, re-validate all open documents after fetching config.
    """
    logger.debug("_fetch_configuration called (revalidate=%s)", revalidate)

    def _on_config(config):
        """Callback to handle configuration response."""
        logger.debug("_on_config callback received: %r", config)
        try:
            # pygls returns a tuple, not a list
            if config and isinstance(config, (list, tuple)) and len(config) > 0:
                ls_config = config[0]
                server_settings["ignoreUnknownSettings"] = ls_config.get(
                    "ignoreUnknownSettings", True
                )
                server_settings["djangoVersion"] = ls_config.get(
                    "djangoVersion", "stable"
                )
                logger.debug(
                    "Configuration updated: ignoreUnknownSettings=%s, djangoVersion=%s",
                    server_settings["ignoreUnknownSettings"],
                    server_settings["djangoVersion"],
                )
                # Re-validate all open documents if requested
                if revalidate:
                    docs = list(server.workspace.text_documents)
                    logger.debug("Revalidating %d open documents: %s", len(docs), docs)
                    for uri in docs:
                        _validate_document(uri)

                # Also update ORM features if they are initialized
                # Get the shared instances
                from django_lsp.orm import (
                    get_orm_completion_feature,
                    get_orm_hover_feature,
                )

                version = server_settings["djangoVersion"]

                comp = get_orm_completion_feature()
                if comp and hasattr(comp, "doc_generator"):
                    comp.doc_generator.django_version = version

                hvr = get_orm_hover_feature()
                if hvr and hasattr(hvr, "doc_generator"):
                    hvr.doc_generator.django_version = version
        except Exception as e:
            logger.exception("Error in _on_config: %s", e)

    server.workspace_configuration(
        types.ConfigurationParams(
            items=[types.ConfigurationItem(section="django-lsp")]
        ),
        callback=_on_config,
    )
    logger.debug("workspace_configuration request sent")


@server.feature(types.INITIALIZED)
def initialized(params: types.InitializedParams) -> None:
    """Fetch initial configuration when the server is initialized."""
    logger.debug("INITIALIZED event received")
    _fetch_configuration(revalidate=True)
    logger.info(
        "ORM dependencies: django_available=%s, parso_available=%s, "
        "DJANGO_SETTINGS_MODULE=%s",
        DJANGO_AVAILABLE,
        PARSO_AVAILABLE,
        os.environ.get("DJANGO_SETTINGS_MODULE", "NOT SET"),
    )

    # Initialize ORM features
    global model_loader, document_cache, orm_completion, orm_hover, parso_parser
    if ORM_FEATURES_AVAILABLE:
        try:
            logger.info("Initializing ORM features...")
            model_loader = get_model_loader()
            document_cache = create_document_cache(model_loader)
            orm_completion = get_orm_completion_feature(model_loader, document_cache)
            orm_hover = get_orm_hover_feature(model_loader, document_cache)

            # Pass djangoVersion to documentation generator
            django_version = server_settings.get("djangoVersion", "stable")
            if orm_completion and hasattr(orm_completion, "doc_generator"):
                orm_completion.doc_generator.django_version = django_version
            if orm_hover and hasattr(orm_hover, "doc_generator"):
                orm_hover.doc_generator.django_version = django_version

            if PARSO_AVAILABLE:
                parso_parser = get_parser()
                logger.info("ORM features initialized successfully")
            else:
                logger.warning("Parso parser not available - ORM features limited")
        except Exception as e:
            logger.error("Failed to initialize ORM features: %s", e)


@server.feature(types.WORKSPACE_DID_CHANGE_CONFIGURATION)
def did_change_configuration(params: types.DidChangeConfigurationParams) -> None:
    """Update global settings when configuration changes."""
    logger.debug("DID_CHANGE_CONFIGURATION event received: %r", params)
    _fetch_configuration(revalidate=True)


# Pattern to detect if we're inside a dict or list (for nested completions)
# Matches: SETTING = { or "key": { or key: {
DICT_CONTEXT_PATTERN = re.compile(
    r'(?:^|\s*)([A-Z][A-Z0-9_]*|"[^"]+"|\'[^\']+\')\s*[=:]\s*[\{\[]', re.MULTILINE
)


def is_settings_file(uri: str) -> bool:
    """Check if this file looks like a Django settings file."""
    path = Path(uri.replace("file://", ""))
    name = path.name

    # Check filename patterns
    if name == "settings.py":
        return True
    if name in (
        "base.py",
        "local.py",
        "production.py",
        "development.py",
        "dev.py",
        "prod.py",
    ):
        # Check if in a settings directory
        if path.parent.name == "settings":
            return True
    if "settings" in str(path).lower():
        return True

    return False


def get_word_at_position(document: TextDocument, position: types.Position) -> str:
    """Get the word (setting name) at the given position."""
    try:
        line = document.lines[position.line]
    except IndexError:
        return ""

    # Find word boundaries
    start = position.character
    end = position.character

    while start > 0 and (line[start - 1].isalnum() or line[start - 1] == "_"):
        start -= 1

    while end < len(line) and (line[end].isalnum() or line[end] == "_"):
        end += 1

    return line[start:end]


def get_completion_range(
    document: TextDocument, position: types.Position
) -> types.Range:
    """Get the range that should be replaced by the completion."""
    try:
        line = document.lines[position.line]
    except IndexError:
        return types.Range(start=position, end=position)

    start = position.character
    end = position.character

    while start > 0 and (line[start - 1].isalnum() or line[start - 1] == "_"):
        start -= 1

    while end < len(line) and (line[end].isalnum() or line[end] == "_"):
        end += 1

    # Match the entire word if it is already quoted (e.g. "NAME")
    if (
        start > 0
        and end < len(line)
        and line[start - 1] in ("'", '"')
        and line[end] == line[start - 1]
    ):
        start -= 1
        end += 1
    # Check if the cursor is immediately between quotes: ""|
    elif (
        start >= 2
        and line[start - 1] in ("'", '"')
        and line[start - 2] == line[start - 1]
    ):
        start -= 2
    # Check if the cursor is immediately before quotes: |""
    elif (
        end <= len(line) - 2 and line[end] in ("'", '"') and line[end + 1] == line[end]
    ):
        end += 2

    return types.Range(
        start=types.Position(line=position.line, character=start),
        end=types.Position(line=position.line, character=end),
    )


def get_current_context(
    document: TextDocument, position: types.Position
) -> tuple[str | None, int]:
    """Determine if we're inside a specific dict like DATABASES or CACHES."""
    text_before = document.source[: document.offset_at_position(position)]

    # 1. Calculate depth ignoring strings and comments
    bracket_level = 0
    in_string = None
    in_comment = False
    escaped = False

    for char in text_before:
        if in_comment:
            if char == "\n":
                in_comment = False
            continue

        if escaped:
            escaped = False
            continue

        if char == "\\":
            escaped = True
            continue

        if in_string:
            if char == in_string:
                in_string = None
            continue

        if char in ("'", '"'):
            in_string = char
            continue

        if char == "#":
            in_comment = True
            continue

        if char in ("{", "["):
            bracket_level += 1
        elif char in ("}", "]"):
            bracket_level -= 1

    depth = max(0, bracket_level)

    # Find the stack of open named containers
    context_stack = []

    for match in DICT_CONTEXT_PATTERN.finditer(text_before):
        name = match.group(1).strip("'\"")
        bracket = match.group(0).strip()[-1]  # { or [

        # Check if this container is still open at the cursor position
        after_text = text_before[match.end() :]
        is_closed = False
        balance = 0

        for char in after_text:
            if char == bracket:
                balance += 1
            elif (bracket == "{" and char == "}") or (bracket == "[" and char == "]"):
                balance -= 1
                if balance < 0:
                    is_closed = True
                    break

        if not is_closed:
            # Skip common alias levels like "default", "django", "jinja2", "OPTIONS"
            # because they aren't part of the qualified label in the catalog
            if name not in ("default", "django", "jinja2", "OPTIONS"):
                context_stack.append(name)

    if not context_stack:
        return None, depth

    return ".".join(context_stack), depth


def get_existing_keys(document: TextDocument, position: types.Position) -> set[str]:
    """Find keys already present in the current dictionary context."""
    offset = document.offset_at_position(position)
    source = document.source

    # Find the start of the current dictionary
    dict_start = None
    bracket_level = 0
    for i in range(offset - 1, -1, -1):
        char = source[i]
        if char == "}":
            bracket_level += 1
        elif char == "{":
            if bracket_level == 0:
                dict_start = i
                break
            bracket_level -= 1

    if dict_start is None:
        return set()

    # Find the end of the current dictionary
    dict_end = None
    bracket_level = 0
    for i in range(offset, len(source)):
        char = source[i]
        if char == "{":
            bracket_level += 1
        elif char == "}":
            if bracket_level == 0:
                dict_end = i
                break
            bracket_level -= 1

    if dict_end is None:
        dict_end = len(source)

    dict_text = source[dict_start:dict_end]

    # Find all keys in this text
    keys = set()
    # Match keys like "NAME": or 'NAME': or even NAME:
    # Look for [optional quote][uppercase name][same optional quote]:
    for match in re.finditer(r'(["\']?)([A-Z][A-Z0-9_]*)\1\s*:', dict_text):
        key = match.group(2)
        # Global offset of this match
        match_start = dict_start + match.start()
        match_end = dict_start + match.end()

        # If the cursor is inside the key name part of this match, don't filter it
        # This allows completions while re-typing an existing key
        if match_start <= offset <= match_end:
            continue

        keys.add(key)

    return keys


def is_value_context(document: TextDocument, position: types.Position) -> bool:
    """Check if the cursor is in a value context (after a colon)."""
    try:
        line = document.lines[position.line]
    except IndexError:
        return False

    text_before = line[: position.character].strip()

    # If the cursor is inside quotes, strip the opening quote
    if text_before and text_before[-1] in ("'", '"'):
        text_before = text_before[:-1].strip()

    # Check for colon or equals on the SAME line
    if text_before.endswith(":") or text_before.endswith("="):
        return True

    return False


# ─────────────────────────────────────────────────────────────
# COMPLETIONS
# ─────────────────────────────────────────────────────────────


@server.feature(
    types.TEXT_DOCUMENT_COMPLETION,
    types.CompletionOptions(trigger_characters=["=", "'", '"']),
)
def completions(params: types.CompletionParams) -> types.CompletionList:
    """Provide completions for Django settings."""
    uri = params.text_document.uri
    document = server.workspace.get_text_document(uri)

    # 1. ORM Completions (for non-settings files)
    if not is_settings_file(uri):
        if document_cache:
            try:
                document_cache.cache_document_source(uri, document.source)
            except Exception as e:
                logger.debug("Failed to cache document source for %s: %s", uri, e)
        _analyze_orm(uri)
        if ORM_FEATURES_AVAILABLE and orm_completion:
            return types.CompletionList(
                is_incomplete=False,
                items=orm_completion.get_completions(
                    uri,
                    params.position.line,
                    params.position.character,
                    document.source,
                ),
            )
        return types.CompletionList(is_incomplete=False, items=[])

    # 2. Settings Completions
    if is_value_context(document, params.position):
        return types.CompletionList(is_incomplete=False, items=[])

    context, depth = get_current_context(document, params.position)
    completion_range = get_completion_range(document, params.position)

    items = []

    if context:
        # We're inside a dict like DATABASES

        # Check if we need an intermediate alias level (DATABASES, CACHES, TEMPLATES)
        needs_alias = context in ("DATABASES", "CACHES", "TEMPLATES")

        if needs_alias and depth == 1:
            # We are directly inside DATABASES = { ... }
            # Suggest a default alias block
            if context == "DATABASES":
                items.append(
                    _create_alias_snippet(
                        "default",
                        '"ENGINE": "django.db.backends.sqlite3",\n"NAME": "db.sqlite3",',
                        completion_range,
                    )
                )
            elif context == "CACHES":
                items.append(
                    _create_alias_snippet(
                        "default",
                        '"BACKEND": "django.core.cache.backends.locmem.LocMemCache",',
                        completion_range,
                    )
                )
            elif context == "TEMPLATES":
                items.append(
                    _create_alias_snippet(
                        "django",
                        '"BACKEND": "django.template.backends.django.DjangoTemplates",\n"APP_DIRS": True,',
                        completion_range,
                    )
                )

        elif (needs_alias and depth >= 2) or (not needs_alias):
            # We are inside an alias, or it's a simple dict
            existing_keys = get_existing_keys(document, params.position)

            # Check for trailing colon to avoid double colons
            line_text = document.lines[params.position.line]
            suffix = line_text[completion_range.end.character :].lstrip()
            include_colon = not suffix.startswith(":")

            for setting in catalog.get_nested(context):
                if setting.name in existing_keys:
                    continue

                items.append(
                    _create_completion_item(
                        setting,
                        is_nested=True,
                        completion_range=completion_range,
                        include_colon=include_colon,
                    )
                )
    else:
        # Top-level completions
        for setting in catalog.get_all(include_nested=False):
            items.append(
                _create_completion_item(
                    setting, is_nested=False, completion_range=completion_range
                )
            )

    return types.CompletionList(is_incomplete=False, items=items)


def _create_alias_snippet(
    name: str, content: str, completion_range: types.Range = None
) -> types.CompletionItem:
    """Create a snippet for a database/cache alias."""
    insert_text = f'"{name}": {{\n    {content}\n}}$0'

    return types.CompletionItem(
        label=name,
        kind=types.CompletionItemKind.Snippet,
        detail=f"Add '{name}' configuration",
        documentation=types.MarkupContent(
            kind=types.MarkupKind.Markdown,
            value=f"Template for {name} configuration",
        ),
        text_edit=types.TextEdit(range=completion_range, new_text=insert_text)
        if completion_range
        else None,
        insert_text=insert_text if not completion_range else None,
        insert_text_format=types.InsertTextFormat.Snippet,
    )


def _create_completion_item(
    setting: DjangoSetting,
    is_nested: bool,
    label_override: str = None,
    completion_range: types.Range = None,
    include_colon: bool = True,
) -> types.CompletionItem:
    """Create a completion item for a setting."""
    label = label_override or setting.name or setting.label

    if is_nested:
        # For nested settings like 'ENGINE' inside DATABASES
        if include_colon:
            insert_text = f'"{label}": ${{1}}'
        else:
            insert_text = f'"{label}"'
    else:
        # For top-level settings
        insert_text = f"{label} = ${{1}}"

    return types.CompletionItem(
        label=label,
        kind=types.CompletionItemKind.Constant,
        detail=f"Setting: {setting.category}",
        documentation=types.MarkupContent(
            kind=types.MarkupKind.Markdown,
            value=setting.get_markdown_docs(
                server_settings.get("djangoVersion", "stable")
            ),
        ),
        text_edit=types.TextEdit(range=completion_range, new_text=insert_text)
        if completion_range
        else None,
        insert_text=insert_text if not completion_range else None,
        insert_text_format=types.InsertTextFormat.Snippet,
        sort_text=f"0_{label}" if not setting.deprecated else f"1_{label}",
    )


# ─────────────────────────────────────────────────────────────
# HOVER
# ─────────────────────────────────────────────────────────────


@server.feature(types.TEXT_DOCUMENT_HOVER)
def hover(params: types.HoverParams) -> types.Hover | None:
    """Provide hover documentation for Django settings."""
    if not is_settings_file(params.text_document.uri):
        if document_cache:
            try:
                document = server.workspace.get_text_document(params.text_document.uri)
                document_cache.cache_document_source(
                    params.text_document.uri, document.source
                )
            except Exception as e:
                logger.debug(
                    "Failed to cache document source for %s: %s",
                    params.text_document.uri,
                    e,
                )
        _analyze_orm(params.text_document.uri)
        if ORM_FEATURES_AVAILABLE and orm_hover:
            return orm_hover.get_hover(
                params.text_document.uri,
                params.position.line,
                params.position.character,
            )
        return None

    document = server.workspace.get_text_document(params.text_document.uri)
    word = get_word_at_position(document, params.position)

    if not word:
        return None

    context, depth = get_current_context(document, params.position)
    setting = None

    if context and depth >= 2:
        # We are inside a dict, check nested settings
        for child in catalog.get_nested(context):
            if child.name == word or child.label == word:
                setting = child
                break

    if not setting:
        # Fallback to global lookup
        setting = catalog.get(word)

    if not setting:
        return None

    return types.Hover(
        contents=types.MarkupContent(
            kind=types.MarkupKind.Markdown,
            value=setting.get_markdown_docs(
                server_settings.get("djangoVersion", "stable")
            ),
        ),
    )


# ─────────────────────────────────────────────────────────────
# DIAGNOSTICS
# ─────────────────────────────────────────────────────────────


@server.feature(types.TEXT_DOCUMENT_DID_OPEN)
def did_open(params: types.DidOpenTextDocumentParams) -> None:
    """Validate document when opened."""
    _validate_document(params.text_document.uri)


@server.feature(types.TEXT_DOCUMENT_DID_SAVE)
def did_save(params: types.DidSaveTextDocumentParams) -> None:
    """Validate document when saved."""
    _validate_document(params.text_document.uri)


@server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
def did_change(params: types.DidChangeTextDocumentParams) -> None:
    """Validate document when changed (debounced by editor typically)."""
    _validate_document(params.text_document.uri)


def _validate_document(uri: str) -> None:
    """Run diagnostics on the document and publish results."""
    logger.debug("_validate_document called: %s", uri)

    if not is_settings_file(uri):
        if document_cache:
            try:
                document = server.workspace.get_text_document(uri)
                document_cache.cache_document_source(uri, document.source)
            except Exception as e:
                logger.debug("Failed to cache document source for %s: %s", uri, e)
        # If not settings file, try ORM analysis
        _analyze_orm(uri)
        return

    # Skip diagnostics if disabled
    ignore = server_settings.get("ignoreUnknownSettings", True)
    logger.debug("ignoreUnknownSettings = %s", ignore)
    if ignore:
        # Clear existing diagnostics if any
        logger.debug("Clearing diagnostics (diagnostics disabled)")
        server.text_document_publish_diagnostics(
            types.PublishDiagnosticsParams(uri=uri, diagnostics=[])
        )
        return

    document = server.workspace.get_text_document(uri)
    diagnostics = []

    # Find all setting assignments
    for match in SETTING_PATTERN.finditer(document.source):
        setting_name = match.group(1)
        start_pos = match.start(1)
        end_pos = match.end(1)

        # Convert offset to line/character
        line = document.source[:start_pos].count("\n")
        line_start = document.source.rfind("\n", 0, start_pos) + 1
        char_start = start_pos - line_start
        char_end = end_pos - line_start

        # Check if this is a known setting
        known_setting = catalog.get(setting_name)

        if known_setting:
            # Check for deprecated settings
            if known_setting.deprecated:
                diagnostics.append(
                    types.Diagnostic(
                        range=types.Range(
                            start=types.Position(line=line, character=char_start),
                            end=types.Position(line=line, character=char_end),
                        ),
                        message=f"'{setting_name}' is deprecated",
                        severity=types.DiagnosticSeverity.Warning,
                        source="django-lsp",
                        tags=[types.DiagnosticTag.Deprecated],
                    )
                )
        else:
            # Unknown setting
            similar = catalog.find_similar(setting_name)
            message = f"Unknown setting '{setting_name}'"
            if similar:
                suggestions = ", ".join(s.label for s in similar)
                message += f". Did you mean: {suggestions}?"

            diagnostics.append(
                types.Diagnostic(
                    range=types.Range(
                        start=types.Position(line=line, character=char_start),
                        end=types.Position(line=line, character=char_end),
                    ),
                    message=message,
                    severity=types.DiagnosticSeverity.Warning,
                    source="django-lsp",
                )
            )

    # Publish diagnostics
    server.text_document_publish_diagnostics(
        types.PublishDiagnosticsParams(uri=uri, diagnostics=diagnostics)
    )


# ─────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────


def _analyze_orm(uri: str) -> None:
    """Analyze document for ORM operations and update cache."""
    if not ORM_FEATURES_AVAILABLE or not parso_parser or not document_cache:
        return

    try:
        document = server.workspace.get_text_document(uri)
        ops_data = parso_parser.extract_orm_operations_with_ranges(document.source)

        # Convert dicts to ORMOperation objects
        orm_operations = []
        for op in ops_data:
            orm_operations.append(ORMOperation(**op))

        document_cache.cache_orm_operations(uri, orm_operations)
        logger.debug("Cached %d ORM operations for %s", len(orm_operations), uri)

    except Exception as e:
        logger.error("Error analyzing ORM for %s: %s", uri, e)


def main():
    """Start the language server."""
    server.start_io()


if __name__ == "__main__":
    main()
