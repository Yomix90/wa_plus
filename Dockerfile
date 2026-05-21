# ═══════════════════════════════════════════════
# DOCKERFILE WAPLUS — PROD/DOKPLOY
# ═══════════════════════════════════════════════

FROM python:3.11-slim

# Éviter l'écriture de fichiers .pyc et forcer l'affichage immédiat des logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production
ENV PORT=5000
ENV DATABASE_URL=sqlite:////app/data/whatsapp_bulk.db

WORKDIR /app

# Installer les outils nécessaires et nettoyer le cache
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc-dev \
    && rm -rf /var/lib/apt/lists/*

# Installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Créer le répertoire pour les données SQLite persistantes
RUN mkdir -p /app/data

# Copier le reste du projet dans le conteneur
COPY . .

# Exposer le port de l'application
EXPOSE 5000

# Commande de démarrage avec gunicorn pour la production (4 workers)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "app:flask_app"]
