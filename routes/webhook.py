import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from database import db, Contact, Message, AIConfig
from services.whatsapp import send_whatsapp_message
from services.gemini import generate_reply

logger = logging.getLogger(__name__)
webhook_bp = Blueprint('webhook', __name__)

@webhook_bp.route('/webhook', methods=['GET'])
def verify_webhook():
    """
    Endpoint GET de diagnostic simple pour le webhook OpenWA.
    Permet de s'assurer rapidement que la route est active et répond correctement.
    """
    return "Webhook WaPlus (OpenWA Integration) est actif et opérationnel !", 200

@webhook_bp.route('/webhook', methods=['POST'])
def handle_webhook_event():
    """
    Réception des événements de messages et statuts envoyés par votre passerelle OpenWA.
    """
    payload = request.get_json()
    logger.debug(f"Payload Webhook OpenWA reçu: {payload}")
    
    if not payload:
        return jsonify({"status": "empty body"}), 400

    event_type = payload.get('event')
    
    # 1. Gestion des messages entrants (Réception)
    if event_type == 'message.received':
        data = payload.get('data', {})
        if not data:
            return jsonify({"status": "no data in payload"}), 200

        # On n'accepte que les messages de type chat / texte pour le traitement de l'IA
        msg_type = data.get('type')
        if msg_type not in ('chat', 'text', 'chat_text'):
            logger.info(f"Événement de type message non textuel ignoré ({msg_type}).")
            return jsonify({"status": "ignored non-text message"}), 200

        # Extraction du numéro de téléphone expéditeur (ex: "33612345678@c.us")
        from_raw = data.get('from', '')
        if not from_raw:
            return jsonify({"status": "missing sender phone"}), 200

        # Nettoyage pour la BDD : enlever @c.us et préfixer par '+' pour le format E.164
        clean_phone = from_raw.replace('@c.us', '')
        from_phone = f"+{clean_phone}" if not clean_phone.startswith('+') else clean_phone

        # Extraction du texte du message et de l'identifiant OpenWA
        message_text = data.get('body', '')
        openwa_msg_id = data.get('id', 'unknown')

        # Extraction du nom du profil de l'expéditeur
        sender_name = data.get('notifyName') or data.get('sender', {}).get('name') or "Contact WhatsApp"

        # Recherche ou création du contact dans la base SQLite de WaPlus
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
            logger.info(f"Nouveau contact créé via Webhook OpenWA: {sender_name} ({from_phone})")
        
        # Si le contact est désabonné (opted_out), on ignore le message
        if contact.opted_out:
            logger.info(f"Message de {from_phone} ignoré car le contact s'est désabonné (opt-out).")
            return jsonify({"status": "contact opted-out"}), 200
            
        # Enregistrement du message entrant en BDD (direction = 'in')
        new_msg = Message(
            contact_id=contact.id,
            direction="in",
            content=message_text,
            status="delivered",
            openwa_message_id=openwa_msg_id,
            sent_at=datetime.utcnow()
        )
        db.session.add(new_msg)
        db.session.commit()
        logger.info(f"Message entrant enregistré de {contact.name}: {message_text}")
        
        # Traitement de l'Auto-Reply via l'IA Gemini
        ai_config = AIConfig.get_config()
        if ai_config.auto_reply_enabled:
            # Générer la réponse intelligente avec le contexte historique
            ai_reply = generate_reply(contact.id, message_text)
            
            # Envoyer la réponse via la passerelle OpenWA
            success, res = send_whatsapp_message(contact, ai_reply)
            if success:
                logger.info(f"Auto-reply envoyé avec succès à {contact.phone} via Gemini.")
            else:
                logger.error(f"Échec de l'envoi de l'auto-reply à {contact.phone} : {res}")
                
    # 2. Gestion facultative des accusés de réception / lectures (si renvoyés par OpenWA)
    elif event_type in ('message.ack', 'message.status'):
        data = payload.get('data', {})
        if data:
            openwa_msg_id = data.get('id')
            # 1 = envoyé, 2 = distribué, 3 = lu, -1 = échec
            ack_val = data.get('ack')
            
            new_status = 'sent'
            if ack_val == 2:
                new_status = 'delivered'
            elif ack_val == 3:
                new_status = 'read'
            elif ack_val == -1:
                new_status = 'failed'
                
            msg = Message.query.filter_by(openwa_message_id=openwa_msg_id).first()
            if msg:
                msg.status = new_status
                db.session.commit()
                logger.info(f"Statut du message OpenWA {openwa_msg_id} mis à jour : {new_status}")

    return jsonify({"status": "success"}), 200
