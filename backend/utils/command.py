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


import sys

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


from typing import Optional, Callable, Awaitable

async def run_command(
    command: str | list[str],
    cwd: Optional[str] = None,
    timeout: int = 300,
    env: Optional[dict[str, str]] = None,
    retries: int = 0,
    retry_delay: float = 2.0,
    on_output: Optional[Callable[[str], Awaitable[None] | None]] = None,
) -> CommandResult:
    """
    Exécute une commande shell de manière asynchrone (compatibilité Windows/Linux/macOS).
    """
    if isinstance(command, str):
        args = shlex.split(command, posix=True)
        cmd_str = command
    else:
        args = command
        cmd_str = " ".join(command)

    # Résoudre le chemin absolu de l'exécutable
    executable = shutil.which(args[0])
    if not executable:
        # Fallback si non trouvé
        executable = args[0]
    
    args[0] = executable

    last_result: Optional[CommandResult] = None

    for attempt in range(retries + 1):
        try:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=env,
                )

                stdout_lines = []
                stderr_lines = []

                async def read_stream(stream, lines_list, is_stdout: bool):
                    while True:
                        line = await stream.readline()
                        if not line:
                            break
                        decoded = line.decode("utf-8", errors="replace")
                        lines_list.append(decoded)
                        if is_stdout and on_output:
                            clean_line = decoded.strip()
                            if clean_line:
                                res = on_output(clean_line)
                                if asyncio.iscoroutine(res):
                                    await res

                await asyncio.wait_for(
                    asyncio.gather(
                        read_stream(proc.stdout, stdout_lines, True),
                        read_stream(proc.stderr, stderr_lines, False),
                        proc.wait(),
                    ),
                    timeout=timeout,
                )

                returncode = proc.returncode or 0
                stdout_str = "".join(stdout_lines).strip()
                stderr_str = "".join(stderr_lines).strip()

            except NotImplementedError:
                import subprocess, threading

                loop = asyncio.get_running_loop()

                def run_sync():
                    p = subprocess.Popen(
                        args,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        cwd=cwd,
                        env=env,
                        bufsize=1,
                    )
                    out_lines = []
                    err_lines = []

                    def read_stdout():
                        if p.stdout:
                            for line in iter(p.stdout.readline, ''):
                                out_lines.append(line)
                                clean = line.strip()
                                if clean and on_output:
                                    try:
                                        if asyncio.iscoroutinefunction(on_output):
                                            asyncio.run_coroutine_threadsafe(on_output(clean), loop)
                                        else:
                                            on_output(clean)
                                    except Exception:
                                        pass
                            p.stdout.close()

                    def read_stderr():
                        if p.stderr:
                            for line in iter(p.stderr.readline, ''):
                                err_lines.append(line)
                            p.stderr.close()

                    t_out = threading.Thread(target=read_stdout, daemon=True)
                    t_err = threading.Thread(target=read_stderr, daemon=True)
                    t_out.start()
                    t_err.start()

                    try:
                        p.wait(timeout=timeout)
                    except subprocess.TimeoutExpired:
                        p.kill()
                        return -1, "".join(out_lines), "Command timed out"

                    t_out.join(timeout=5)
                    t_err.join(timeout=5)

                    return p.returncode, "".join(out_lines), "".join(err_lines)

                returncode, stdout_str, stderr_str = await asyncio.to_thread(run_sync)

            result = CommandResult(
                returncode=returncode,
                stdout=stdout_str,
                stderr=stderr_str,
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


def fix_corrupted_ddev_project_list(error_text: str) -> bool:
    """
    Détecte et répare automatiquement la corruption du fichier DDEV global project_list.yaml
    si DDEV renvoie une erreur de type 'control characters are not allowed' ou 'unable to load DDEV global projects file'.
    """
    err_lower = (error_text or "").lower()
    if "project_list.yaml" in err_lower and (
        "control characters" in err_lower
        or "unable to load ddev global" in err_lower
        or "go-yaml load error" in err_lower
    ):
        from pathlib import Path
        paths_to_check = [
            Path.home() / ".ddev" / "project_list.yaml",
            Path("~/.ddev/project_list.yaml").expanduser(),
            Path("/home/pwuser/.ddev/project_list.yaml"),
        ]
        fixed = False
        for p in paths_to_check:
            try:
                if p.exists():
                    p.unlink(missing_ok=True)
                    fixed = True
            except Exception:
                pass
        return fixed
    return False


async def run_ddev_command(
    command: str,
    project_dir: str,
    timeout: int = 120,
    retries: int = 0,
    on_output: Optional[Callable[[str], Awaitable[None] | None]] = None,
) -> CommandResult:
    """
    Exécute une commande DDEV dans le répertoire d'un projet.
    Répare automatiquement le fichier project_list.yaml s'il est corrompu avec des octets nuls.
    """
    # Si project_dir existe, l'utiliser comme cwd
    from pathlib import Path
    p_path = Path(project_dir)
    cwd = str(p_path) if p_path.exists() else None
    
    # Si p_path n'existe pas mais est un nom de projet, injecter -s <project>
    if cwd is None and not command.startswith("ddev list"):
        proj_name = p_path.name
        # Ex: ddev start -> ddev start proj_name
        parts = command.split()
        if len(parts) >= 2:
            parts.insert(2, proj_name)
            command = " ".join(parts)

    res = await run_command(command, cwd=cwd, timeout=timeout, retries=retries, on_output=on_output)

    # Réparation automatique si project_list.yaml est corrompu par des caractères de contrôle nuls
    if not res.success and fix_corrupted_ddev_project_list(res.stderr + " " + res.stdout):
        res = await run_command(command, cwd=cwd, timeout=timeout, retries=retries, on_output=on_output)

    return res


async def run_wp_cli(
    wp_command: str,
    project_dir: str,
    timeout: int = 120,
    on_output: Optional[Callable[[str], Awaitable[None] | None]] = None,
) -> CommandResult:
    """
    Exécute une commande WP-CLI via DDEV avec retransmission en direct des sorties.
    """
    full_command = f"ddev wp {wp_command}"
    return await run_ddev_command(full_command, project_dir=project_dir, timeout=timeout, on_output=on_output)

