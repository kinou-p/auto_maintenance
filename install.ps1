# Auto Maintenance - Windows Installation & Dependency Check Script (PowerShell)

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Verification et Installation de Auto Maintenance (Windows)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# Fonction pour verifier et installer via winget si manquant
function Ensure-Tool {
    param (
        [string]$CommandName,
        [string]$WingetId,
        [string]$DisplayName,
        [bool]$Optional = $false
    )

    Write-Host "`n[Verif] $DisplayName..." -ForegroundColor Yellow

    if (Get-Command $CommandName -ErrorAction SilentlyContinue) {
        $ver = & $CommandName --version 2>&1
        Write-Host "  [OK] $DisplayName est deja installe ($ver)." -ForegroundColor Green
        return $true
    }

    Write-Host "  [ATTENTION] $DisplayName n'a pas ete trouve." -ForegroundColor Yellow

    # Tenter l'installation via winget si disponible
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "  [INFO] Tentative d'installation automatique via winget ($WingetId)..." -ForegroundColor Cyan
        try {
            winget install --id $WingetId --silent --accept-source-agreements --accept-package-agreements
            
            # Recharger le PATH systeme pour la session en cours
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

            if (Get-Command $CommandName -ErrorAction SilentlyContinue) {
                Write-Host "  [OK] $DisplayName installe avec succes !" -ForegroundColor Green
                return $true
            } else {
                Write-Host "  [INFO] $DisplayName installe. Si la commande n'est pas reconnue, redemarrez votre terminal." -ForegroundColor Cyan
                return $true
            }
        } catch {
            Write-Host "  [ERREUR] Echec de l'installation automatique de $DisplayName via winget." -ForegroundColor Red
        }
    } else {
        Write-Host "  [ATTENTION] 'winget' n'est pas disponible sur votre systeme." -ForegroundColor Yellow
    }

    if ($Optional) {
        Write-Host "  [INFO] (Optionnel) Vous pourrez installer $DisplayName plus tard." -ForegroundColor Gray
        return $false
    } else {
        Write-Host "  [ERREUR] $DisplayName est requis. Veuillez l'installer manuellement puis relancer ce script." -ForegroundColor Red
        return $false
    }
}

# 1. Verifier / Installer Python 3
Ensure-Tool -CommandName "python" -WingetId "Python.Python.3.12" -DisplayName "Python 3" -Optional $false

# 2. Verifier / Installer Node.js & npm
Ensure-Tool -CommandName "node" -WingetId "OpenJS.NodeJS.LTS" -DisplayName "Node.js (npm)" -Optional $false

# 3. Verifier / Installer Docker Desktop
Ensure-Tool -CommandName "docker" -WingetId "Docker.DockerDesktop" -DisplayName "Docker Desktop" -Optional $true

# 4. Verifier / Installer DDEV
Ensure-Tool -CommandName "ddev" -WingetId "DDEVFoundation.DDEV" -DisplayName "DDEV" -Optional $true

# 5. Creer l'environnement virtuel venv
Write-Host "`n------------------------------------------------------------" -ForegroundColor Cyan
Write-Host " Configuration du projet Auto Maintenance..." -ForegroundColor Cyan
Write-Host "------------------------------------------------------------" -ForegroundColor Cyan

$pythonExe = ".\venv\Scripts\python.exe"

if (-not (Test-Path "venv")) {
    Write-Host "[INFO] Creation du venv Python..." -ForegroundColor Yellow
    python -m venv venv
    Write-Host "[OK] venv cree." -ForegroundColor Green
}

if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

# 6. Dependances Python
Write-Host "`n[INFO] Installation des dependances Python (pip)..." -ForegroundColor Yellow
& $pythonExe -m pip install --upgrade pip -q
& $pythonExe -m pip install -r requirements.txt

# 7. Playwright Chromium
Write-Host "`n[INFO] Installation du navigateur Chromium (Playwright)..." -ForegroundColor Yellow
& $pythonExe -m playwright install chromium

# 8. Dependances Frontend npm
Write-Host "`n[INFO] Installation des dependances Frontend (npm)..." -ForegroundColor Yellow
if (Test-Path "frontend") {
    Push-Location frontend
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        npm install
    } else {
        Write-Host "[ATTENTION] npm introuvable dans cette session. Redemarrez le terminal apres l'installation de Node.js." -ForegroundColor Yellow
    }
    Pop-Location
}

# 9. Configurations et Dossiers
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[OK] Fichier .env cree a partir de .env.example." -ForegroundColor Green
}

New-Item -ItemType Directory -Force -Path "data\screenshots", "data\reports", "data\uploads", "data\cache\wordpress" | Out-Null

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host " Verification et installation terminees !" -ForegroundColor Green
Write-Host " Pour lancer l'application : python start.py (ou .\start.ps1)" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
