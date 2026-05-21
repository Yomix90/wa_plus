import os
import logging
from flask import Flask, render_template

# Configurer les logs de manière lisible et structurée
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s : %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Définition globale pour accès depuis les threads en tâche de fond
flask_app = None

def create_app():
    """Factory de création de l'application Flask."""
    global flask_app
    
    app = Flask(__name__)
    
    # Charger la configuration
    from config import Config
    app.config.from_object(Config)
    
    # Initialiser la base de données SQLite & seed AIConfig
    from database import init_db
    init_db(app)
    
    # Initialiser le Planificateur APScheduler
    from services.scheduler import init_scheduler
    init_scheduler(app)
    
    # Importer et enregistrer les Blueprints de l'API
    from routes.webhook import webhook_bp
    from routes.messages import messages_bp
    from routes.contacts import contacts_bp
    from routes.ai import ai_bp
    
    # Le webhook reste à la racine pour Meta Business Manager
    app.register_blueprint(webhook_bp, url_prefix='')
    
    # Les APIs d'administration sont préfixées par /api pour la propreté architecturale
    app.register_blueprint(messages_bp, url_prefix='/api')
    app.register_blueprint(contacts_bp, url_prefix='/api')
    app.register_blueprint(ai_bp, url_prefix='/api')
    
    # ═══════════════════════════════════════════════
    # ROUTES DE RENDU DE L'INTERFACE GRAPHIQUE (UI)
    # ═══════════════════════════════════════════════
    
    @app.route('/')
    def dashboard_page():
        """Page principale de statistiques et KPI."""
        return render_template('dashboard.html', active_page='dashboard')
        
    @app.route('/contacts')
    def contacts_page():
        """Page de gestion et d'importation des contacts."""
        return render_template('contacts.html', active_page='contacts')
        
    @app.route('/send-bulk')
    def send_bulk_page():
        """Page de composition et d'envoi en lot."""
        return render_template('send_bulk.html', active_page='send-bulk')
        
    @app.route('/history')
    def history_page():
        """Page de fil de discussion et historique des messages."""
        return render_template('history.html', active_page='history')
        
    @app.route('/settings')
    def settings_page():
        """Page de configuration globale et de diagnostics."""
        return render_template('settings.html', active_page='settings')
        
    # Gestionnaire d'erreur 404 personnalisé avec thème premium
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('base.html', error_404=True), 404

    flask_app = app
    return app

if __name__ == '__main__':
    flask_app = create_app()
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Démarrage de l'application WaPlus sur le port {port}...")
    flask_app.run(host='0.0.0.0', port=port, debug=flask_app.config['DEBUG'])
else:
    # Pour le serveur de production WSGI gunicorn (Dokploy)
    flask_app = create_app()
