#!/usr/bin/env python3
"""
Auto Maintenance - Universal Cross-Platform Launcher.

Démarre simultanément le Backend FastAPI (Uvicorn) et le Frontend React (Vite)
sur n'importe quel système d'exploitation (Windows, Linux, macOS).
"""

import os
import sys
import io
import subprocess
import time
import signal
from pathlib import Path

# Configurer l'encodage UTF-8 pour la sortie standard sous Windows
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent

def check_venv() -> str:
    """Vérifie et retourne le chemin de l'exécutable python dans le venv."""
    venv_dir = BASE_DIR / "venv"
    if sys.platform == "win32":
        python_exe = venv_dir / "Scripts" / "python.exe"
    else:
        python_exe = venv_dir / "bin" / "python"

    if python_exe.exists():
        return str(python_exe)
    
    print("⚠️ Environnement virtuel 'venv' non trouvé. Utilisation du Python du système.")
    return sys.executable

def main():
    python_exe = check_venv()
    
    print("=" * 60)
    print("🚀 Démarrage de Auto Maintenance...")
    print("=" * 60)
    print(f"📌 Système : {sys.platform}")
    print(f"📌 Python  : {python_exe}")
    print("=" * 60)

    processes = []
    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0

    try:
        # 1. Démarrer le Backend FastAPI avec Uvicorn
        print("▶️ Démarrage du Backend FastAPI (http://localhost:8000)...")
        backend_cmd = [
            python_exe,
            "-m", "uvicorn",
            "backend.main:app",
            "--reload",
            "--reload-dir", "backend",
            "--host", "0.0.0.0",
            "--port", "8000"
        ]
        backend_proc = subprocess.Popen(
            backend_cmd,
            cwd=str(BASE_DIR),
            creationflags=creation_flags
        )
        processes.append(("Backend", backend_proc))

        # 2. Démarrer le Frontend React avec Vite
        frontend_dir = BASE_DIR / "frontend"
        if frontend_dir.exists():
            print("▶️ Démarrage du Frontend React (http://localhost:5173)...")
            npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
            frontend_proc = subprocess.Popen(
                [npm_cmd, "run", "dev"],
                cwd=str(frontend_dir),
                creationflags=creation_flags
            )
            processes.append(("Frontend", frontend_proc))
        else:
            print("⚠️ Dossier frontend introuvable, seul le backend est démarré.")

        print("\n✅ Tous les services sont démarrés !")
        print("🌐 Dashboard  : http://localhost:5173")
        print("📚 API Docs   : http://localhost:8000/docs")
        print("\nAppuyez sur Ctrl+C pour tout arrêter.\n")

        # Boucle d'attente
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n🛑 Arrêt des services en cours...")
        for name, proc in processes:
            print(f"Arrêt de {name}...")
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
        print("✅ Tous les services sont arrêtés.")


if __name__ == "__main__":
    main()
