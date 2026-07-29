"""
Auto Maintenance - Configuration centralisée.

Utilise pydantic-settings pour valider et charger la configuration
depuis les variables d'environnement et le fichier .env.
"""

from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Répertoire racine du projet
BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _default_ddev_projects_dir() -> Path:
    """Chemin portable des projets DDEV (data local du projet)."""
    return BASE_DIR / "data" / "ddev-projects"


class Settings(BaseSettings):
    """Configuration globale de l'application."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "auto_maintenance"
    app_env: Literal["development", "production", "testing"] = "development"
    app_debug: bool = True
    sql_echo: bool = False
    app_port: int = 8000
    app_host: str = "0.0.0.0"

    # --- Frontend ---
    frontend_url: str = "http://localhost:5173"
    frontend_port: int = 5173
    cors_origins: list[str] | str = ["http://localhost:5173", "http://localhost:3000"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v) -> list[str]:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # --- Security & Auth ---
    jwt_secret_key: str = "auto_maintenance_super_secret_jwt_key_2026_change_me!"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24  # 24 heures

    @field_validator("jwt_secret_key", mode="before")
    @classmethod
    def _validate_jwt_secret(cls, v, info) -> str:
        insecure_default = "auto_maintenance_super_secret_jwt_key_2026_change_me!"
        if not v or not str(v).strip():
            v = insecure_default
        app_env = info.data.get("app_env", "development")
        if app_env == "production" and (v == insecure_default or len(v) < 32):
            # En production sans secret fort défini, lever une exception explicite
            raise ValueError(
                "En environnement de production (APP_ENV=production), JWT_SECRET_KEY doit être définie avec une valeur sécurisée (au moins 32 caractères)."
            )
        return str(v)

    # --- Database ---
    database_url: str = Field(
        default=f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'auto_maintenance.db'}"
    )

    # --- Docker Environments ---
    docker_projects_dir: Path = Field(default_factory=lambda: BASE_DIR / "data" / "docker-projects")
    docker_base_port: int = 8080
    vrt_enable_dom_snapshot: bool = True
    vrt_dom_similarity_threshold: float = 0.95

    # --- DDEV (compatibilité / legacy) ---
    ddev_projects_dir: Path = Field(default_factory=_default_ddev_projects_dir)
    # Chemin hôte pour Docker-in-Docker (identique hôte/container si monté)
    host_ddev_projects: Optional[Path] = None
    ddev_php_version: str = "8.2"
    ddev_webserver_type: str = "nginx-fpm"
    ddev_mariadb_version: str = "10.6"


    # --- Workflows & Concurrence ---
    max_concurrent_workflows: int = 2
    updates_cache_ttl_minutes: int = 15

    # --- Uploads ---
    max_upload_size_mb: int = 2048  # 2 Go max par fichier .wpress

    # --- WordPress ---
    wp_admin_user: str = "admin_temp"
    wp_admin_password: str = "temp_password_change_me"
    wp_admin_email: str = "admin@localhost.local"
    wp_locale: str = "fr_FR"
    wp_cache_max_age_days: int = 7

    # --- Assets ---
    aio_plugin_zip_path: Path = Field(
        default_factory=lambda: BASE_DIR / "assets" / "all-in-one-wp-migration.zip"
    )

    # --- Screenshots ---
    screenshot_desktop_width: int = 1920
    screenshot_desktop_height: int = 1080
    screenshot_tablet_width: int = 768
    screenshot_tablet_height: int = 1024
    screenshot_mobile_width: int = 375
    screenshot_mobile_height: int = 812
    # Multi-Breakpoints actifs par défaut: 'desktop', 'tablet', 'mobile' (séparés par virgule ou liste)
    screenshot_enabled_devices: str = "desktop,mobile"
    playwright_timeout: int = 60000  # 60s pour permettre le chargement complet CSS/fonts
    screenshot_load_timeout: int = 15000  # 15s max d'attente pour le load state
    screenshot_networkidle_timeout: int = 5000  # 5s max d'attente pour le networkidle
    screenshot_stabilize_delay: int = 1000  # 1000ms de pause de stabilisation avant capture
    # Wait/Scroll intelligent
    screenshot_scroll_delay_ms: int = 60  # Délai entre chaque palier de scroll
    screenshot_scroll_step_px: int = 400  # Pas de scroll en pixels
    screenshot_images_wait_timeout_ms: int = 4000  # Attente max pour le chargement des images


    # --- VRT ---
    vrt_threshold: float = 0.1
    vrt_anti_aliasing_tolerance: int = 2
    vrt_diff_color_r: int = 255
    vrt_diff_color_g: int = 0
    vrt_diff_color_b: int = 255

    # --- Logging ---
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    # --- Sudo ---
    sudo_method: Literal["sudoers", "pkexec", "prompt"] = "sudoers"

    @field_validator("ddev_projects_dir", "host_ddev_projects", "aio_plugin_zip_path", mode="before")
    @classmethod
    def _expand_path(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, str):
            return Path(v).expanduser()
        return v

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def effective_ddev_projects_dir(self) -> Path:
        """Répertoire DDEV effectif (host path prioritaire si défini)."""
        if self.host_ddev_projects:
            return self.host_ddev_projects
        return self.ddev_projects_dir

    # --- Paths dérivés ---
    @property
    def data_dir(self) -> Path:
        return BASE_DIR / "data"

    @property
    def screenshots_dir(self) -> Path:
        return self.data_dir / "screenshots"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def wp_cache_dir(self) -> Path:
        return self.data_dir / "cache" / "wordpress"


# Singleton settings
settings = Settings()
