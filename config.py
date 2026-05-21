import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

# Chemin vers la racine du projet
BASE_DIR = Path(__file__).resolve().parent

# Charger le fichier .env si présent
load_dotenv(os.path.join(BASE_DIR, '.env'))

class Config:
    """Configuration de base de l'application Flask."""
    
    # Clef secrète de Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(32))
    
    # Configuration de la base de données SQLAlchemy
    # Par défaut, utilise sqlite:///whatsapp_bulk.db
    DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///whatsapp_bulk.db')
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
        
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Configuration du planificateur de tâches (Flask-APScheduler)
    SCHEDULER_API_ENABLED = True
    SCHEDULER_TIMEZONE = "UTC"
    
    # Configuration des APIs externes (chargement par défaut)
    OPENWA_API_URL = os.environ.get('OPENWA_API_URL', 'https://openwa-waplus-hmvwgl-24722a-51-210-177-24.sslip.io')
    OPENWA_API_KEY = os.environ.get('OPENWA_API_KEY', '')
    OPENWA_SESSION_ID = os.environ.get('OPENWA_SESSION_ID', 'default')
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
    
    # Mode de l'application
    FLASK_ENV = os.environ.get('FLASK_ENV', 'development')
    DEBUG = FLASK_ENV == 'development'
