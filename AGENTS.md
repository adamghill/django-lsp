# Django Language Server

## 🎯 Project Overview
This is a Language Server Protocol (LSP) implementation specifically designed for Django `settings.py` files. It provides context-aware completions, hover documentation, and diagnostics by parsing the official Django documentation into a searchable catalog.

## 🏗️ Architecture

### 1. The Catalog (`/catalog`)
The project depends on a `settings.json` metadata file generated from the Django RST documentation.
- `parse_settings.py`: Scrapes/processes Django's `settings.txt`. Use `--download` to refresh.
- `settings.json`: The source of truth for all setting names, defaults, and documentation.
- Hierarchical Structure: The catalog understands nesting (e.g., `NAME` is nested inside `DATABASES.{}.NAME`).

### 2. The LSP Server (`/lsp`)
Built with `pygls` and `lsprotocol`.
- `server.py`: The entry point and main logic.
- `catalog.py`: Loads the JSON catalog and provides query methods (e.g., `get_nested`, `find_similar`).
- **Context Detection**: Uses regex and bracket counting (`get_current_context`) to determine if the cursor is at the top-level or inside a specific nested dict (like `DATABASES` or `TEMPLATES`).

> [!IMPORTANT]
> **pygls v2 API**: This project uses pygls v2 which has different method names than v1:
> | Feature | pygls v2 (current) | pygls v1 (old) |
> |---------|-------------------|----------------|
> | Get configuration | `server.workspace_configuration()` | `server.get_configuration()` |
> | Publish diagnostics | `server.text_document_publish_diagnostics()` | `server.publish_diagnostics()` |
>
> ⚠️ **CRITICAL**: `workspace_configuration()` is async. **Never call `.result()` synchronously** — it blocks the event loop and causes "Loading..." hangs. Always use `callback=`:
> ```python
> server.workspace_configuration(params, callback=lambda cfg: handle(cfg))
> ```

### 3. VS Code Extension (`/vscode`)
A TypeScript wrapper that bundles the Python LSP server.
- The extension packages the Python source and the JSON catalog into a VSIX.

## 🛠️ Key Workflows

### Testing
Always run tests before committing.
- **LSP Tests**: `cd lsp && uv run pytest`
- **Catalog Tests**: `cd catalog && uv run pytest`

### Catalog Updates
If Django releases a new version or settings change:
1. `python catalog/parse_settings.py --download`
2. This updates `catalog/settings.json`.

## 🧠 Architectural Nuances

### Contextual Completions
The server doesn't just look for strings; it calculates "depth".
- **Depth 0**: Top-level settings (e.g., `DEBUG`).
- **Depth 1 (Alias level)**: Inside a dict like `DATABASES`, it suggests aliases like `"default": { ... }`.
- **Depth 2+ (Nested level)**: Inside an alias, it suggests keys like `"ENGINE"`.

### Preventing Quote Duplication
The `get_completion_range` function is critical. It detects if the cursor is already inside quotes (e.g., `""`) and returns a range that includes those quotes. This allows the `TextEdit` to replace the quotes entirely, preventing the common bug where completions result in double-quoted strings like `""NAME""`.

### Typo Detection (Diagnostics)
The server uses `difflib.SequenceMatcher` to find settings similar to unknown keys. If an agent adds a new diagnostic, ensure it is debounced/triggered correctly in `_validate_document`.

## 📏 Standards & Rules
1. **Imports**: Always at the top of the file. No local imports unless strictly necessary to avoid circularity.
2. **Linting**: Use `ruff check . --fix` and `ruff format .`.
3. **No AI "Thinking"**: Remove comments like "New case:", "Step 1:", or any conversational meta-commentary before finishing a task.
4. **Documentation**: Keep the catalog and the hover text in sync. If you change setting metadata, you must rebuild the catalog.

## 🚀 Proactive Actions
- If you change `server.py` logic, pro-actively run `uv run pytest` in the `lsp/` directory.
- If you notice `settings.json` is missing or outdated, pro-actively suggest/run the parser.
