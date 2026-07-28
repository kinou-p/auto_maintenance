"""
Auto Maintenance CLI - Menu interactif dans le terminal (Mode Assistant/Wizard).
"""

import sys
import typer
from rich.prompt import Prompt, Confirm
from rich.panel import Panel

from backend.cli.main import app, console, run_async


@app.command("interactive")
def interactive_menu():
    """
    🎛️ Lancer le menu interactif guidé pour gérer vos sites et tests.
    """
    console.print(Panel(
        "[bold cyan]Bienvenue dans le menu interactif Auto Maintenance 🛠️[/bold cyan]\n"
        "Gérez vos projets WordPress DDEV et vos tests VRT en toute simplicité.",
        border_style="magenta",
    ))

    while True:
        console.print("\n[bold yellow]Que souhaitez-vous faire ?[/bold yellow]")
        console.print(" 1. 📋 Lister tous les projets DDEV")
        console.print(" 2. 📊 Voir les détails et le statut d'un projet")
        console.print(" 3. ▶️ Démarrer un projet DDEV")
        console.print(" 4. ⏹️ Arrêter un projet DDEV")
        console.print(" 5. 🔍 Vérifier les mises à jour WordPress")
        console.print(" 6. ⚙️ Appliquer des mises à jour (Core, Plugins, Thèmes)")
        console.print(" 7. 📸 Lancer un test VRT (Baseline vs Current)")
        console.print(" 8. 🚀 Exécuter une maintenance complète (End-to-End)")
        console.print(" 9. 🖥️ Vérifier l'état du système & fichier hosts")
        console.print(" 0. ❌ Quitter")

        choice = Prompt.ask("\nChoisissez une option", choices=["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"], default="1")

        if choice == "0":
            console.print("[info]Au revoir ! 👋[/info]")
            break
        elif choice == "1":
            from backend.cli.commands_projects import list_projects
            list_projects()
        elif choice == "2":
            pname = Prompt.ask("Nom du projet")
            if pname:
                from backend.cli.commands_projects import project_status
                project_status(name=pname)
        elif choice == "3":
            pname = Prompt.ask("Nom du projet à démarrer")
            if pname:
                from backend.cli.commands_projects import start_project
                start_project(name=pname)
        elif choice == "4":
            pname = Prompt.ask("Nom du projet à arrêter")
            if pname:
                from backend.cli.commands_projects import stop_project
                stop_project(name=pname)
        elif choice == "5":
            pname = Prompt.ask("Nom du projet")
            if pname:
                from backend.cli.commands_wp import list_wp_updates
                list_wp_updates(name=pname)
        elif choice == "6":
            pname = Prompt.ask("Nom du projet")
            if pname:
                update_all = Confirm.ask("Tout mettre à jour (Core, Plugins, Thèmes) ?")
                from backend.cli.commands_wp import apply_wp_updates
                apply_wp_updates(name=pname, all_updates=update_all, core=not update_all)
        elif choice == "7":
            pname = Prompt.ask("Nom du projet")
            if pname:
                from backend.cli.commands_vrt import run_vrt_test
                run_vrt_test(name=pname)
        elif choice == "8":
            pname = Prompt.ask("Nom du projet")
            if pname:
                mode = Prompt.ask("Mode d'exécution", choices=["1", "2"], default="1", show_choices=False, description="1: Maintenance complète (Mises à jour & VRT) | 2: Lancer & Importer seulement (Sans maintenance)")
                import_only = (mode == "2")
                from backend.cli.commands_maintenance import run_maintenance_workflow
                run_maintenance_workflow(name=pname, update_all=True, import_only=import_only)

        elif choice == "9":
            from backend.cli.commands_system import system_status
            system_status()
