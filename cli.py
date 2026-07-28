#!/usr/bin/env python3
"""
Auto Maintenance - Entry Point CLI Universal.

Utilisation :
    python cli.py --help
    python cli.py projects list
    python cli.py system status
    python cli.py interactive
"""

import os
import sys
from pathlib import Path

# Ajouter le répertoire racine au PYTHONPATH
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Masquer les logs SQL SQLAlchemy en mode CLI
import logging
for log_name in ("sqlalchemy.engine", "sqlalchemy.engine.Engine", "sqlalchemy.pool", "sqlalchemy.dialects"):
    logger = logging.getLogger(log_name)
    logger.setLevel(logging.ERROR)
    logger.handlers.clear()
    logger.propagate = False



# Encoder stdout/stderr en UTF-8 pour Windows

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from backend.cli.main import app

# Import Sub-commands & Router Modules to register all Typer commands
import backend.cli.commands_projects
import backend.cli.commands_wp
import backend.cli.commands_vrt
import backend.cli.commands_maintenance
import backend.cli.commands_system
import backend.cli.interactive


if __name__ == "__main__":
    app()
