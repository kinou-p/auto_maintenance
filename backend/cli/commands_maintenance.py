"""
Auto Maintenance CLI - Commandes pour l'exécution des workflows de maintenance complète.
"""

from typing import Optional
import typer
from rich.panel import Panel

from backend.cli.main import app, console, cli_ctx, run_async

maint_app = typer.Typer(name="maintenance", help="🚀 Automation et orchestration de la maintenance complète")
app.add_typer(maint_app)


@maint_app.command("run")
@run_async
async def run_maintenance_workflow(
    name: str = typer.Argument(..., help="Nom du projet DDEV"),
    update_all: bool = typer.Option(True, "--all/--select", help="Appliquer toutes les mises à jour automatiquement"),
    import_only: bool = typer.Option(False, "--import-only", "--no-maintenance", "--setup-only", help="Lancer et importer le site sans exécuter la maintenance après"),
):
    """
    Lancer le workflow de maintenance automatisée (ou import seul).
    (Backup -> Captures Avant -> Mises à jour WP -> Captures Après -> Rapport VRT Diff).
    """
    msg = f"🚀 Lancement & Import sans maintenance pour '{name}'..." if import_only else f"🚀 Démarrage de la maintenance automatisée pour '{name}'..."
    console.print(f"[info]{msg}[/info]")

    if cli_ctx.use_api:
        import httpx
        async with httpx.AsyncClient() as client:
            # Récupérer l'ID du projet
            res_p = await client.get(f"{cli_ctx.api_url}/api/projects/{name}")
            res_p.raise_for_status()
            project_id = res_p.json().get("id")

            # Lancer le workflow
            resp = await client.post(
                f"{cli_ctx.api_url}/api/workflows/",
                json={"project_id": project_id, "import_only": import_only, "options": {"all": update_all, "import_only": import_only}}
            )
            resp.raise_for_status()
            res = resp.json()
            wf_id = res.get("id")
            console.print(f"[success]✅ Workflow #{wf_id} lancé via l'API backend.[/success]")
    else:
        from pathlib import Path
        from sqlalchemy import select
        from backend.models.database import Project, Workflow, WorkflowStatus, async_session
        from backend.managers.workflow_orchestrator import WorkflowOrchestrator

        async with async_session() as session:
            res_db = await session.execute(select(Project).where(Project.name == name))
            project = res_db.scalar_one_or_none()
            if not project:
                console.print(f"[error]❌ Projet '{name}' introuvable.[/error]")
                raise typer.Exit(1)

            workflow = Workflow(
                project_id=project.id,
                status=WorkflowStatus.RUNNING,
                options={"all": update_all, "import_only": import_only},
            )

            session.add(workflow)
            await session.commit()
            await session.refresh(workflow)
            wf_id = workflow.id

        from datetime import datetime

        def cli_log_handler(msg: dict):
            t_str = datetime.now().strftime("%H:%M:%S")
            level = msg.get("level", "info")
            step = msg.get("step", "")
            text = msg.get("message", "")

            color = "cyan"
            if level == "success": color = "green"
            elif level == "warning": color = "yellow"
            elif level == "error": color = "bold red"

            step_tag = f"[bold dim][{step}][/bold dim]" if step else ""
            console.print(f"[dim]\\[{t_str}\\][/dim] [{color}]{text}[/{color}] {step_tag}")


        options_dict = {"all": update_all, "import_only": import_only}
        orchestrator = WorkflowOrchestrator(
            project_id=project.id,
            workflow_id=wf_id,
            selected_updates=options_dict,
            options=options_dict,
        )

        orchestrator.logger.on_log = cli_log_handler
        result = await orchestrator.run()



        if cli_ctx.json_output:
            console.print_json(data=result)
            return

        status = result.get("status", "failed")
        is_success = status == "completed"
        badge_style = "bold green" if is_success else "bold red"

        content = (
            f"[bold cyan]ID Workflow :[/bold cyan] #{wf_id}\n"
            f"[bold cyan]Projet :[/bold cyan] {name}\n"
            f"[bold cyan]Résultat :[/bold cyan] [{badge_style}]{status.upper()}[/{badge_style}]\n"
            f"[bold cyan]Erreur éventuelle :[/bold cyan] {result.get('error', 'Aucune')}\n"
        )

        console.print(Panel(content, title=f"📊 Synthèse Maintenance: {name}", border_style="cyan"))
