"""
Auto Maintenance CLI - Commandes pour la gestion des projets DDEV.
"""

import json
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table
from rich.panel import Panel
from rich.json import JSON

from backend.cli.main import app, console, cli_ctx, run_async

projects_app = typer.Typer(name="projects", help="📂 Gestion des projets WordPress DDEV")
app.add_typer(projects_app)


@projects_app.command("list")
@run_async
async def list_projects():
    """
    Lister tous les projets enregistrés et afficher leur statut DDEV.
    """
    if cli_ctx.use_api:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{cli_ctx.api_url}/api/projects")
            resp.raise_for_status()
            data = resp.json()
            projects = data.get("projects", [])
    else:
        from sqlalchemy import select
        from backend.models.database import Project, async_session
        from backend.managers.ddev_manager import DDEVManager

        async with async_session() as session:
            result = await session.execute(select(Project).order_by(Project.id.desc()))
            db_projects = result.scalars().all()
            
            projects = []
            for p in db_projects:
                ddev_status = "unknown"
                if p.ddev_dir and Path(p.ddev_dir).exists():
                    try:
                        info = await DDEVManager.get_status(Path(p.ddev_dir))
                        ddev_status = info.get("status", "stopped")
                    except Exception:
                        ddev_status = "error"
                else:
                    ddev_status = "stopped"

                projects.append({
                    "id": p.id,
                    "name": p.name,
                    "domain": p.domain,
                    "status": p.status.value if hasattr(p.status, "value") else str(p.status),
                    "ddev_status": ddev_status,
                    "created_at": p.created_at.strftime("%Y-%m-%d %H:%M") if p.created_at else "",
                })

    if cli_ctx.json_output:
        console.print_json(data=projects)
        return

    if not projects:
        console.print("[warning]⚠️ Aucun projet trouvé.[/warning]")
        return

    table = Table(title="📋 Liste des Projets Auto Maintenance", header_style="bold magenta")
    table.add_column("ID", style="dim", justify="right")
    table.add_column("Nom", style="bold cyan")
    table.add_column("Domaine", style="blue")
    table.add_column("Statut Projet", style="yellow")
    table.add_column("Statut DDEV", style="green")
    table.add_column("Créé le", style="muted")

    for p in projects:
        ddev_style = "green" if p.get("ddev_status") == "running" else "red"
        table.add_row(
            str(p.get("id")),
            p.get("name"),
            p.get("domain"),
            p.get("status"),
            f"[{ddev_style}]{p.get('ddev_status')}[/{ddev_style}]",
            p.get("created_at"),
        )

    console.print(table)


