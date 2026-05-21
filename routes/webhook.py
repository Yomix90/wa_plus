import os
import hmac
import hashlib
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from database import db, Contact, Message, AIConfig
from services.whatsapp import send_whatsapp_message
from services.gemini import generate_reply

logger = logging.getLogger(__name__)
webhook_bp = Blueprint('webhook', __name__)

def verify_signature(raw_body, signature_header):
    """
    Valide la signature HMAC SHA-256 de Meta si WEBHOOK_APP_SECRET est configuré.
    Si non configuré, laisse passer avec un avertissement (facilite le dev/test).
    """
    app_secret = os.environ.get('WEBHOOK_APP_SECRET') or current_app.config.get('SECRET_KEY')
    # Si l'utilisateur n'a pas défini de secret d'application de production, on bypass en loggant
    if not app_secret or app_secret.startswith('cle_flask_par_defaut'):
        logger.warning("Bypass de la signature X-Hub-Signature-256 en mode développement (SECRET_KEY par défaut).")
        return True
        
    if not signature_header or not signature_header.startswith('sha256='):
        logger.error("En-tête X-Hub-Signature-256 manquant ou invalide.")
        return False
        
    signature = signature_header.split('sha256=')[-1]
    expected_signature = hmac.new(
        app_secret.encode('utf-8'),
        raw_body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)

@webhook_bp.route('/webhook', methods=['GET'])
def verify_webhook():
    """
    Endpoint requis par Meta pour valider le webhook lors de la configuration.
    Exemple de paramètres GET reçus :
    ?hub.mode=subscribe&hub.challenge=1158201444&hub.verify_token=mon_token_secret
    """
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    
    config = AIConfig.get_config()
    expected_token = config.webhook_verify_token or current_app.config.get('WEBHOOK_VERIFY_TOKEN', '')
    
    if mode and token:
        if mode == 'subscribe' and token == expected_token:
            logger.info("Webhook WhatsApp Business validé par Meta avec succès !")
            return challenge, 200
        else:
            logger.warning(f"Échec de validation du Webhook. Token reçu: {token}, attendu: {expected_token}")
            return "Forbidden", 403
            
    return "Mauvaise requête", 400

@webhook_bp.route('/webhook', methods=['POST'])
def handle_webhook_event():
    """
    Réception des événements de messages et statuts envoyés par Meta.
    """
    raw_body = request.data
    signature = request.headers.get('X-Hub-Signature-256')
    
    # Validation de la signature pour la sécurité
    if not verify_signature(raw_body, signature):
        logger.warning("Signature de webhook invalide.")
        return jsonify({"status": "invalid signature"}), 401
        
    payload = request.get_json()
    logger.debug(f"Payload Webhook reçu: {payload}")
    
    if not payload:
        return jsonify({"status": "empty body"}), 400

    # Meta envoie les événements structurés sous forme d'entrées 'entry'
    for entry in payload.get('entry', []):
        for change in entry.get('changes', []):
            value = change.get('value', {})
            
            # 1. Gestion des messages entrants (Réception)
            if 'messages' in value:
                for msg in value.get('messages', []):
                    # Ignorer si ce n'est pas un message textuel
                    if msg.get('type') != 'text':
                        continue
                        
                    from_phone_raw = msg.get('from') # Ex: "33612345678"
                    # Mettre au format E.164 propre avec '+' pour la BDD
                    from_phone = f"+{from_phone_raw}" if not from_phone_raw.startswith('+') else from_phone_raw
                    message_text = msg.get('text', {}).get('body', '')
                    meta_msg_id = msg.get('id')
                    
                    # Récupération du profil de l'expéditeur
                    contacts_list = value.get('contacts', [])
                    sender_name = "Contact WhatsApp"
                    if contacts_list:
                        sender_name = contacts_list[0].get('profile', {}).get('name', 'Contact WhatsApp')
                        
                    # Recherche ou création du contact dans la base SQLite
                    contact = Contact.query.filter_by(phone=from_phone).first()
                    if not contact:
                        contact = Contact(
                            name=sender_name,
                            phone=from_phone,
                            group_tag="Nouveau",
                            opted_out=False
                        )
                        db.session.add(contact)
                        db.session.commit()
                        logger.info(f"Nouveau contact créé à la volée via Webhook: {sender_name} ({from_phone})")
                    
                    # Si le contact est désabonné (opted_out), on n'enregistre pas les messages et on n'auto-répond pas
                    if contact.opted_out:
                        logger.info(f"Message de {from_phone} ignoré car le contact est opt-out.")
                        continue
                        
                    # Enregistrement du message en BDD (direction = 'in')
                    new_msg = Message(
                        contact_id=contact.id,
                        direction="in",
                        content=message_text,
                        status="delivered",
                        meta_message_id=meta_msg_id,
                        sent_at=datetime.utcnow()
                    )
                    db.session.add(new_msg)
                    db.session.commit()
                    logger.info(f"Message entrant enregistré pour {contact.name}: {message_text}")
                    
                    # Traitement de l'Auto-Reply via Gemini
                    ai_config = AIConfig.get_config()
                    if ai_config.auto_reply_enabled:
                        # Générer la réponse automatique intelligente
                        ai_reply = generate_reply(contact.id, message_text)
                        
                        # Envoyer la réponse via WhatsApp
                        success, res = send_whatsapp_message(contact, ai_reply)
                        if success:
                            logger.info(f"Auto-reply envoyé à {contact.phone} via Gemini.")
                        else:
                            logger.error(f"Échec de l'envoi de l'auto-reply à {contact.phone} : {res}")
                            
            # 2. Gestion des mises à jour de statut (sent -> delivered -> read -> failed)
            elif 'statuses' in value:
                for status_event in value.get('statuses', []):
                    meta_msg_id = status_event.get('id')
                    new_status = status_event.get('status') # 'sent', 'delivered', 'read', 'failed'
                    
                    # Recherche du message par son identifiant Meta
                    msg = Message.query.filter_by(meta_message_id=meta_msg_id).first()
                    if msg:
                        msg.status = new_status
                        db.session.commit()
                        logger.info(f"Statut du message {meta_msg_id} mis à jour : {new_status}")
                    else:
                        logger.debug(f"Statut reçu pour un message non répertorié : {meta_msg_id} ({new_status})")
                        
    return jsonify({"status": "success"}), 200
