# Django Language Server

Rich, context-aware autocomplete for Django `settings.py` files with documentation, examples, and typo detection.

## Features

### 🔍 Smart Completions
Intelligent completions for all Django settings with:
- Full documentation and examples
- Links to official Django docs
- Snippet support with placeholders

### 📖 Hover Documentation
Hover over any Django setting to see:
- Default value
- Description
- Code example
- Link to docs

### ⚠️ Diagnostics
- **Typo detection** — warns about unknown settings with suggestions (e.g., `DEUBG` → Did you mean `DEBUG`?)
- **Deprecated settings** — warns when using deprecated Django settings

### 🎯 Context-Aware
- Top-level settings at module scope
- Nested settings inside `DATABASES`, `CACHES`, etc.

## Supported Files

The extension activates for:
- `settings.py`
- Files in `settings/` directories (`base.py`, `local.py`, `production.py`, etc.)
- Any Python file with "settings" in the path

## Requirements

- **Python 3.9+** installed and available in your PATH

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `django-lsp.pythonPath` | Auto-detect | Path to Python interpreter |
| `django-lsp.djangoVersion` | `"5.0"` | Target Django version for docs links |
| `django-lsp.includeDeprecated` | `false` | Show deprecated settings |

## Credits

Settings documentation sourced from the [Django documentation](https://docs.djangoproject.com/).

## License

MIT
