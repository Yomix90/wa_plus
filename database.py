from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Contact(db.Model):
    """Représente un contact dans le système."""
    __tablename__ = 'contacts'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(30), unique=True, nullable=False)  # Format E.164 (ex: +33612345678)
    group_tag = db.Column(db.String(50), nullable=True, index=True) # Tag groupe pour envois ciblés
    opted_out = db.Column(db.Boolean, default=False, nullable=False) # Désabonné (opt-out)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relation vers les messages associés
    messages = db.relationship('Message', backref='contact', lazy='dynamic', cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'group_tag': self.group_tag,
            'opted_out': self.opted_out,
            'created_at': self.created_at.isoformat()
        }

class Message(db.Model):
    """Représente un message envoyé ou reçu."""
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True)
    contact_id = db.Column(db.Integer, db.ForeignKey('contacts.id', ondelete='CASCADE'), nullable=False)
    direction = db.Column(db.String(10), nullable=False) # 'in' (reçu) ou 'out' (envoyé)
    content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), default='sent', nullable=False) # 'pending', 'sent', 'delivered', 'failed'
    openwa_message_id = db.Column(db.String(100), nullable=True, index=True) # ID unique renvoyé par OpenWA
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'contact_id': self.contact_id,
            'contact_name': self.contact.name if self.contact else 'Inconnu',
            'contact_phone': self.contact.phone if self.contact else '',
            'direction': self.direction,
            'content': self.content,
            'status': self.status,
            'openwa_message_id': self.openwa_message_id,
            'sent_at': self.sent_at.isoformat()
        }

class Campaign(db.Model):
    """Représente une campagne d'envoi en masse (bulk)."""
    __tablename__ = 'campaigns'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    template = db.Column(db.Text, nullable=False) # Contenu du message
    target_group = db.Column(db.String(50), nullable=True) # Groupe cible (ex: 'all' ou tag spécifique)
    scheduled_at = db.Column(db.DateTime, nullable=True) # Null si envoi immédiat
    status = db.Column(db.String(20), default='pending', nullable=False) # 'pending', 'sent', 'failed'
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'template': self.template,
            'target_group': self.target_group,
            'scheduled_at': self.scheduled_at.isoformat() if self.scheduled_at else None,
            'status': self.status,
            'created_at': self.created_at.isoformat()
        }

class AIConfig(db.Model):
    """Configuration globale du module d'intelligence artificielle Gemini et identifiants."""
    __tablename__ = 'ai_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    system_prompt = db.Column(db.Text, nullable=False)
    auto_reply_enabled = db.Column(db.Boolean, default=False, nullable=False)
    
    # Stockage direct des secrets en BDD pour modification directe par l'UI
    # On utilisera ces champs en priorité, sinon repli sur le .env de config.py
    openwa_api_url = db.Column(db.Text, nullable=True)
    openwa_api_key = db.Column(db.Text, nullable=True)
    openwa_session_id = db.Column(db.String(100), nullable=True)
    gemini_api_key = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    @classmethod
    def get_config(cls):
        """Récupère l'unique configuration active (ID=1) ou la crée si absente."""
        config = cls.query.get(1)
        if not config:
            config = cls(
                id=1,
                system_prompt=(
                    "Tu es un assistant commercial WhatsApp expert, amical et concis. "
                    "Réponds toujours poliment et brièvement (maximum 2-3 phrases) en français. "
                    "Aide le client avec professionnalisme."
                ),
                auto_reply_enabled=False
            )
            db.session.add(config)
            db.session.commit()
        return config


def init_db(app):
    """Initialise la base de données SQLite et crée les tables."""
    db.init_app(app)
    with app.app_context():
        # Migration automatique de l'ancienne structure de base de données si elle existe
        try:
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            
            if inspector.has_table('ai_configs'):
                columns = [col['name'] for col in inspector.get_columns('ai_configs')]
                with db.engine.begin() as conn:
                    if 'openwa_api_url' not in columns:
                        conn.execute(db.text("ALTER TABLE ai_configs ADD COLUMN openwa_api_url TEXT"))
                    if 'openwa_api_key' not in columns:
                        conn.execute(db.text("ALTER TABLE ai_configs ADD COLUMN openwa_api_key TEXT"))
                    if 'openwa_session_id' not in columns:
                        conn.execute(db.text("ALTER TABLE ai_configs ADD COLUMN openwa_session_id VARCHAR(100)"))
                    if 'gemini_api_key' not in columns:
                        conn.execute(db.text("ALTER TABLE ai_configs ADD COLUMN gemini_api_key TEXT"))
            
            if inspector.has_table('messages'):
                columns = [col['name'] for col in inspector.get_columns('messages')]
                with db.engine.begin() as conn:
                    if 'openwa_message_id' not in columns:
                        conn.execute(db.text("ALTER TABLE messages ADD COLUMN openwa_message_id VARCHAR(100)"))
                        try:
                            conn.execute(db.text("CREATE INDEX IF NOT EXISTS ix_messages_openwa_message_id ON messages (openwa_message_id)"))
                        except Exception:
                            pass
        except Exception as e:
            app.logger.warning(f"Note de migration de base de données : {e}")

        db.create_all()
        # Initialise le singleton AIConfig
        AIConfig.get_config()
