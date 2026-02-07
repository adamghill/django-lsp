# django-lsp

Rich, context-aware autocomplete for Django `settings.py` files powered by a **Language Server Protocol (LSP)** server for editor-agnostic support.

## Features

- **Context-aware completions** — offers top-level settings at module scope, and nested sub-keys (like `ENGINE`, `HOST`, `PORT`) when your cursor is inside a `DATABASES` or `CACHES` block.
- **Rich documentation panel** — each completion expands to show a full description, a working code example, and a link to the official Django docs.
- **Typo detection** — diagnostics warn about potential typos (e.g., `DEUBG` → Did you mean `DEBUG`?)
- **Hover documentation** — hover over any setting to see its default value, description, and example.
- **Editor-agnostic** — the Python LSP server can be used with Neovim, Emacs, Sublime, and other LSP-compatible editors.

## Requirements

- NodeJS

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

## Generate Catalog

The catalog is generated from the [Django documentation](https://github.com/django/django/blob/main/docs/ref/settings.txt):

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
| `includeDeprecated` | `false` | Show deprecated settings |

## License

MIT
