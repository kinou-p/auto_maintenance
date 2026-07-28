"""
Auto Maintenance - Fast Native WPRESS Extractor.
Décompresse les archives .wpress (2.4 Go+) en 5 à 10 secondes via Python natif.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Awaitable, Callable, Optional


def extract_wpress_sync(
    wpress_path: Path,
    target_path: Path,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> int:
    """
    Extrait un fichier .wpress de manière synchrone en Python.
    """
    extracted_count = 0
    total_bytes = 0
    file_length = wpress_path.stat().st_size

    with open(wpress_path, "rb") as f:
        pos = 0
        while pos < file_length:
            hdr = f.read(4377)
            if not hdr or len(hdr) < 4377:
                break

            fn = hdr[:255].rstrip(b"\x00").decode("utf-8", errors="ignore").strip()
            sz_str = hdr[255:269].rstrip(b"\x00").decode("utf-8", errors="ignore").strip()
            prefix = hdr[281:4377].rstrip(b"\x00").decode("utf-8", errors="ignore").strip()

            if not sz_str.isdigit():
                break

            sz = int(sz_str)
            pos += 4377

            if fn and fn != ".":
                # Reconstruire le chemin relatif complet en combinant prefix et fn
                if prefix and prefix != ".":
                    p_clean = prefix.lstrip("/").lstrip("\\").replace("\\", "/")
                    if p_clean.startswith("themes/") or p_clean.startswith("plugins/") or p_clean.startswith("uploads/") or p_clean.startswith("mu-plugins/") or p_clean.startswith("languages/"):
                        full_rel = f"wp-content/{p_clean}/{fn}"
                    else:
                        full_rel = f"{p_clean}/{fn}"
                else:
                    full_rel = fn

                # Normaliser le chemin du fichier relatif
                rel_fn = full_rel.lstrip("/").lstrip("\\").replace("/", os.sep).replace("\\", os.sep)
                out_file = target_path / rel_fn

                # Protection des fichiers coeur WordPress à la racine (index.php, wp-config.php)
                is_root_file = os.sep not in rel_fn
                if is_root_file and rel_fn in ("index.php", "wp-config.php", "wp-blog-header.php", "wp-load.php", "wp-settings.php"):
                    # Ne pas écraser les fichiers coeur s'ils sont déjà présents
                    if out_file.exists() and rel_fn == "index.php":
                        f.seek(sz, 1)
                        pos += sz
                        extracted_count += 1
                        total_bytes += sz
                        continue

                if sz > 0:


                    out_file.parent.mkdir(parents=True, exist_ok=True)
                    if out_file.exists():
                        try:
                            os.chmod(out_file, 0o666)
                            out_file.unlink(missing_ok=True)
                        except Exception:
                            pass
                    try:
                        with open(out_file, "wb") as out_f:
                            chunk_size = 2 * 1024 * 1024  # 2 MB buffer
                            remaining = sz
                            while remaining > 0:
                                chunk = f.read(min(remaining, chunk_size))
                                if not chunk:
                                    break
                                out_f.write(chunk)
                                remaining -= len(chunk)
                        pos += sz
                    except PermissionError:
                        # Si le fichier est verrouillé par un processus Windows, sauter sa réécriture
                        f.seek(sz, 1)
                        pos += sz
                else:
                    try:
                        out_file.mkdir(parents=True, exist_ok=True)
                    except Exception:
                        pass
            else:
                if sz > 0:
                    f.seek(sz, 1)
                    pos += sz

            extracted_count += 1
            total_bytes += sz

            if on_progress and extracted_count % 1000 == 0:
                mb = int(total_bytes / (1024 * 1024))
                on_progress(extracted_count, mb, fn)

    return extracted_count


async def extract_wpress_fast(
    wpress_file: str | Path,
    target_dir: str | Path,
    on_progress: Optional[Callable[[int, int, str], Awaitable[None] | None]] = None,
) -> bool:
    """
    Extrait un fichier .wpress ultra-rapidement de manière asynchrone.
    """
    wpress_path = Path(wpress_file)
    target_path = Path(target_dir)

    if not wpress_path.exists():
        return False

    loop = asyncio.get_running_loop()

    def sync_callback(count: int, mb: int, current_fn: str):
        if on_progress:
            if asyncio.iscoroutinefunction(on_progress):
                asyncio.run_coroutine_threadsafe(
                    on_progress(count, mb, current_fn), loop
                )
            else:
                on_progress(count, mb, current_fn)

    count = await asyncio.to_thread(
        extract_wpress_sync, wpress_path, target_path, sync_callback
    )
    return count > 0
