"""
Django environment setup and configuration.

This module handles setting up the Django environment for the LSP,
including finding settings modules and configuring Django.

Django is an optional dependency - this module gracefully handles
cases where Django is not installed.
"""

import importlib
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Check for Django availability
DJANGO_AVAILABLE = False
_django = None
try:
    import django

    DJANGO_AVAILABLE = True
    _django = django
except ImportError:
    logger.debug("Django not available")


class DjangoSetup:
    """Handles Django environment setup for multiple workspaces."""

    def __init__(self) -> None:
        self.workspace_setups: Dict[str, bool] = {}
        self.settings_modules: Dict[str, str] = {}
        self.project_roots: Dict[str, Path] = {}
        self._global_setup: bool = False
        logger.debug("DjangoSetup initialized")

    def setup(self, workspace_root: str) -> bool:
        """
        Set up Django environment by finding and loading settings.

        Args:
            workspace_root: Path to the workspace root

        Returns:
            True if successful, False otherwise
        """
        if not DJANGO_AVAILABLE:
            logger.warning("Django not available - ORM features disabled")
            return False

        # Check if this workspace is already set up
        if self.workspace_setups.get(workspace_root, False):
            logger.debug("Django already set up for workspace: %s", workspace_root)
            return True

        logger.info("Setting up Django environment for workspace: %s", workspace_root)
        logger.debug(
            "Current DJANGO_SETTINGS_MODULE: %s",
            os.environ.get("DJANGO_SETTINGS_MODULE", "NOT SET"),
        )

        workspace_path = Path(workspace_root)

        # Find manage.py and project root
        project_root = self._find_project_root(workspace_path)
        if not project_root:
            logger.error(
                "Could not find Django project root in workspace: %s", workspace_root
            )
            return False

        self.project_roots[workspace_root] = project_root
        logger.info("Found project root at: %s", project_root)

        # Add project root to Python path if not already there
        project_root_str = str(project_root)
        if project_root_str not in sys.path:
            sys.path.insert(0, project_root_str)
            logger.debug("Added %s to Python path", project_root)

        # Find or set settings module
        settings_module = self._get_settings_module(project_root)
        if not settings_module:
            logger.error("Failed to determine settings module for: %s", project_root)
            return False

        self.settings_modules[workspace_root] = settings_module

        # Configure and setup Django
        success = self._configure_django(settings_module, workspace_root)
        if success:
            self.workspace_setups[workspace_root] = True
            self._global_setup = True
            logger.info("Django setup successful for: %s", workspace_root)
        else:
            logger.error("Django setup failed for: %s", workspace_root)

        return success

    def is_setup_for_workspace(self, workspace_root: str) -> bool:
        """Check if Django is set up for a specific workspace."""
        return self.workspace_setups.get(workspace_root, False)

    @property
    def is_setup(self) -> bool:
        """Check if Django is set up for any workspace."""
        return self._global_setup

    def get_project_root(self, workspace_root: str) -> Optional[Path]:
        """Get the project root for a specific workspace."""
        return self.project_roots.get(workspace_root)

    def get_settings_module(self, workspace_root: str) -> Optional[str]:
        """Get the settings module for a specific workspace."""
        return self.settings_modules.get(workspace_root)

    def reset_workspace(self, workspace_root: str) -> None:
        """Reset Django setup for a specific workspace."""
        self.workspace_setups.pop(workspace_root, None)
        self.settings_modules.pop(workspace_root, None)
        self.project_roots.pop(workspace_root, None)

        if not self.workspace_setups:
            self._global_setup = False

        logger.info("Reset Django setup for workspace: %s", workspace_root)

    def reset(self) -> None:
        """Reset all Django setup state."""
        self.workspace_setups.clear()
        self.settings_modules.clear()
        self.project_roots.clear()
        self._global_setup = False
        logger.info("Reset all Django setup state")

    def __enter__(self) -> "DjangoSetup":
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[Exception],
        exc_tb: Optional[Any],
    ) -> None:
        """Context manager exit - cleanup resources."""
        self.reset()

    def get_workspace_info(self) -> Dict[str, Any]:
        """Get information about all workspaces."""
        return {
            "workspaces": list(self.workspace_setups.keys()),
            "setup_workspaces": [
                ws for ws, setup in self.workspace_setups.items() if setup
            ],
            "settings_modules": self.settings_modules,
            "project_roots": {ws: str(path) for ws, path in self.project_roots.items()},
            "global_setup": self._global_setup,
            "total_workspaces": len(self.workspace_setups),
            "setup_count": sum(1 for setup in self.workspace_setups.values() if setup),
        }

    def configure_django(self, settings_module: str) -> bool:
        """
        Configure Django with settings module (standalone mode).

        For cases where workspace context is not available.
        """
        return self._configure_django(settings_module, "standalone")

    def _find_project_root(self, workspace_path: Path) -> Optional[Path]:
        """
        Find the Django project root.

        First tries DJANGO_SETTINGS_MODULE's BASE_DIR, then falls back
        to searching for manage.py.
        """
        # Get settings module from environment
        settings_module = os.environ.get("DJANGO_SETTINGS_MODULE")
        if settings_module:
            project_root = self._get_project_root_from_settings_module(settings_module)
            if project_root:
                return project_root

        # Fall back to manage.py discovery
        return self._find_project_root_by_manage_py(workspace_path)

    def _get_project_root_from_settings_module(
        self, settings_module: str
    ) -> Optional[Path]:
        """Get the project root from Django's BASE_DIR."""
        try:
            settings = importlib.import_module(settings_module)

            if hasattr(settings, "BASE_DIR"):
                base_dir: Any = settings.BASE_DIR

                if isinstance(base_dir, str):
                    base_dir_path = Path(base_dir)
                elif isinstance(base_dir, Path):
                    base_dir_path = base_dir
                else:
                    logger.warning(
                        "BASE_DIR is not a string or Path: %s", type(base_dir)
                    )
                    return None

                # Validate that BASE_DIR contains manage.py
                if (base_dir_path / "manage.py").exists():
                    return base_dir_path
                else:
                    logger.warning(
                        "BASE_DIR does not contain manage.py: %s", base_dir_path
                    )
                    return None
            else:
                logger.warning("Settings module has no BASE_DIR: %s", settings_module)
                return None

        except ImportError as e:
            logger.debug("Could not import settings module %s: %s", settings_module, e)
            return None
        except Exception as e:
            logger.debug("Error getting BASE_DIR from %s: %s", settings_module, e)
            return None

    def _find_project_root_by_manage_py(self, workspace_path: Path) -> Optional[Path]:
        """Find Django project root by searching for manage.py."""
        # Look for manage.py in workspace root
        manage_py = workspace_path / "manage.py"
        if manage_py.exists():
            return manage_py.parent

        # Try subdirectories
        for subdir in workspace_path.iterdir():
            if subdir.is_dir():
                potential_manage = subdir / "manage.py"
                if potential_manage.exists():
                    return potential_manage.parent

        logger.error("No manage.py found in workspace: %s", workspace_path)
        return None

    def _get_settings_module(self, project_root: Path) -> Optional[str]:
        """Get Django settings module from environment."""
        settings_module = os.environ.get("DJANGO_SETTINGS_MODULE")
        if settings_module:
            logger.debug("Using DJANGO_SETTINGS_MODULE: %s", settings_module)
            return settings_module

        logger.error(
            "DJANGO_SETTINGS_MODULE not set. "
            "Please set it to your Django project's settings module."
        )
        return None

    def _configure_django(self, settings_module: str, workspace_context: str) -> bool:
        """Configure and setup Django with the given settings module."""
        if not DJANGO_AVAILABLE or _django is None:
            logger.error("Django not available")
            return False

        try:
            os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)
            _django.setup()
            logger.info("Django setup successful with settings: %s", settings_module)
            return True

        except ModuleNotFoundError as e:
            logger.error("Missing dependency for Django setup: %s", e)
            logger.error("Run the LSP from your Django project's virtual environment")
            return False

        except ImportError as e:
            logger.error("Settings module '%s' import error: %s", settings_module, e)
            return False

        except Exception as e:
            logger.error("Failed to setup Django: %s", e)
            return False


# Module-level singleton
_django_setup_instance: Optional[DjangoSetup] = None


def get_django_setup() -> DjangoSetup:
    """Get the shared DjangoSetup instance."""
    global _django_setup_instance
    if _django_setup_instance is None:
        _django_setup_instance = DjangoSetup()
    return _django_setup_instance
