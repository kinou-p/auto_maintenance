#!/usr/bin/env bash
# ============================================
# Auto Maintenance - Script d'installation
# ============================================
# Compatible Ubuntu 22.04 / 24.04
# Usage: bash install.sh
# ============================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Auto Maintenance - Installation        ║"
echo "║   WordPress Maintenance Automation        ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Vérifier l'OS ─────────────────────────────────────────────
info "Vérification du système..."
if [[ ! -f /etc/os-release ]]; then
    error "Ce script est conçu pour Ubuntu 22.04/24.04."
    exit 1
fi
source /etc/os-release
if [[ "$ID" != "ubuntu" ]]; then
    warn "OS détecté: $ID. Ce script est optimisé pour Ubuntu."
fi
success "OS: $PRETTY_NAME"

# ── 2. Prérequis système ─────────────────────────────────────────
info "Installation des prérequis système..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    wget \
    git \
    jq \
    fonts-dejavu-core \
    > /dev/null 2>&1
success "Prérequis système installés."

# ── 3. Docker ────────────────────────────────────────────────────
if command -v docker &> /dev/null; then
    success "Docker déjà installé: $(docker --version)"
else
    info "Installation de Docker..."
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
    success "Docker installé. IMPORTANT: Déconnectez-vous et reconnectez-vous pour les permissions."
fi

# Vérifier que Docker fonctionne
if docker info &> /dev/null 2>&1; then
    success "Docker est en cours d'exécution."
else
    warn "Docker n'est pas démarré ou vous n'avez pas les permissions."
    warn "Essayez: sudo systemctl start docker && sudo usermod -aG docker $USER"
fi

# ── 4. DDEV ──────────────────────────────────────────────────────
if command -v ddev &> /dev/null; then
    success "DDEV déjà installé: $(ddev version | head -1)"
else
    info "Installation de DDEV..."
    curl -fsSL https://pkg.ddev.com/apt/gpg.key | gpg --dearmor | sudo tee /etc/apt/keyrings/ddev.gpg > /dev/null
    echo "deb [signed-by=/etc/apt/keyrings/ddev.gpg] https://pkg.ddev.com/apt/ * *" | sudo tee /etc/apt/sources.list.d/ddev.list > /dev/null
    sudo apt-get update -qq && sudo apt-get install -y -qq ddev > /dev/null 2>&1
    success "DDEV installé."
fi

# ── 5. Node.js (via NodeSource) ──────────────────────────────────
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    success "Node.js déjà installé: $NODE_VERSION"
else
    info "Installation de Node.js 20.x..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - > /dev/null 2>&1
    sudo apt-get install -y -qq nodejs > /dev/null 2>&1
    success "Node.js installé: $(node --version)"
fi

# ── 6. Environnement Python ──────────────────────────────────────
info "Configuration de l'environnement Python..."
if [[ ! -d "venv" ]]; then
    python3 -m venv venv
    success "Environnement virtuel Python créé."
else
    success "Environnement virtuel Python existant."
fi

source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
success "Dépendances Python installées."

# ── 7. Playwright ────────────────────────────────────────────────
info "Installation des navigateurs Playwright..."
playwright install chromium --with-deps > /dev/null 2>&1
success "Playwright (Chromium) installé."

# ── 8. Frontend ──────────────────────────────────────────────────
info "Installation des dépendances frontend..."
cd frontend
npm install --silent 2>/dev/null
success "Dépendances frontend installées."
cd "$SCRIPT_DIR"

# ── 9. Configuration ─────────────────────────────────────────────
if [[ ! -f ".env" ]]; then
    cp .env.example .env
    success "Fichier .env créé depuis .env.example"
    warn "Modifiez .env selon vos besoins avant de lancer l'application."
else
    success "Fichier .env existant."
fi

# ── 10. Répertoires de données ───────────────────────────────────
mkdir -p data/{screenshots,reports,uploads}
mkdir -p ~/ddev-projects
success "Répertoires de données créés."

# ── 11. Configuration sudoers (optionnel) ────────────────────────
echo ""
read -p "Configurer les permissions sudoers pour /etc/hosts ? (y/N) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    SUDOERS_FILE="/etc/sudoers.d/auto-maintenance"
    SUDOERS_CONTENT="${USER} ALL=(root) NOPASSWD: /usr/bin/cp /tmp/*.hosts /etc/hosts
${USER} ALL=(root) NOPASSWD: /usr/bin/cp /etc/hosts /tmp/hosts.backup.*
${USER} ALL=(root) NOPASSWD: /usr/bin/chmod 644 /etc/hosts"

    echo "$SUDOERS_CONTENT" | sudo tee /tmp/auto-maintenance.sudoers > /dev/null
    if sudo visudo -cf /tmp/auto-maintenance.sudoers; then
        sudo cp /tmp/auto-maintenance.sudoers "$SUDOERS_FILE"
        sudo chmod 440 "$SUDOERS_FILE"
        success "Permissions sudoers configurées."
    else
        error "Erreur dans la configuration sudoers."
    fi
    rm -f /tmp/auto-maintenance.sudoers
else
    info "Configuration sudoers ignorée. Vous devrez entrer votre mot de passe sudo."
fi

# ── Résumé ────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Installation terminée !                ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Pour lancer l'application :"
echo ""
echo "  1. Activez l'environnement Python :"
echo "     source venv/bin/activate"
echo ""
echo "  2. Lancez le backend :"
echo "     uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "  3. Lancez le frontend (dans un autre terminal) :"
echo "     cd frontend && npm run dev"
echo ""
echo "  4. Ouvrez le navigateur :"
echo "     http://localhost:5173"
echo ""
echo "  Ou utilisez le script de démarrage :"
echo "     bash start.sh"
echo ""
