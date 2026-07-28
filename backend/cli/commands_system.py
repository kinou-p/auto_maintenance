"""
Auto Maintenance CLI - Commandes système et vérification d'environnement.
"""

import sys
from typing import Optional
import typer
from rich.table import Table
from rich.panel import Panel

from backend.cli.main import app, console, cli_ctx, run_async

sys_app = typer.Typer(name="system", help="🖥️ Diagnostics système, Docker, DDEV et fichier hosts")
app.add_typer(sys_app)


@sys_app.command("status")
@run_async
async def system_status():
    """
    Afficher l'état de l'environnement (Docker, DDEV, Python, Espace disque).
    """
    console.print("[info]🔍 Analyse de l'environnement système...[/info]")

    if cli_ctx.use_api:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{cli_ctx.api_url}/api/system/status")
            resp.raise_for_status()
            data = resp.json()
    else:
        import shutil
        import subprocess
        from backend.core.config import settings, BASE_DIR

        # Check Docker
        docker_ok = False
        try:
            res = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=5)
            docker_ok = res.returncode == 0
        except Exception:
            docker_ok = False

        # Check DDEV
        ddev_version = "N/A"
        try:
            res = subprocess.run(["ddev", "version"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                ddev_version = res.stdout.strip().split("\n")[0]
        except Exception:
            ddev_version = "Non installé"

        # Check Disk
        disk = shutil.disk_usage(BASE_DIR)
        disk_free_gb = disk.free / (1024 ** 3)
        disk_total_gb = disk.total / (1024 ** 3)


        data = {
            "platform": sys.platform,
            "python_version": sys.version.split()[0],
            "docker_running": docker_ok,
            "ddev_version": ddev_version,
            "disk_free_gb": f"{disk_free_gb:.1f} / {disk_total_gb:.1f} GB",
            "ddev_projects_dir": str(settings.ddev_projects_dir),
        }

    if cli_ctx.json_output:
        console.print_json(data=data)
        return

    table = Table(title="🖥️ État du Système Auto Maintenance", header_style="bold cyan")
    table.add_column("Composant", style="bold")
    table.add_column("Valeur / Statut", style="green")

    table.add_row("Système d'exploitation", str(data.get("platform")))
    table.add_row("Version Python", str(data.get("python_version")))
    
    docker_style = "green" if data.get("docker_running") else "red"
    docker_label = "Actif / Operationnel" if data.get("docker_running") else "Inactif / Erreur"
    table.add_row("Docker Daemon", f"[{docker_style}]{docker_label}[/{docker_style}]")
    table.add_row("DDEV CLI", str(data.get("ddev_version")))
    table.add_row("Espace disque disponible", str(data.get("disk_free_gb")))
    table.add_row("Dossier Projets DDEV", str(data.get("ddev_projects_dir")))

    console.print(table)


@sys_app.command("hosts")
@run_async
async def sync_hosts():
    """
    Vérifier et synchroniser les domaines des projets dans le fichier hosts.
    """
    console.print("[info]⚙️ Vérification des entrées du fichier hosts...[/info]")

    if cli_ctx.use_api:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{cli_ctx.api_url}/api/system/hosts/sync")
            resp.raise_for_status()
            res = resp.json()
    else:
        from backend.managers.hosts_manager import HostsManager
        res = await HostsManager.sync_all_projects()

    if cli_ctx.json_output:
        console.print_json(data=res)
        return

    console.print(f"[success]✅ {res.get('message', 'Fichier hosts synchronisé avec succès.')}[/success]")
