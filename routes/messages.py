import csv
import io
import time
import logging
import threading
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, Response, make_response
from database import db, Contact, Message, Campaign
from services.whatsapp import send_whatsapp_message

logger = logging.getLogger(__name__)
messages_bp = Blueprint('messages', __name__)

# Structure globale thread-safe pour suivre l'avancement des campagnes en direct
CAMPAIGN_PROGRESS = {}
progress_lock = threading.Lock()

def process_immediate_campaign(campaign_id, contacts_ids):
    """
    Exécute la campagne de messagerie en arrière-plan et met à jour l'état de progression.
    """
    with progress_lock:
        CAMPAIGN_PROGRESS[campaign_id] = {
            "current": 0,
            "total": len(contacts_ids),
            "status": "sending",
            "percent": 0,
            "contact_name": ""
        }
        
    # Importer l'application Flask courante pour avoir accès au contexte de la BDD
    from app import flask_app
    
    with flask_app.app_context():
        campaign = Campaign.query.get(campaign_id)
        if not campaign:
            return
            
        success_count = 0
        total_contacts = len(contacts_ids)
        
        for idx, contact_id in enumerate(contacts_ids):
            contact = Contact.query.get(contact_id)
            if contact and not contact.opted_out:
                # Mise à jour du nom du contact en cours de traitement
                with progress_lock:
                    CAMPAIGN_PROGRESS[campaign_id]["contact_name"] = f"{contact.name or 'Inconnu'} ({contact.phone})"
                    CAMPAIGN_PROGRESS[campaign_id]["current"] = idx + 1
                    CAMPAIGN_PROGRESS[campaign_id]["percent"] = int(((idx + 1) / total_contacts) * 100)
                
                success, response = send_whatsapp_message(contact, campaign.template)
                if success:
                    success_count += 1
                
                # Attendre 1 seconde entre chaque envoi pour respecter les limites (rate limiting)
                time.sleep(1.0)
                
        # Fin de la campagne
        campaign.status = "sent"
        db.session.commit()
        
        with progress_lock:
            CAMPAIGN_PROGRESS[campaign_id]["status"] = "completed"
            CAMPAIGN_PROGRESS[campaign_id]["contact_name"] = "Terminé !"
            CAMPAIGN_PROGRESS[campaign_id]["percent"] = 100

@messages_bp.route('/messages/bulk', methods=['POST'])
def send_bulk_messages():
    """
    Crée une campagne d'envoi en masse immédiate ou planifiée.
    JSON : {
        "name": "Campagne Relance",
        "message": "Bonjour...",
        "target_type": "all" | "group" | "manual",
        "target_group": "Prospects" (si target_type = group),
        "contacts": [1, 2, 3] (si target_type = manual),
        "scheduled_at": "2026-05-21T19:30:00" | null
    }
    """
    data = request.get_json()
    if not data or not data.get('message') or not data.get('name'):
        return jsonify({"error": "Nom de campagne et message requis"}), 400
        
    campaign_name = data.get('name')
    template = data.get('message')
    target_type = data.get('target_type', 'all')
    target_group = data.get('target_group')
    selected_contacts = data.get('contacts', [])
    scheduled_at_str = data.get('scheduled_at')
    
    # Résolution de la date de planification si fournie
    scheduled_at = None
    if scheduled_at_str:
        try:
            # Attend le format ISO (ex: 2026-05-21T19:30:00)
            scheduled_at = datetime.fromisoformat(scheduled_at_str)
        except ValueError:
            return jsonify({"error": "Format de date invalide (ISO requis)"}), 400

    # Cibler les contacts admissibles (non désabonnés)
    if target_type == 'all':
        contacts = Contact.query.filter_by(opted_out=False).all()
        campaign_target = 'all'
    elif target_type == 'group':
        if not target_group:
            return jsonify({"error": "Nom du groupe requis"}), 400
        contacts = Contact.query.filter_by(group_tag=target_group, opted_out=False).all()
        campaign_target = target_group
    else: # manual selection
        if not selected_contacts:
            return jsonify({"error": "Sélection de contacts requise"}), 400
        contacts = Contact.query.filter(Contact.id.in_(selected_contacts), Contact.opted_out == False).all()
        campaign_target = 'selection'
        
    if not contacts:
        return jsonify({"error": "Aucun contact éligible ciblé"}), 400

    # Création du modèle de campagne
    campaign = Campaign(
        name=campaign_name,
        template=template,
        target_group=campaign_target,
        scheduled_at=scheduled_at,
        status='pending'
    )
    db.session.add(campaign)
    db.session.commit()

    # Si c'est planifié dans le futur
    if scheduled_at and scheduled_at > datetime.utcnow():
        return jsonify({
            "success": True,
            "message": f"Campagne planifiée avec succès pour le {scheduled_at.isoformat()}",
            "campaign_id": campaign.id,
            "scheduled": True
        })
        
    # Sinon envoi immédiat en arrière-plan
    contacts_ids = [c.id for c in contacts]
    thread = threading.Thread(
        target=process_immediate_campaign,
        args=(campaign.id, contacts_ids)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "success": True,
        "message": "Campagne démarrée en arrière-plan.",
        "campaign_id": campaign.id,
        "scheduled": False
    })

