"""
Feature detection for ORM support.

This module handles detection of optional dependencies (Django)
and provides flags to enable/disable ORM features gracefully.
"""

import logging

logger = logging.getLogger(__name__)

# Check for Django availability
DJANGO_AVAILABLE = False
DJANGO_VERSION = None
try:
    import django

    DJANGO_AVAILABLE = True
    DJANGO_VERSION = django.VERSION
    logger.debug("Django %s detected", django.__version__)
except ImportError:
    logger.debug("Django not available - ORM features disabled")

# parso is a required dependency and should always be available via vendoring
PARSO_AVAILABLE = True

# ORM features require Django
ORM_FEATURES_AVAILABLE = DJANGO_AVAILABLE and PARSO_AVAILABLE

if ORM_FEATURES_AVAILABLE:
    logger.info("ORM features enabled")
else:
    missing = []
    if not DJANGO_AVAILABLE:
        missing.append("django")
    # parso is a required dependency and should be present via vendoring
    logger.info("ORM features disabled (missing: %s)", ", ".join(missing))


def get_feature_status() -> dict:
    """Return a dictionary describing the current feature status."""
    return {
        "django_available": DJANGO_AVAILABLE,
        "django_version": DJANGO_VERSION,
        "parso_available": PARSO_AVAILABLE,
        "orm_features_available": ORM_FEATURES_AVAILABLE,
    }
