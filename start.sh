#!/usr/bin/env bash
# ============================================
# Auto Maintenance - Script de démarrage
# ============================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; }

# Vérifier l'environnement virtuel
if [[ ! -d "venv" ]]; then
    error "Environnement virtuel non trouvé. Lancez d'abord: bash install.sh"
    exit 1
fi

# Activer l'environnement virtuel
source venv/bin/activate

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Auto Maintenance - Démarrage           ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# Fonction de nettoyage
cleanup() {
    info "Arrêt des processus..."
    kill "$BACKEND_PID" 2>/dev/null || true
    kill "$FRONTEND_PID" 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM

# Lancer le backend
info "Démarrage du backend (port 8000)..."
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
sleep 2

# Vérifier que le backend est démarré
if kill -0 "$BACKEND_PID" 2>/dev/null; then
    success "Backend démarré (PID: $BACKEND_PID)"
else
    error "Le backend n'a pas pu démarrer."
    exit 1
fi

# Lancer le frontend
info "Démarrage du frontend (port 5173)..."
cd frontend && npm run dev &
FRONTEND_PID=$!
cd "$SCRIPT_DIR"
sleep 3

if kill -0 "$FRONTEND_PID" 2>/dev/null; then
    success "Frontend démarré (PID: $FRONTEND_PID)"
else
    error "Le frontend n'a pas pu démarrer."
    kill "$BACKEND_PID" 2>/dev/null || true
    exit 1
fi

echo ""
success "Application prête !"
echo ""
echo "  Dashboard : http://localhost:5173"
echo "  API       : http://localhost:8000/docs"
echo ""
echo "  Appuyez sur Ctrl+C pour arrêter."
echo ""

# Attendre
wait