@projects_app.command("status")
@run_async
async def project_status(
    name: str = typer.Argument(..., help="Nom du projet"),
):
    """
    Afficher les détails et le statut d'un projet spécifique.
    """
    if cli_ctx.use_api:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{cli_ctx.api_url}/api/projects/{name}")
            resp.raise_for_status()
            pdata = resp.json()
    else:
        from sqlalchemy import select
        from backend.models.database import Project, async_session
        from backend.managers.ddev_manager import DDEVManager
        from backend.managers.wordpress_manager import WordPressManager

        async with async_session() as session:
            res = await session.execute(select(Project).where(Project.name == name))
            project = res.scalar_one_or_none()
            if not project:
                console.print(f"[error]❌ Projet '{name}' introuvable.[/error]")
                raise typer.Exit(1)

            pdata = {
                "id": project.id,
                "name": project.name,
                "domain": project.domain,
                "ddev_dir": project.ddev_dir,
                "status": project.status.value if hasattr(project.status, "value") else str(project.status),
                "wpress_file": project.wpress_file,
                "created_at": str(project.created_at),
            }

            if project.ddev_dir and Path(project.ddev_dir).exists():
                ddev_mgr = DDEVManager(project.name, Path(project.ddev_dir))
                ddev_info = await ddev_mgr.get_status()
                pdata["ddev"] = ddev_info
                
                # Check WP details if running
                if ddev_info.get("status") == "running":
                    wp_mgr = WordPressManager(project.name, ddev_mgr)
                    # wp_info = await wp_mgr.get_site_info()
                    # pdata["wordpress"] = wp_info

    if cli_ctx.json_output:
        console.print_json(data=pdata)
        return

    content = (
        f"[bold cyan]ID :[/bold cyan] {pdata.get('id')}\n"
        f"[bold cyan]Nom :[/bold cyan] {pdata.get('name')}\n"
        f"[bold cyan]Domaine :[/bold cyan] https://{pdata.get('domain')}\n"
        f"[bold cyan]Statut :[/bold cyan] {pdata.get('status')}\n"
        f"[bold cyan]Dossier DDEV :[/bold cyan] {pdata.get('ddev_dir')}\n"
    )

    if "ddev" in pdata:
        ddev = pdata["ddev"]
        content += f"\n[bold green]--- DDEV Info ---[/bold green]\n"
        content += f"Statut : {ddev.get('status')}\n"
        content += f"PHP : {ddev.get('php_version')}\n"
        content += f"Webserver : {ddev.get('webserver')}\n"

    if "wordpress" in pdata:
        wp = pdata["wordpress"]
        content += f"\n[bold yellow]--- WordPress Info ---[/bold yellow]\n"
        content += f"Version Core : {wp.get('version', 'inconnue')}\n"
        content += f"Thème actif : {wp.get('active_theme', 'aucun')}\n"

    console.print(Panel(content, title=f"📊 Statut du Projet: {name}", border_style="cyan"))


@projects_app.command("start")
@run_async
async def start_project(
    name: str = typer.Argument(..., help="Nom du projet"),
):
    """
    Démarrer un projet DDEV et vérifier la résolution DNS local.
    """
    console.print(f"[info]▶️ Démarrage du projet '{name}'...[/info]")
    if cli_ctx.use_api:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{cli_ctx.api_url}/api/projects/{name}/start")
            resp.raise_for_status()
            res = resp.json()
    else:
        from sqlalchemy import select
        from backend.models.database import Project, async_session
        from backend.managers.ddev_manager import DDEVManager
        from backend.managers.hosts_manager import HostsManager

        async with async_session() as session:
            res_db = await session.execute(select(Project).where(Project.name == name))
            project = res_db.scalar_one_or_none()
            if not project or not project.ddev_dir:
                console.print(f"[error]❌ Projet '{name}' introuvable ou non configuré.[/error]")
                raise typer.Exit(1)

            success = await DDEVManager.start(Path(project.ddev_dir))
            if not success:
                console.print(f"[error]❌ Échec du démarrage de DDEV pour '{name}'.[/error]")
                raise typer.Exit(1)

            await HostsManager.add_entry(project.domain)
            res = {"status": "success", "message": f"Projet '{name}' démarré avec succès."}

    console.print(f"[success]✅ {res.get('message', 'Projet démarré.')}[/success]")


@projects_app.command("stop")
@run_async
async def stop_project(
    name: str = typer.Argument(..., help="Nom du projet"),
):
    """
    Arrêter les conteneurs DDEV d'un projet.
    """
    console.print(f"[info]⏹️ Arrêt du projet '{name}'...[/info]")
    if cli_ctx.use_api:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{cli_ctx.api_url}/api/projects/{name}/stop")
            resp.raise_for_status()
            res = resp.json()
    else:
        from sqlalchemy import select
        from backend.models.database import Project, async_session
        from backend.managers.ddev_manager import DDEVManager

        async with async_session() as session:
            res_db = await session.execute(select(Project).where(Project.name == name))
            project = res_db.scalar_one_or_none()
            if not project or not project.ddev_dir:
                console.print(f"[error]❌ Projet '{name}' introuvable.[/error]")
                raise typer.Exit(1)

            await DDEVManager.stop(Path(project.ddev_dir))
            res = {"status": "success", "message": f"Projet '{name}' arrêté."}

    console.print(f"[success]✅ {res.get('message', 'Projet arrêté.')}[/success]")


