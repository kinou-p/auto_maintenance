"""
Auto Maintenance - WordPress Manager (Module de rétrocompatibilité).

Ce fichier réexporte WordPressManager depuis le sous-package modulaire
backend.managers.wordpress afin de préserver 100% de la compatibilité des imports existants.
"""

from __future__ import annotations

from backend.managers.wordpress import WordPressManager

__all__ = ["WordPressManager"]
