"""
Auto Maintenance - Hosts Manager.

Gestion sécurisée du fichier /etc/hosts pour ajouter/supprimer
les entrées DNS locales des projets DDEV.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.core.config import settings
from backend.core.websocket import WorkflowLogger
from backend.utils.command import run_command

import sys

# Marqueurs pour identifier les entrées gérées par l'application
HOSTS_MARKER_START = "# >>> AUTO_MAINTENANCE MANAGED - DO NOT EDIT >>>"
HOSTS_MARKER_END = "# <<< AUTO_MAINTENANCE MANAGED <<<"

def get_hosts_file() -> Path:
    if sys.platform == "win32":
        return Path(r"C:\Windows\System32\drivers\etc\hosts")
    return Path("/etc/hosts")


class HostsManager:
    """Gère les modifications du fichier hosts de manière sécurisée et cross-platform."""

    def __init__(self, logger: Optional[WorkflowLogger] = None) -> None:
        self.logger = logger
        self.hosts_file = get_hosts_file()

    async def _log(self, level: str, message: str) -> None:
        if self.logger:
            await getattr(self.logger, level)(message, step="dns_setup")

    # ── Lecture / Parse ───────────────────────────────────────────

    def _read_hosts(self) -> str:
        """Lit le contenu du fichier hosts."""
        if not self.hosts_file.exists():
            return ""
        return self.hosts_file.read_text(encoding="utf-8", errors="replace")

    def _get_managed_entries(self, content: str) -> dict[str, str]:
        """
        Extrait les entrées gérées par l'application.

        Returns:
            Dict { domain: ip }.
        """
        entries: dict[str, str] = {}
        in_block = False

        for line in content.splitlines():
            if HOSTS_MARKER_START in line:
                in_block = True
                continue
            if HOSTS_MARKER_END in line:
                in_block = False
                continue
            if in_block and line.strip() and not line.strip().startswith("#"):
                parts = line.split()
                if len(parts) >= 2:
                    entries[parts[1]] = parts[0]

        return entries

    def _build_hosts_content(
        self, original_content: str, entries: dict[str, str]
    ) -> str:
        """
        Reconstruit le contenu de /etc/hosts avec les entrées gérées.

        Args:
            original_content: Contenu original de /etc/hosts.
            entries: Dict { domain: ip } des entrées à écrire.
        """
        # Supprimer l'ancien bloc géré
        lines = original_content.splitlines()
        new_lines: list[str] = []
        in_block = False

        for line in lines:
            if HOSTS_MARKER_START in line:
                in_block = True
                continue
            if HOSTS_MARKER_END in line:
                in_block = False
                continue
            if not in_block:
                new_lines.append(line)

        # Supprimer les lignes vides en fin de fichier
        while new_lines and not new_lines[-1].strip():
            new_lines.pop()

        # Ajouter le nouveau bloc géré (si des entrées existent)
        if entries:
            new_lines.append("")
            new_lines.append(HOSTS_MARKER_START)
            for domain, ip in sorted(entries.items()):
                new_lines.append(f"{ip}\t{domain}")
            new_lines.append(HOSTS_MARKER_END)

        new_lines.append("")  # Ligne vide finale
        return "\n".join(new_lines)

    # ── Opérations ────────────────────────────────────────────────

    async def add_entry(self, domain: str, ip: str = "127.0.0.1") -> bool:
        """
        Ajoute une entrée DNS dans /etc/hosts.

        Args:
            domain: Nom de domaine à ajouter.
            ip: Adresse IP (par défaut 127.0.0.1).

        Returns:
            True si l'opération a réussi.
        """
        await self._log("info", f"Ajout de l'entrée DNS : {ip} → {domain}")

        try:
            content = self._read_hosts()
            entries = self._get_managed_entries(content)

            # Vérifier si l'entrée existe déjà
            if domain in entries and entries[domain] == ip:
                await self._log("info", f"L'entrée DNS existe déjà : {domain}")
                return True

            entries[domain] = ip
            new_content = self._build_hosts_content(content, entries)

            return await self._write_hosts(new_content)

        except Exception as e:
            await self._log("error", f"Erreur lors de la modification de /etc/hosts : {e}")
            return False

    async def remove_entry(self, domain: str) -> bool:
        """
        Supprime une entrée DNS de /etc/hosts.

        Args:
            domain: Nom de domaine à supprimer.

        Returns:
            True si l'opération a réussi.
        """
        await self._log("info", f"Suppression de l'entrée DNS : {domain}")

        try:
            content = self._read_hosts()
            entries = self._get_managed_entries(content)

            if domain not in entries:
                await self._log("info", f"L'entrée DNS n'existe pas : {domain}")
                return True

            del entries[domain]
            new_content = self._build_hosts_content(content, entries)

            return await self._write_hosts(new_content)

        except Exception as e:
            await self._log("error", f"Erreur lors de la suppression DNS : {e}")
            return False

    async def _write_hosts(self, content: str) -> bool:
        """
        Écrit le contenu dans le fichier hosts de manière sécurisée et cross-platform.
        """
        hosts_file = get_hosts_file()

        if sys.platform == "win32":
            try:
                hosts_file.write_text(content, encoding="utf-8")
                await self._log("success", "Fichier hosts Windows mis à jour avec succès.")
                return True
            except PermissionError:
                await self._log(
                    "warning",
                    "Impossible d'écrire dans C:\\Windows\\System32\\drivers\\etc\\hosts (privilèges Administrateur requis). "
                    "Remarque: les domaines *.ddev.site résolvent automatiquement vers 127.0.0.1 via DNS.",
                )
                # Retourner True car la résolution .ddev.site fonctionne tout de même nativement
                return True
            except Exception as e:
                await self._log("error", f"Erreur d'écriture hosts sous Windows : {e}")
                return False

        # Sur Linux / macOS
        backup_path = f"/tmp/hosts.backup.{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        backup_result = await run_command(f"sudo cp {hosts_file} {backup_path}")
        if backup_result.success:
            await self._log("info", f"Backup du fichier hosts : {backup_path}")

        # Écrire dans un fichier temporaire
        with tempfile.NamedTemporaryFile(mode="w", suffix=".hosts", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            method = settings.sudo_method

            if method == "sudoers":
                result = await run_command(
                    f"sudo cp {tmp_path} {hosts_file}", timeout=10
                )
            elif method == "pkexec":
                result = await run_command(
                    f"pkexec cp {tmp_path} {hosts_file}", timeout=30
                )
            else:  # prompt
                result = await run_command(
                    f"sudo cp {tmp_path} {hosts_file}", timeout=30
                )

            if result.success:
                await run_command(f"sudo chmod 644 {hosts_file}")
                await self._log("success", "Fichier hosts mis à jour avec succès.")
                return True
            else:
                await self._log("error", f"Échec de l'écriture du fichier hosts : {result.stderr}")
                await run_command(f"sudo cp {backup_path} {hosts_file}")
                await self._log("info", "Rollback du fichier hosts effectué.")
                return False

        finally:
            Path(tmp_path).unlink(missing_ok=True)

    # ── Sudoers setup ─────────────────────────────────────────────

    @staticmethod
    async def setup_sudoers() -> bool:
        """
        Configure les permissions sudoers pour permettre la modification
        de /etc/hosts sans mot de passe.

        Crée un fichier dans /etc/sudoers.d/ avec les permissions minimales.
        """
        import getpass
        username = getpass.getuser()

        sudoers_content = (
            f"# Auto Maintenance - Permissions pour modification /etc/hosts\n"
            f"# Généré le {datetime.now(timezone.utc).isoformat()}\n"
            f"{username} ALL=(root) NOPASSWD: /usr/bin/cp /tmp/*.hosts /etc/hosts\n"
            f"{username} ALL=(root) NOPASSWD: /usr/bin/cp /etc/hosts /tmp/hosts.backup.*\n"
            f"{username} ALL=(root) NOPASSWD: /usr/bin/chmod 644 /etc/hosts\n"
        )

        # Écrire dans un fichier temporaire
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sudoers", delete=False) as tmp:
            tmp.write(sudoers_content)
            tmp_path = tmp.name

        try:
            # Valider la syntaxe sudoers
            check = await run_command(f"sudo visudo -cf {tmp_path}", timeout=10)
            if not check.success:
                Path(tmp_path).unlink(missing_ok=True)
                return False

            # Installer le fichier sudoers
            result = await run_command(
                f"sudo cp {tmp_path} /etc/sudoers.d/auto-maintenance", timeout=10
            )
            if result.success:
                await run_command("sudo chmod 440 /etc/sudoers.d/auto-maintenance")
                return True

            return False
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    async def list_entries(self) -> dict[str, str]:
        """Liste toutes les entrées DNS gérées par l'application."""
        content = self._read_hosts()
        return self._get_managed_entries(content)
