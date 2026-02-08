# django-lsp

Rich, context-aware autocomplete for Django powered by a **Language Server Protocol (LSP)** server for editor-agnostic support.

## Features

### Settings

- Supports `settings.py` files or files in a `settings` directory
- Context-aware completions for top-level settings and nested sub-keys (like `ENGINE`, `HOST`, `PORT`) when your cursor is inside a `DATABASES` or `CACHES` block.
- Documentation panel: each completion expands to show a full description, a working code example, and a link to the official Django docs.
- Typo detection: diagnostics warn about potential typos (e.g., `DEUBG` → Did you mean `DEBUG`?)

### Models

- Show available fields to query against when using queryset methods like `.filter()`
- Show available foreign-key relations to traverse
- Show SQL functions like `__isnull`, `__startswith`, etc.

## Vendored Dependencies

The `VS Code` extension bundles Python dependencies in `vscode/vendor`. Versions:

- `pygls` `2.0.1`
- `lsprotocol` `2025.0.0`
- `parso` `0.8.5`
- `attrs` `25.4.0`
- `cattrs` `25.3.0`
- `typing-extensions` `4.15.0`

## Build Extension (.vsix)

To package the extension for distribution:

```bash
cd vscode

# Install vsce if not already installed
npm install -g @vscode/vsce

# Package the extension
npm run package
```

This creates a `.vsix` file that can be installed in VS Code via:
- **Extensions** → **...** → **Install from VSIX...**

## Generate Settings Catalog

Settings information is derived from the [Django RST documentation](https://github.com/django/django/blob/main/docs/ref/settings.txt):

```bash
# Download latest settings.txt documentation and generate JSON catalog
python catalog/parse_settings.py --download

# Or parse existing settings.txt
python catalog/parse_settings.py
```

## Using with Other Editors

The Python LSP server can be used directly:

```bash
# Start the LSP server (communicates via stdio)
cd lsp/src && python -m django_lsp
```

### Neovim (nvim-lspconfig)

```lua
require('lspconfig').configs.django_settings = {
  default_config = {
    cmd = { 'python', '-m', 'django_lsp' },
    filetypes = { 'python' },
    root_dir = function() return vim.fn.getcwd() end,
  },
}
require('lspconfig').django_settings.setup {}
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `djangoVersion` | `"5.0"` | Target Django version for docs links |
| `ignoreUnknownSettings` | `true` | Ignore unknown settings |
| `includeDeprecated` | `false` | Show deprecated settings |

# Acknowledgements

- [django-qs-lsp](https://pypi.org/project/django-qs-lsp/): the original implementation of the Django ORM LSP server (which was forked and ported to `parso` so it's pure Python)

## License

MIT
