"""
Tests unitaires pour utils/wpress_extractor.py
"""

from pathlib import Path
import pytest
from backend.utils.wpress_extractor import extract_wpress_fast, extract_wpress_sync


def create_dummy_wpress_file(filepath: Path, filename: str, content: bytes):
    """
    Crée un fichier .wpress minimal avec l'en-tête de 4377 octets requis.
    """
    hdr = bytearray(4377)
    
    fn_bytes = filename.encode("utf-8")
    hdr[:len(fn_bytes)] = fn_bytes
    
    sz_bytes = str(len(content)).encode("utf-8")
    hdr[255:255 + len(sz_bytes)] = sz_bytes

    prefix_bytes = b"uploads/test_folder"
    hdr[281:281 + len(prefix_bytes)] = prefix_bytes

    with open(filepath, "wb") as f:
        f.write(hdr)
        f.write(content)


def test_extract_wpress_sync(tmp_path):
    """Vérifie l'extraction synchrone d'un fichier .wpress de test."""
    wpress_path = tmp_path / "test.wpress"
    target_dir = tmp_path / "extracted"
    target_dir.mkdir()

    test_content = b"Hello WPRESS World!"
    create_dummy_wpress_file(wpress_path, "test_file.txt", test_content)

    count = extract_wpress_sync(wpress_path, target_dir)
    assert count == 1

    extracted_file = target_dir / "wp-content" / "uploads" / "test_folder" / "test_file.txt"
    assert extracted_file.exists()
    assert extracted_file.read_bytes() == test_content


@pytest.mark.asyncio
async def test_extract_wpress_fast_nonexistent(tmp_path):
    """Vérifie que l'extraction échoue proprement si le fichier n'existe pas."""
    result = await extract_wpress_fast(tmp_path / "missing.wpress", tmp_path / "out")
    assert result is False
