import time
import logging
from datetime import datetime
from flask_apscheduler import APScheduler
from database import db, Campaign, Contact
from services.whatsapp import send_whatsapp_message

logger = logging.getLogger(__name__)

# Jeton global du planificateur
scheduler = APScheduler()

def init_scheduler(app):
    """Initialise le planificateur avec l'application Flask."""
    if not scheduler.running:
        try:
            scheduler.init_app(app)
            scheduler.start()
            logger.info("Planificateur APScheduler démarré avec succès.")
        except Exception as e:
            logger.warning(f"Note lors du démarrage d'APScheduler: {e}")
    else:
        logger.info("Le Planificateur APScheduler est déjà en cours d'exécution.")
    
    # Ajouter la tâche récurrente toutes les 60 secondes s'il n'est pas déjà enregistré
    try:
        @scheduler.task('interval', id='check_campaigns_job', seconds=60, timezone="UTC")
        def check_campaigns_job():
            with app.app_context():
                check_pending_campaigns()
    except Exception:
        # Tâche déjà enregistrée
        pass

def check_pending_campaigns():
    """
    Vérifie les campagnes en attente et les traite si l'heure planifiée est atteinte.
    """
    now = datetime.utcnow()
    # Récupère toutes les campagnes 'pending' dont l'heure d'envoi est dépassée
    pending_campaigns = Campaign.query.filter(
        Campaign.status == 'pending',
        Campaign.scheduled_at <= now
    ).all()
    
    if not pending_campaigns:
        return
        
    logger.info(f"Détection de {len(pending_campaigns)} campagne(s) planifiée(s) à traiter.")
    
    for campaign in pending_campaigns:
        try:
            logger.info(f"Traitement de la campagne: {campaign.name} (ID: {campaign.id})")
            
            # Récupération des contacts ciblés
            if not campaign.target_group or campaign.target_group.lower() == 'all':
                # Tous les contacts non désabonnés
                contacts = Contact.query.filter_by(opted_out=False).all()
            else:
                # Contacts d'un groupe spécifique non désabonnés
                contacts = Contact.query.filter_by(
                    group_tag=campaign.target_group,
                    opted_out=False
                ).all()
                
            if not contacts:
                logger.warning(f"Aucun contact éligible trouvé pour la campagne {campaign.name}.")
                campaign.status = 'sent'  # Marqué comme traité même si vide
                db.session.commit()
                continue

            # Passage du statut à en cours / envoyé pour éviter les doubles traitements
            campaign.status = 'sent'
            db.session.commit()
            
            # Envoi individuel avec temporisation de 1 seconde (Rate limiting)
            success_count = 0
            for contact in contacts:
                success, response = send_whatsapp_message(contact, campaign.template)
                if success:
                    success_count += 1
                
                # Pause d'une seconde pour respecter le rate limit de l'API
                time.sleep(1.0)
                
            logger.info(f"Campagne {campaign.name} terminée. {success_count}/{len(contacts)} messages envoyés.")
            
        except Exception as e:
            logger.error(f"Erreur lors du traitement de la campagne {campaign.id}: {e}")
            campaign.status = 'failed'
            db.session.commit()