@messages_bp.route('/messages/progress/<int:campaign_id>', methods=['GET'])
def get_campaign_progress(campaign_id):
    """
    Flux Server-Sent Events (SSE) pour suivre la progression de l'envoi en direct.
    """
    def generate_events():
        while True:
            with progress_lock:
                progress = CAMPAIGN_PROGRESS.get(campaign_id)
                
            if not progress:
                # Si pas encore dans la map ou déjà terminé/nettoyé
                yield f"data: {{\"status\": \"searching\", \"percent\": 0}}\n\n"
                time.sleep(1)
                continue
                
            yield f"data: {{\"current\": {progress['current']}, \"total\": {progress['total']}, \"percent\": {progress['percent']}, \"status\": \"{progress['status']}\", \"contact\": \"{progress['contact_name']}\"}}\n\n"
            
            if progress['status'] == 'completed':
                # Supprimer les ressources de suivi après la fin
                with progress_lock:
                    CAMPAIGN_PROGRESS.pop(campaign_id, None)
                break
                
            time.sleep(0.5)
            
    return Response(generate_events(), mimetype='text/event-stream')

@messages_bp.route('/messages/history', methods=['GET'])
def get_messages_history():
    """
    Retourne la liste des messages filtrée et paginée.
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    direction = request.args.get('direction') # 'in' ou 'out'
    status = request.args.get('status')
    search = request.args.get('search') # nom ou numéro
    
    query = Message.query.join(Contact)
    
    if direction:
        query = query.filter(Message.direction == direction)
    if status:
        query = query.filter(Message.status == status)
    if search:
        query = query.filter(
            (Contact.name.like(f"%{search}%")) | 
            (Contact.phone.like(f"%{search}%")) |
            (Message.content.like(f"%{search}%"))
        )
        
    pagination = query.order_by(Message.sent_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        "messages": [msg.to_dict() for msg in pagination.items],
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": pagination.page
    })

@messages_bp.route('/messages/stats', methods=['GET'])
def get_dashboard_stats():
    """
    Calcule et renvoie les indicateurs clés (KPI) pour le Dashboard.
    """
    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    
    # Messages envoyés dans les dernières 24h
    sent_24h = Message.query.filter(
        Message.direction == 'out',
        Message.sent_at >= last_24h,
        Message.status != 'failed'
    ).count()
    
    # Messages reçus dans les dernières 24h
    received_24h = Message.query.filter(
        Message.direction == 'in',
        Message.sent_at >= last_24h
    ).count()
    
    # Calcul du taux de réponse (combien de contacts uniques ont envoyé 'in' par rapport à 'out')
    total_sent = Message.query.filter_by(direction='out').count()
    total_received = Message.query.filter_by(direction='in').count()
    
    response_rate = 0
    if total_sent > 0:
        response_rate = round((total_received / total_sent) * 100, 1)
        
    # Campagnes en attente actives
    active_campaigns = Campaign.query.filter_by(status='pending').count()
    
    # Liste des dernières conversations actives (groupées par contact, triées par date)
    subquery = db.session.query(
        Message.contact_id,
        db.func.max(Message.sent_at).label('max_sent_at')
    ).group_by(Message.contact_id).subquery()
    
    latest_messages = Message.query.join(
        subquery,
        (Message.contact_id == subquery.c.contact_id) & (Message.sent_at == subquery.c.max_sent_at)
    ).order_by(Message.sent_at.desc()).limit(5).all()
    
    return jsonify({
        "sent_24h": sent_24h,
        "received_24h": received_24h,
        "response_rate": f"{response_rate}%",
        "active_campaigns": active_campaigns,
        "latest_conversations": [msg.to_dict() for msg in latest_messages]
    })

@messages_bp.route('/messages/export', methods=['GET'])
def export_messages_csv():
    """
    Génère et renvoie un fichier CSV de l'historique complet des messages.
    """
    messages = Message.query.join(Contact).order_by(Message.sent_at.desc()).all()
    
    # Création d'un buffer en mémoire
    si = io.StringIO()
    cw = csv.writer(si)
    
    # Header
    cw.writerow(['ID Message', 'Nom Contact', 'Numéro de Téléphone', 'Direction', 'Contenu', 'Statut', 'Date d\'envoi'])
    
    for msg in messages:
        direction_label = "Reçu" if msg.direction == "in" else "Envoyé"
        cw.writerow([
            msg.id,
            msg.contact.name if msg.contact else 'Inconnu',
            msg.contact.phone if msg.contact else '',
            direction_label,
            msg.content,
            msg.status,
            msg.sent_at.strftime('%Y-%m-%d %H:%M:%S')
        ])
        
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=historique_messages.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8"
    return output
