"""
Auto Maintenance CLI - Commandes pour la gestion des mises à jour WordPress.
"""

from typing import Optional
import typer
from rich.table import Table
from rich.panel import Panel

from backend.cli.main import app, console, cli_ctx, run_async

wp_app = typer.Typer(name="wp", help="🧩 Gestion des mises à jour WordPress (Core, Plugins, Thèmes)")
app.add_typer(wp_app)


@wp_app.command("updates")
@run_async
async def list_wp_updates(
    name: str = typer.Argument(..., help="Nom du projet DDEV"),
):
    """
    Vérifier les mises à jour disponibles (WordPress Core, Plugins, Thèmes).
    """
    console.print(f"[info]🔍 Recherche des mises à jour pour '{name}'...[/info]")

    if cli_ctx.use_api:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{cli_ctx.api_url}/api/updates-vrt/projects/{name}/updates")
            resp.raise_for_status()
            data = resp.json()
    else:
        from pathlib import Path
        from sqlalchemy import select
        from backend.models.database import Project, async_session
        from backend.managers.wordpress_manager import WordPressManager

        async with async_session() as session:
            res = await session.execute(select(Project).where(Project.name == name))
            project = res.scalar_one_or_none()
            if not project or not project.ddev_dir:
                console.print(f"[error]❌ Projet '{name}' introuvable.[/error]")
                raise typer.Exit(1)

            data = await WordPressManager.check_updates(Path(project.ddev_dir))

    if cli_ctx.json_output:
        console.print_json(data=data)
        return

    # Render Core updates
    core = data.get("core", {})
    if core.get("update_available"):
        console.print(Panel(
            f"[bold yellow]WordPress Core[/bold yellow] : Version actuelle {core.get('current_version')} ➡️ Nouvelle version {core.get('new_version')}",
            title="✨ Mise à jour Core disponible",
            border_style="yellow"
        ))
    else:
        console.print(f"[success]✅ WordPress Core est à jour ({core.get('current_version', 'ok')}).[/success]")

    # Render Plugins updates table
    plugins = data.get("plugins", [])
    if plugins:
        table_p = Table(title="🧩 Mises à jour de Plugins disponibles", header_style="bold cyan")
        table_p.add_column("Plugin", style="bold")
        table_p.add_column("Version Actuelle", style="muted")
        table_p.add_column("Nouvelle Version", style="green")
        table_p.add_column("Statut", style="yellow")

        for p in plugins:
            table_p.add_row(
                p.get("name") or p.get("plugin") or "Unknown",
                p.get("current_version", "N/A"),
                p.get("new_version", "N/A"),
                p.get("status", "update_available"),
            )
        console.print(table_p)
    else:
        console.print("[success]✅ Tous les plugins sont à jour.[/success]")

    # Render Themes updates table
    themes = data.get("themes", [])
    if themes:
        table_t = Table(title="🎨 Mises à jour de Thèmes disponibles", header_style="bold magenta")
        table_t.add_column("Thème", style="bold")
        table_t.add_column("Version Actuelle", style="muted")
        table_t.add_column("Nouvelle Version", style="green")

        for t in themes:
            table_t.add_row(
                t.get("name") or t.get("theme") or "Unknown",
                t.get("current_version", "N/A"),
                t.get("new_version", "N/A"),
            )
        console.print(table_t)
    else:
        console.print("[success]✅ Tous les thèmes sont à jour.[/success]")


@wp_app.command("update")
@run_async
async def apply_wp_updates(
    name: str = typer.Argument(..., help="Nom du projet DDEV"),
    all_updates: bool = typer.Option(False, "--all", "-a", help="Mettre à jour tout (core, plugins, thèmes)"),
    core: bool = typer.Option(False, "--core", help="Mettre à jour le cœur de WordPress"),
    plugin: Optional[str] = typer.Option(None, "--plugin", "-p", help="Nom d'un plugin spécifique à mettre à jour (ou 'all')"),
    theme: Optional[str] = typer.Option(None, "--theme", "-t", help="Nom d'un thème spécifique à mettre à jour (ou 'all')"),
):
    """
    Appliquer les mises à jour sur un projet WordPress.
    """
    if not (all_updates or core or plugin or theme):
        console.print("[warning]⚠️ Veuillez spécifier au moins une option de mise à jour (--all, --core, --plugin, --theme).[/warning]")
        raise typer.Exit(1)

    console.print(f"[info]⚙️ Application des mises à jour pour '{name}'...[/info]")

    if cli_ctx.use_api:
        import httpx
        async with httpx.AsyncClient() as client:
            payload = {
                "update_core": all_updates or core,
                "plugins": ["all"] if (all_updates or plugin == "all") else ([plugin] if plugin else []),
                "themes": ["all"] if (all_updates or theme == "all") else ([theme] if theme else []),
            }
            resp = await client.post(
                f"{cli_ctx.api_url}/api/updates-vrt/projects/{name}/update",
                json=payload
            )
            resp.raise_for_status()
            res = resp.json()
    else:
        from pathlib import Path
        from sqlalchemy import select
        from backend.models.database import Project, async_session
        from backend.managers.wordpress_manager import WordPressManager

        async with async_session() as session:
            res_db = await session.execute(select(Project).where(Project.name == name))
            project = res_db.scalar_one_or_none()
            if not project or not project.ddev_dir:
                console.print(f"[error]❌ Projet '{name}' introuvable.[/error]")
                raise typer.Exit(1)

            results = []
            ddev_dir = Path(project.ddev_dir)

            if all_updates or core:
                res_c = await WordPressManager.update_core(ddev_dir)
                results.append(f"Core: {res_c.get('message', 'Mis à jour')}")

            if all_updates or plugin:
                p_target = "all" if (all_updates or plugin == "all") else plugin
                res_p = await WordPressManager.update_plugins(ddev_dir, plugins=[p_target] if p_target else [])
                results.append(f"Plugins: {res_p.get('message', 'Mis à jour')}")

            if all_updates or theme:
                t_target = "all" if (all_updates or theme == "all") else theme
                res_t = await WordPressManager.update_themes(ddev_dir, themes=[t_target] if t_target else [])
                results.append(f"Thèmes: {res_t.get('message', 'Mis à jour')}")

            res = {"status": "success", "details": results}

    console.print(f"[success]✅ Mises à jour appliquées avec succès sur '{name}' ![/success]")
    if "details" in res:
        for detail in res["details"]:
            console.print(f"  • {detail}")
