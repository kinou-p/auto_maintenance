"""
Auto Maintenance - Utilitaires d'exécution de commandes async.

Wrapper autour de asyncio.create_subprocess_exec avec gestion
des timeouts, retries et logging structuré.
"""

from __future__ import annotations

import asyncio
import shlex
import shutil
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CommandResult:
    """Résultat d'une commande shell."""
    returncode: int
    stdout: str
    stderr: str
    command: str
    success: bool = field(init=False)

    def __post_init__(self) -> None:
        self.success = self.returncode == 0


async def run_command(
    command: str | list[str],
    cwd: Optional[str] = None,
    timeout: int = 300,
    env: Optional[dict[str, str]] = None,
    retries: int = 0,
    retry_delay: float = 2.0,
) -> CommandResult:
    """
    Exécute une commande shell de manière asynchrone.

    Args:
        command: Commande à exécuter (str ou liste d'args).
        cwd: Répertoire de travail.
        timeout: Timeout en secondes.
        env: Variables d'environnement additionnelles.
        retries: Nombre de tentatives supplémentaires en cas d'échec.
        retry_delay: Délai entre les tentatives (secondes).

    Returns:
        CommandResult avec stdout, stderr et code retour.

    Raises:
        asyncio.TimeoutError: Si la commande dépasse le timeout.
    """
    if isinstance(command, str):
        args = shlex.split(command)
        cmd_str = command
    else:
        args = command
        cmd_str = " ".join(command)

    # Résoudre le chemin absolu de l'exécutable
    executable = shutil.which(args[0])
    if not executable:
        # Fallback si non trouvé (pour les commandes builtin ou si déjà absolu)
        executable = args[0]
    
    # Remplacer la commande par son chemin absolu
    args[0] = executable

    last_result: Optional[CommandResult] = None

    for attempt in range(retries + 1):
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )

            result = CommandResult(
                returncode=proc.returncode or 0,
                stdout=stdout_bytes.decode("utf-8", errors="replace").strip(),
                stderr=stderr_bytes.decode("utf-8", errors="replace").strip(),
                command=cmd_str,
            )

            if result.success or attempt >= retries:
                return result

            last_result = result
            await asyncio.sleep(retry_delay * (attempt + 1))

        except asyncio.TimeoutError:
            if attempt >= retries:
                return CommandResult(
                    returncode=-1,
                    stdout="",
                    stderr=f"Commande timeout après {timeout}s: {cmd_str}",
                    command=cmd_str,
                )
            await asyncio.sleep(retry_delay * (attempt + 1))

    # Ne devrait jamais arriver, mais safety net
    return last_result or CommandResult(
        returncode=-1, stdout="", stderr="Erreur inconnue", command=cmd_str
    )


async def run_ddev_command(
    command: str,
    project_dir: str,
    timeout: int = 120,
    retries: int = 0,
) -> CommandResult:
    """
    Exécute une commande DDEV dans le répertoire d'un projet.

    Args:
        command: Commande DDEV (ex: "ddev start").
        project_dir: Répertoire du projet DDEV.
        timeout: Timeout en secondes.
        retries: Nombre de retries.
    """
    return await run_command(command, cwd=project_dir, timeout=timeout, retries=retries)


async def run_wp_cli(
    wp_command: str,
    project_dir: str,
    timeout: int = 120,
) -> CommandResult:
    """
    Exécute une commande WP-CLI via DDEV.

    Args:
        wp_command: Commande WP-CLI (sans le préfixe 'wp').
        project_dir: Répertoire du projet DDEV.
        timeout: Timeout en secondes.
    """
    full_command = f"ddev wp {wp_command}"
    return await run_command(full_command, cwd=project_dir, timeout=timeout)
