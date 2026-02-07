"""Django Language Server - LSP for Django settings."""

__version__ = "0.1.0"


def main():
    """Entry point for the language server."""
    # Lazy import to avoid loading pygls at import time
    from django_lsp.server import main as server_main

    server_main()
