# Auto Maintenance 🛠️

> **Automatisation de la maintenance WordPress avec Visual Regression Testing (VRT)**

Auto Maintenance est une solution complète pour orchestrer et sécuriser la maintenance de sites WordPress locaux (via DDEV). Elle permet d'automatiser les mises à jour (cœur, plugins, thèmes) tout en garantissant l'intégrité visuelle du site grâce à des tests de régression visuelle (VRT) avant/après.

---

## 🚀 Fonctionnalités

- **Système d'Authentification & Admin Setup** : Inscription de l'admin initial, connexion JWT sécurisée, protection des routes backend & frontend et gestion d'utilisateurs.
- **Thème Sombre / Clair** : Basculement dynamique de thème (Dark/Light mode) et profil utilisateur avec déconnexion.
- **Visual Regression Testing (VRT) avancé** :
  - Capture d'écran automatique (Desktop & Mobile) via Playwright (gestion robuste des timeouts, scroll progressif et animations).
  - Comparaison "Pixel Perfect" avant/après mise à jour avec basculement 2-up, slider interactif, overlay et différence d'images.
  - Détection et surlignage des changements visuels indésirables.
- **Bouton de navigation rapide** : Bouton flottant pour défiler rapidement en haut/bas de page.
- **Gestion de projets DDEV** : Création, import, gestion et détection d'erreurs (auto-réparation `project_list.yaml`, nettoyage des réseaux orphelins, retry DDEV router).
- **Mises à jour automatisées & Workflow** : Détection et application des mises à jour WordPress avec suivi des statuts (`pending`, etc.).
- **Rapports détaillés & Logs** : Historique des maintenances, preuves visuelles et logs en temps réel via WebSocket avec filtrage et recherche.
- **Architecture moderne** : Backend FastAPI (Python) avec authentification JWT/Passlib + Frontend React/Vite/TailwindCSS/Lucide-react.

## 📋 Prérequis

Ce projet est optimisé pour **Ubuntu 22.04 / 24.04**.

- **OS** : Linux (Ubuntu recommandé)
- **Docker** : Engine & Compose (pour DDEV)
- **DDEV** : Gestionnaire d'environnement local PHP/MySQL
- **Python** : 3.10+
- **Node.js** : 20.x+ (pour le frontend)

## 🛠️ Installation

### Méthode Automatique (Recommandée)

Le script d'installation configure tout l'environnement (dépendances système, Docker, DDEV, Node.js, venv Python, etc.).

```bash
chmod +x install.sh
./install.sh
```

### Méthode Manuelle

1. **Backend & Python**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   playwright install chromium --with-deps
   ```

2. **Frontend**
   ```bash
   cd frontend
   npm install
   cd ..
   ```

3. **Environnement**
   ```bash
   cp .env.example .env
   # Modifiez .env si nécessaire
   ```

4. **Dossiers de données**
   ```bash
   mkdir -p data/{screenshots,reports,uploads}
   ```

## ⚙️ Configuration

Toute la configuration se trouve dans le fichier `.env`.

| Variable | Description | Défaut |
|----------|-------------|---------|
| `APP_PORT` | Port du backend API | `8000` |
| `FRONTEND_PORT` | Port du frontend React | `5173` |
| `DDEV_PROJECTS_DIR` | Dossier des projets DDEV | `~/ddev-projects` |
| `VRT_THRESHOLD` | Sensibilité de la comparaison d'images (0.0 - 1.0) | `0.1` |
| `PLAYWRIGHT_TIMEOUT` | Timeout capture d'écran (ms) | `60000` |

## ▶️ Démarrage

### Via script (Recommandé)

Lance le backend et le frontend en arrière-plan.

```bash
./start.sh
```

### Manuellement

**Terminal 1 (Backend)**
```bash
source venv/bin/activate
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 (Frontend)**
```bash
cd frontend
npm run dev
```

L'application sera accessible sur :
- **Dashboard** : [http://localhost:5173](http://localhost:5173)
- **API Docs** : [http://localhost:8000/docs](http://localhost:8000/docs)

### Mode CLI (Ligne de Commande) 💻

Une interface CLI complète est disponible pour tester et administrer vos projets sans ouvrir l'interface web :

```bash
# Menu interactif guidé
python cli.py interactive

# Gestion des projets
python cli.py projects list
python cli.py projects status <nom-projet>
python cli.py projects start <nom-projet>

# Mises à jour WordPress & Visual Regression Testing (VRT)
python cli.py wp updates <nom-projet>
python cli.py vrt test <nom-projet>
python cli.py maintenance run <nom-projet>

# Diagnostic système
python cli.py system status
```


## 🏗️ Architecture Technique

- **Backend** : FastAPI, SQLAlchemy (Async), aiosqlite.
- **Automation** : Playwright (Screenshots), Pillow/Scikit-image (VRT), Subprocess (DDEV/CLI).
- **Frontend** : React 19, Vite, TailwindCSS, Shadcn/UI, Zustand.
- **Communication** : API REST + WebSockets (pour logs temps réel).

## ❓ Dépannage

**Erreur : "Docker permission denied"**
Assurez-vous que votre utilisateur est dans le groupe docker.
```bash
sudo usermod -aG docker $USER
newgrp docker
```

**Erreur : "Environnement virtuel non trouvé"**
Vérifiez que vous avez bien exécuté `./install.sh` ou créé le venv manuellement.

**Logs**
Les logs sont affichés dans le terminal de lancement ou dans la console du navigateur via WebSocket.

## 📄 Licence

MIT License.
