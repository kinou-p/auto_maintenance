"""
Auto Maintenance CLI - Commandes pour le Visual Regression Testing (VRT).
"""

from typing import Optional
import typer
from rich.table import Table
from rich.panel import Panel

from backend.cli.main import app, console, cli_ctx, run_async

vrt_app = typer.Typer(name="vrt", help="📸 Capture d'écran et Visual Regression Testing (VRT)")
app.add_typer(vrt_app)


@vrt_app.command("test")
@run_async
async def run_vrt_test(
    name: str = typer.Argument(..., help="Nom du projet DDEV"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="URL custom à tester (par défaut: http://domain)"),
):
    """
    Exécuter un test VRT (Capture d'écran Desktop & Mobile + Comparaison visuelle avant/après).
    """
    console.print(f"[info]📸 Lancement des captures et tests VRT pour '{name}'...[/info]")

    if cli_ctx.use_api:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{cli_ctx.api_url}/api/updates-vrt/projects/{name}/vrt/compare",
            )
            resp.raise_for_status()
            res = resp.json()
    else:
        from pathlib import Path
        from sqlalchemy import select
        from backend.models.database import Project, async_session
        from backend.managers.screenshot_manager import ScreenshotManager
        from backend.managers.vrt_manager import VRTManager

        async with async_session() as session:
            res_db = await session.execute(select(Project).where(Project.name == name))
            project = res_db.scalar_one_or_none()
            if not project:
                console.print(f"[error]❌ Projet '{name}' introuvable.[/error]")
                raise typer.Exit(1)

            target_url = url or f"http://{project.domain}"
            pages = [{"url": target_url, "name": "home", "type": "page"}]

            sm = ScreenshotManager(name)
            console.print(f"[info]1. Capture d'écran 'Baseline' (Avant)...[/info]")
            await sm.capture_screenshots(pages, phase="before")

            console.print(f"[info]2. Capture d'écran 'Current' (Après)...[/info]")
            await sm.capture_screenshots(pages, phase="after")
            await sm.cleanup()

            console.print(f"[info]3. Comparaison Pixel-Perfect & Génération du rapport...[/info]")
            vrt = VRTManager(name)
            res = await vrt.compare_all()

    if cli_ctx.json_output:
        console.print_json(data=res)
        return

    items = res.get("items", [])
    passed_count = res.get("total_passed", 0)
    failed_count = res.get("total_failed", 0)

    badge_style = "bold green" if failed_count == 0 else "bold red"
    badge_text = "PASSED (Aucune régression visuelle)" if failed_count == 0 else "WARNING/FAILED (Différences détectées)"

    content = (
        f"[bold cyan]Projet :[/bold cyan] {name}\n"
        f"[bold cyan]Captures analysées :[/bold cyan] {len(items)}\n"
        f"[bold cyan]Réussis :[/bold cyan] {passed_count} | [bold red]Échecs/Warnings :[/bold red] {failed_count}\n"
        f"[bold cyan]Statut VRT :[/bold cyan] [{badge_style}]{badge_text}[/{badge_style}]\n"
    )

    console.print(Panel(content, title=f"📊 Résultat du Test VRT: {name}", border_style="cyan"))

    if items:
        table = Table(title="Détail des captures VRT", header_style="bold yellow")
        table.add_column("Page", style="bold")
        table.add_column("Device", style="cyan")
        table.add_column("Score SSIM", style="magenta")
        table.add_column("Diff Pixels (%)", style="yellow")
        table.add_column("Verdict", style="green")

        for item in items:
            p_pass = item.get("passed", True)
            d_style = "green" if p_pass else "red"
            table.add_row(
                item.get("page_name", "home"),
                item.get("device", "desktop"),
                f"{item.get('ssim_score', 1.0):.4f}",
                f"{item.get('diff_percentage', 0.0):.2f}%",
                f"[{d_style}]{item.get('verdict', 'pass').upper()}[/{d_style}]"
            )
        console.print(table)
