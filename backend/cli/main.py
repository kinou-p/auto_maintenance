"""
Auto Maintenance CLI - Application principale Typer & Context.
"""

import sys
import asyncio
import functools
from typing import Optional, Callable, Any
from pathlib import Path

import typer
from rich.console import Console
from rich.theme import Theme

import logging
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

# Force UTF-8 on Windows
if sys.platform == "win32":

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "highlight": "bold magenta",
    "muted": "dim white",
})

console = Console(theme=custom_theme)

app = typer.Typer(
    name="auto-maintenance",
    help="🛠️ CLI d'administration et de test pour Auto Maintenance (DDEV + WordPress + VRT)",
    add_completion=False,
    rich_markup_mode="rich",
)

# Shared CLI context / options
class CLIContext:
    use_api: bool = False
    api_url: str = "http://localhost:8000"
    json_output: bool = False

cli_ctx = CLIContext()


@app.callback()
def global_options(
    api: bool = typer.Option(
        False,
        "--api",
        "-a",
        help="Utiliser l'API FastAPI au lieu des accès direct aux managers Python.",
    ),
    api_url: str = typer.Option(
        "http://localhost:8000",
        "--api-url",
        help="URL du serveur backend FastAPI (si --api est activé).",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Afficher les résultats au format JSON brut.",
    ),
):
    """
    Options globales pour la CLI Auto Maintenance.
    """
    cli_ctx.use_api = api
    cli_ctx.api_url = api_url.rstrip("/")
    cli_ctx.json_output = json_output


def run_async(async_func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Décorateur pour exécuter des commandes CLI asynchrones de façon synchrone.
    Initialise également la base de données SQLite si nécessaire.
    """
    @functools.wraps(async_func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        async def runner():
            if not cli_ctx.use_api:
                from backend.models.database import engine, Base
                engine.echo = False
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
            return await async_func(*args, **kwargs)



        try:
            return asyncio.run(runner())
        except KeyboardInterrupt:
            console.print("\n[warning]⚠️ Opération annulée par l'utilisateur (Ctrl+C).[/warning]")
            sys.exit(130)
        except Exception as e:
            console.print(f"\n[error]❌ Erreur lors de l'exécution : {e}[/error]")
            console.print_exception(show_locals=False)
            sys.exit(1)

    return wrapper
