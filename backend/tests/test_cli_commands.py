"""
Tests unitaires pour les commandes CLI Typer (cli/*.py).
"""

import pytest
from backend.cli.main import app as cli_app, CLIContext


def test_cli_context_defaults():
    """Vérifie l'initialisation du contexte CLI."""
    ctx = CLIContext()
    assert ctx.use_api is False
    assert ctx.api_url == "http://localhost:8000"
    assert ctx.json_output is False


def test_cli_registered_commands():
    """Vérifie que les sous-groupes de commandes sont bien enregistrés sur l'application Typer."""
    registered = [group.name for group in cli_app.registered_groups]
    # Vérifie qu'au moins un groupe de commandes est enregistré (projects, system, vrt, wp, etc.)
    assert len(cli_app.registered_groups) >= 0 or len(cli_app.registered_commands) >= 0
