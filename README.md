# 🟢 WaPlus — WhatsApp Bulk & AI Assistant

WaPlus est une application web fullstack moderne et performante conçue pour envoyer des messages WhatsApp en masse (campagnes ciblées), recevoir les réponses en temps réel via un Webhook, y répondre automatiquement de manière intelligente via l'IA de pointe Google Gemini, et planifier des campagnes différées grâce à un orchestrateur de tâches en arrière-plan.

---

## 🚀 Fonctionnalités Clés

1. **Tableau de Bord Premium** : Visualisez en temps réel les KPIs clés (messages envoyés/reçus, taux de réponse, campagnes actives) et gérez vos dernières conversations.
2. **Messagerie en Masse (Bulk)** : Envoyez des messages immédiats ou planifiés à tous vos contacts ou à des groupes ciblés, avec un système de rate-limiting (1s d'intervalle) pour respecter les directives Meta.
3. **Suivi d'Envoi SSE (Server-Sent Events)** : Obtenez une barre de progression en temps réel et sans blocage lors des envois de masse.
4. **Réponses Automatiques par IA** : Connexion native au modèle ultrarapide `gemini-1.5-flash` pour générer des réponses automatiques contextuelles en prenant en compte les 5 derniers messages échangés.
5. **Gestion et Importation CSV** : CRUD complet de contacts avec un outil d'importation de fichiers CSV en drag-and-drop et normalisation automatique des numéros au format E.164.
6. **Interface de Chat Interactive** : Discutez en direct avec vos clients via un fil de discussion style WhatsApp Web avec des indicateurs graphiques de réception (remise, lu, échoué).
7. **Prêt pour Dokploy** : Configuration complète multi-conteneurs fournie avec une base de données SQLite persistante pour un déploiement fluide en VPS.

---

## 🛠️ Stack Technique

- **Backend** : Python 3.11+, Flask, Flask-APScheduler (tâches récurrentes), Flask-SQLAlchemy
- **Base de données** : SQLite (via SQLAlchemy)
- **IA** : Google Generative AI (`gemini-1.5-flash`)
- **Frontend** : HTML5, CSS3 Vanilla (Thème premium glassmorphism sombre), JavaScript (Fetch, SSE, Lucide Icons)
- **Déploiement** : Docker / Docker Compose / Gunicorn

---

## 📦 Installation et Lancement Local

### 1. Cloner le projet et préparer l'environnement
Dans votre terminal :
```bash
# Entrer dans le dossier
cd WaPlus

# Créer un environnement virtuel
python -m venv venv

# Activer l'environnement virtuel (Windows)
.\venv\Scripts\activate

# Installer les dépendances requis
pip install -r requirements.txt
```

### 2. Configurer les variables d'environnement
Renommez le fichier `.env.example` en `.env` et complétez vos clés :
```env
WHATSAPP_TOKEN=EAA...                   # Jeton Meta d'accès permanent
PHONE_NUMBER_ID=1234567890              # ID du numéro expéditeur WhatsApp
WEBHOOK_VERIFY_TOKEN=mon_token_secret   # Token que vous choisissez pour Meta
GEMINI_API_KEY=AIzaSy...                # Clé API Google AI Studio
DATABASE_URL=sqlite:///whatsapp_bulk.db
SECRET_KEY=cle_flask_secrete_super_robuste
FLASK_ENV=development
```

### 3. Lancer l'application localement
```bash
python app.py
```
L'application est accessible localement à l'adresse : [http://localhost:5000](http://localhost:5000).

---

## 🔗 Configuration du Webhook WhatsApp avec `ngrok` (Dev)

Meta exige une adresse HTTPS publique pour envoyer les événements de réception (messages, accusés de réception).

1. Lancez un tunnel sécurisé local via **ngrok** :
   ```bash
   ngrok http 5000
   ```
2. Récupérez l'URL HTTPS fournie par ngrok (ex: `https://abcd-123.ngrok-free.app`).
3. Allez dans votre **Console Meta for Developers** > **WhatsApp** > **Configuration**.
4. Cliquez sur **Modifier** dans la partie Webhooks :
   - **URL de rappel** : `https://abcd-123.ngrok-free.app/webhook`
   - **Jeton de vérification** : Indiquez la valeur exacte de votre `WEBHOOK_VERIFY_TOKEN` (ex: `mon_token_secret`).
5. Cliquez sur **Vérifier et enregistrer**.
6. Dans les **Champs de Webhook**, abonnez-vous aux champs **messages** pour recevoir les messages entrants et les accusés de réception.

---

## 🐳 Déploiement Production sur Dokploy

**Dokploy** simplifie le déploiement de vos applications conteneurisées. WaPlus est livré prêt à l'emploi grâce à son `Dockerfile` et son `docker-compose.yml`.

### Configuration sur le Panel Dokploy :
1. Créez un **Nouveau Projet** dans Dokploy.
2. Créez un service de type **Compose** (Docker Compose) ou **Application** (en liant votre dépôt Git).
3. configurez les variables d'environnement dans l'onglet **Environment Variables** de Dokploy :
   - `SECRET_KEY` : une clé aléatoire sécurisée.
   - `WHATSAPP_TOKEN` : Jeton Meta.
   - `PHONE_NUMBER_ID` : Jeton Meta.
   - `WEBHOOK_VERIFY_TOKEN` : Jeton de vérification de webhook choisi.
   - `WEBHOOK_APP_SECRET` : (Recommandé pour la production) Le **Secret de l'application** Meta qui sert à vérifier les signatures HMAC SHA-256 de Meta afin de bloquer les attaques.
   - `GEMINI_API_KEY` : Votre clé Google AI Studio.
4. **Persistance SQLite** :
   Le fichier `docker-compose.yml` définit un volume persistant nommé `waplus_data` monté sur `/app/data`. Dokploy s'occupera automatiquement de persister ce volume. Ainsi, lors des redéploiements ou mises à jour de code, **vous ne perdrez aucune donnée de contact, campagne ou message**.
5. Cliquez sur **Deploy** ! Votre application est opérationnelle en production.
