# Auto Maintenance - Windows Launcher (PowerShell)

$pythonExe = ".\venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

& $pythonExe start.py
