"""
Tests unitaires pour utils/command.py
"""

import sys
import pytest
from backend.utils.command import CommandResult, run_command, run_ddev_command, run_wp_cli


def test_command_result_post_init():
    """Vérifie le calcul automatique du drapeau success."""
    res_success = CommandResult(returncode=0, stdout="ok", stderr="", command="echo 1")
    assert res_success.success is True

    res_failed = CommandResult(returncode=1, stdout="", stderr="error", command="false")
    assert res_failed.success is False


@pytest.mark.asyncio
async def test_run_command_echo():
    """Vérifie l'exécution basique d'une commande système."""
    cmd = [sys.executable, "-c", "print('hello world')"]
    res = await run_command(cmd)
    assert res.success is True
    assert res.returncode == 0
    assert "hello world" in res.stdout


@pytest.mark.asyncio
async def test_run_command_output_callback():
    """Vérifie que la callback on_output reçoit les lignes de sortie."""
    captured = []

    def on_out(line: str):
        captured.append(line)

    cmd = [sys.executable, "-c", "print('line1'); print('line2')"]
    res = await run_command(cmd, on_output=on_out)
    assert res.success is True
    assert "line1" in captured
    assert "line2" in captured


@pytest.mark.asyncio
async def test_run_command_timeout():
    """Vérifie la gestion du timeout."""
    cmd = [sys.executable, "-c", "import time; time.sleep(5)"]
    res = await run_command(cmd, timeout=1)
    assert res.success is False
    assert res.returncode == -1
    assert "timeout" in res.stderr.lower()
