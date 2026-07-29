"""
Auto Maintenance - Docker Environment Manager.

Gère la création, l'exécution et l'arrêt d'environnements WordPress éphémères
ultra-légers basés sur Docker Compose (Nginx + PHP-FPM + MariaDB).
Remplaçant direct de DDEV : aucun privilège root / sudo nécessaire, ports dynamiques.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
from pathlib import Path
from typing import Optional

from backend.core.config import settings
from backend.core.websocket import WorkflowLogger
from backend.utils.command import run_command



class DockerEnvManager:
    """Gestionnaire d'environnements WordPress Docker éphémères."""

    def __init__(
        self,
        project_name: str,
        logger: Optional[WorkflowLogger] = None,
    ) -> None:
        self.project_name = project_name
        self.logger = logger
        self.project_dir = settings.docker_projects_dir / project_name
        self.port: Optional[int] = None


    async def _log(self, level: str, message: str, step: str = "docker_env") -> None:
        if self.logger:
            await getattr(self.logger, level)(message, step=step)

    def _find_free_port(self) -> int:
        """Trouve un port libre sur l'hôte en partant du port de base."""
        start_port = settings.docker_base_port
        for port in range(start_port, start_port + 500):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", port)) != 0:
                    return port
        raise RuntimeError("Aucun port libre disponible pour le container Docker.")

    def _generate_nginx_config(self) -> str:
        return """
server {
    listen 80;
    server_name localhost;
    root /var/www/html;
    index index.php index.html;

    client_max_body_size 2048M;

    location / {
        try_files $uri $uri/ /index.php?$args;
    }

    location ~ \\.php$ {
        fastcgi_split_path_info ^(.+\\.php)(/.+)$;
        fastcgi_pass wordpress:9000;
        fastcgi_index index.php;
        include fastcgi_params;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        fastcgi_param PATH_INFO $fastcgi_path_info;
    }

    location ~* \\.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
        expires max;
        log_not_found off;
    }
}
"""

    def _generate_docker_compose(self, port: int) -> str:
        return f"""
version: '3.8'

services:
  db:
    image: mariadb:10.11-alpine
    container_name: {self.project_name}_db
    restart: always
    environment:
      MYSQL_ROOT_PASSWORD: root_password
      MYSQL_DATABASE: wordpress
      MYSQL_USER: wp_user
      MYSQL_PASSWORD: wp_password
    volumes:
      - db_data:/var/lib/mysql

  wordpress:
    image: wordpress:6.5-php8.2-fpm-alpine
    container_name: {self.project_name}_wp
    restart: always
    depends_on:
      - db
    environment:
      WORDPRESS_DB_HOST: db:3306
      WORDPRESS_DB_USER: wp_user
      WORDPRESS_DB_PASSWORD: wp_password
      WORDPRESS_DB_NAME: wordpress
    volumes:
      - ./wp-content:/var/www/html/wp-content

  web:
    image: nginx:alpine
    container_name: {self.project_name}_web
    restart: always
    depends_on:
      - wordpress
    ports:
      - "{port}:80"
    volumes:
      - ./wp-content:/var/www/html/wp-content
      - ./nginx.conf:/etc/nginx/conf.d/default.conf

volumes:
  db_data:
"""

    async def start_environment(self) -> dict:
        """
        Initialise et démarre l'environnement Docker éphémère.
        
        Returns:
            Dict avec les informations de connexion (url, port, container_name).
        """
        step = "docker_env"
        await self._log("info", f"Initialisation de l'environnement Docker éphémère pour {self.project_name}...", step=step)

        self.project_dir.mkdir(parents=True, exist_ok=True)
        wp_content_dir = self.project_dir / "wp-content"
        wp_content_dir.mkdir(exist_ok=True)

        self.port = self._find_free_port()
        
        # Fichiers de conf
        (self.project_dir / "nginx.conf").write_text(self._generate_nginx_config(), encoding="utf-8")
        (self.project_dir / "docker-compose.yml").write_text(self._generate_docker_compose(self.port), encoding="utf-8")

        # Lancement de Docker Compose
        res = await run_command(
            ["docker", "compose", "up", "-d"],
            cwd=str(self.project_dir),
        )

        if not res.success:
            await self._log("error", f"Échec du démarrage Docker: {res.stderr}", step=step)
            raise RuntimeError(f"Docker Compose failed: {res.stderr}")

        url = f"http://localhost:{self.port}"
        await self._log("success", f"Environnement Docker opérationnel sur {url}", step=step)
        
        return {
            "project_name": self.project_name,
            "url": url,
            "port": self.port,
            "project_dir": str(self.project_dir),
        }

    async def stop_environment(self) -> None:
        """Arrête et nettoie les containers éphémères."""
        step = "docker_env"
        if self.project_dir.exists() and (self.project_dir / "docker-compose.yml").exists():
            await self._log("info", f"Arrêt des containers Docker pour {self.project_name}...", step=step)
            await run_command(
                ["docker", "compose", "down", "-v"],
                cwd=str(self.project_dir),
            )
            await self._log("success", f"Environnement Docker nettoyé pour {self.project_name}.", step=step)

    async def execute_wp_cli(self, command: list[str]) -> str:
        """Exécute une commande WP-CLI à l'intérieur du container WordPress."""
        step = "wp_cli"
        cmd_args = [
            "docker", "exec", "-i", f"{self.project_name}_wp",
            "wp", "--allow-root"
        ] + command

        res = await run_command(cmd_args, cwd=str(self.project_dir))
        if not res.success:
            raise RuntimeError(f"WP-CLI Error: {res.stderr}")
        return res.stdout.strip()