@projects_app.command("create")
@run_async
async def create_project(
    name: str = typer.Argument(..., help="Nom du projet (alphanumérique, tirets, underscores)"),
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Domaine local (ex: site.ddev.site)"),
    import_only: bool = typer.Option(False, "--import-only", "--no-maintenance", "--setup-only", help="Importer et lancer le projet sans exécuter la maintenance après"),
):
    """
    Créer un nouveau projet WordPress DDEV.
    """
    console.print(f"[info]🔨 Création du projet '{name}'...[/info]")
    if cli_ctx.use_api:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{cli_ctx.api_url}/api/projects",
                data={"name": name, "domain": domain or f"{name}.ddev.site"}
            )
            resp.raise_for_status()
            res = resp.json()
            if import_only and "id" in res:
                await client.post(
                    f"{cli_ctx.api_url}/api/workflows/",
                    json={"project_id": res["id"], "import_only": True}
                )
    else:

        from backend.core.config import settings
        from backend.models.database import Project, ProjectStatus, async_session
        from backend.managers.ddev_manager import DDEVManager
        from backend.managers.wordpress_manager import WordPressManager
        from backend.managers.hosts_manager import HostsManager
        from sqlalchemy import select

        target_domain = domain or f"{name}.ddev.site"
        async with async_session() as session:
            existing = await session.execute(select(Project).where(Project.name == name))
            if existing.scalar_one_or_none():
                console.print(f"[error]❌ Un projet nommé '{name}' existe déjà.[/error]")
                raise typer.Exit(1)

            ddev_dir = settings.ddev_projects_dir / name
            ddev_dir.mkdir(parents=True, exist_ok=True)

            project = Project(
                name=name,
                domain=target_domain,
                ddev_dir=str(ddev_dir),
                status=ProjectStatus.INITIALIZING,
            )
            session.add(project)
            await session.commit()
            await session.refresh(project)

            # Init DDEV and WP
            await DDEVManager.create_project(name, target_domain, ddev_dir)
            await HostsManager.add_entry(target_domain)

            project.status = ProjectStatus.READY
            await session.commit()
            res = {"name": name, "domain": target_domain, "status": "ready"}

    console.print(f"[success]🎉 Projet '{name}' créé avec succès ! (https://{res.get('domain')})[/success]")


@projects_app.command("delete")
@run_async
async def delete_project(
    name: str = typer.Argument(..., help="Nom du projet à supprimer"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Confirmer la suppression sans prompt"),
):
    """
    Supprimer un projet et ses conteneurs DDEV.
    """
    if not confirm:
        sure = typer.confirm(f"Êtes-vous sûr de vouloir supprimer le projet '{name}' ?")
        if not sure:
            console.print("[warning]Opération annulée.[/warning]")
            return

    console.print(f"[info]🗑️ Suppression du projet '{name}'...[/info]")
    if cli_ctx.use_api:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.delete(f"{cli_ctx.api_url}/api/projects/{name}")
            resp.raise_for_status()
            res = resp.json()
    else:
        import shutil
        from sqlalchemy import select
        from backend.models.database import Project, async_session
        from backend.managers.ddev_manager import DDEVManager

        async with async_session() as session:
            res_db = await session.execute(select(Project).where(Project.name == name))
            project = res_db.scalar_one_or_none()
            if not project:
                console.print(f"[error]❌ Projet '{name}' introuvable.[/error]")
                raise typer.Exit(1)

            if project.ddev_dir and Path(project.ddev_dir).exists():
                await DDEVManager.delete_project(Path(project.ddev_dir))

            await session.delete(project)
            await session.commit()
            res = {"message": f"Projet '{name}' supprimé."}

    console.print(f"[success]✅ {res.get('message', 'Projet supprimé.')}[/success]")
