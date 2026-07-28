# ==============================================================================
# Auto Maintenance - Makefile Universel (Windows, Linux, macOS)
# ==============================================================================

# Détection du système d'exploitation
ifeq ($(OS),Windows_NT)
    DETECTED_OS := Windows
    PYTHON := .\venv\Scripts\python.exe
    INSTALL_SCRIPT := powershell -ExecutionPolicy Bypass -File .\install.ps1
    START_SCRIPT := $(PYTHON) start.py
    RM := rmdir /s /q
else
    DETECTED_OS := $(shell uname -s)
    PYTHON := ./venv/bin/python3
    INSTALL_SCRIPT := ./install.sh
    START_SCRIPT := $(PYTHON) start.py
    RM := rm -rf
endif

.PHONY: all help install start dev cli cli-interactive clean

all: install

help:
	@echo "================================================================="
	@echo " Auto Maintenance - Commande Makefile ($(DETECTED_OS) détecté)"
	@echo "================================================================="
	@echo " make          - (Par défaut) Vérifie les prérequis et installe l'environnement"
	@echo " make install  - Auto-vérification/installation (Python, Node, Docker, DDEV, venv, npm, Playwright)"
	@echo " make start    - Lance le backend (FastAPI) et le frontend (Vite)"
	@echo " make cli      - Lance l'interface CLI d'administration"
	@echo " make clean    - Nettoie les fichiers temporaires et les caches"
	@echo "================================================================="

install:
	@echo "▶️ Lancement de l'installation pour $(DETECTED_OS)..."
	$(INSTALL_SCRIPT)

start:
	@echo "▶️ Démarrage de Auto Maintenance sous $(DETECTED_OS)..."
	$(START_SCRIPT)

cli:
	$(PYTHON) cli.py --help

cli-interactive:
	$(PYTHON) cli.py interactive

dev: start

clean:
	@echo "🧹 Nettoyage des fichiers temporaires..."
	$(RM) data\screenshots\temp 2>nul || true
	$(RM) data/screenshots/temp 2>nul || true
	@echo "✅ Nettoyage effectué."

