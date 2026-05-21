import logging
import requests
from flask import current_app
from database import db, AIConfig, Message

logger = logging.getLogger(__name__)

def get_whatsapp_credentials():
    """Récupère les identifiants depuis la BDD (AIConfig) ou à défaut depuis la config Flask."""
    try:
        config = AIConfig.get_config()
        token = config.whatsapp_token or current_app.config.get('WHATSAPP_TOKEN', '')
        phone_id = config.phone_number_id or current_app.config.get('PHONE_NUMBER_ID', '')
        return token.strip(), phone_id.strip()
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des identifiants WhatsApp: {e}")
        return current_app.config.get('WHATSAPP_TOKEN', ''), current_app.config.get('PHONE_NUMBER_ID', '')

def clean_phone_for_meta(phone):
    """
    Nettoie le numéro pour l'API Meta Cloud (uniquement les chiffres, pas de '+').
    Le numéro en BDD est au format E.164 (ex: +33612345678).
    """
    if not phone:
        return ""
    return "".join(c for c in str(phone) if c.isdigit())

def send_whatsapp_message(contact, message_text):
    """
    Envoie un message WhatsApp via l'API Cloud de Meta.
    Enregistre ou met à jour le statut du message en BDD.
    
    :param contact: Instance du modèle Contact
    :param message_text: Contenu texte du message
    :return: (success_bool, message_id_or_error_message)
    """
    if contact.opted_out:
        logger.warning(f"Tentative d'envoi à un contact opt-out: {contact.phone}")
        return False, "Le contact s'est désabonné (opt-out)"
        
    token, phone_number_id = get_whatsapp_credentials()
    
    if not token or not phone_number_id or token == 'EAA_PLACEHOLDER':
        logger.error("Identifiants WhatsApp Business manquants ou non configurés.")
        return False, "Identifiants WhatsApp manquants ou invalides"

    cleaned_phone = clean_phone_for_meta(contact.phone)
    url = f"https://graph.facebook.com/v18.0/{phone_number_id}/messages"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messaging_product": "whatsapp",
        "to": cleaned_phone,
        "type": "text",
        "text": {
            "body": message_text
        }
    }

    # Création initiale du message en BDD avec statut 'pending'
    new_message = Message(
        contact_id=contact.id,
        direction="out",
        content=message_text,
        status="pending"
    )
    db.session.add(new_message)
    db.session.commit()

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response_data = response.json()
        
        if response.status_code == 200:
            # Succès d'envoi
            meta_msg_id = response_data.get('messages', [{}])[0].get('id', 'unknown')
            new_message.status = "sent"
            new_message.meta_message_id = meta_msg_id
            db.session.commit()
            logger.info(f"Message envoyé avec succès à {contact.phone}. Meta ID: {meta_msg_id}")
            return True, meta_msg_id
        else:
            # Erreur renvoyée par Meta
            error_details = response_data.get('error', {}).get('message', 'Erreur inconnue')
            new_message.status = "failed"
            db.session.commit()
            logger.error(f"Erreur API Meta WhatsApp ({response.status_code}): {error_details}")
            return False, error_details
            
    except requests.exceptions.RequestException as e:
        # Erreur réseau ou timeout
        new_message.status = "failed"
        db.session.commit()
        logger.error(f"Erreur réseau lors de l'envoi WhatsApp à {contact.phone}: {e}")
        return False, str(e)

def test_whatsapp_connection():
    """
    Vérifie la validité du Token et du Phone Number ID en interrogeant
    le profil du numéro de téléphone sur le Graph API (sans envoyer de message).
    """
    token, phone_number_id = get_whatsapp_credentials()
    if not token or not phone_number_id or token == 'EAA_PLACEHOLDER':
        return False, "Identifiants non saisis ou configurés par défaut."
        
    url = f"https://graph.facebook.com/v18.0/{phone_number_id}"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response_data = response.json()
        if response.status_code == 200:
            verified_name = response_data.get('verified_name', 'Numéro WhatsApp Business')
            return True, f"Connexion réussie ! Compte validé : {verified_name}"
        else:
            error_msg = response_data.get('error', {}).get('message', 'Erreur d\'autorisation Meta')
            return False, f"Erreur de connexion ({response.status_code}) : {error_msg}"
    except Exception as e:
        return False, f"Exception de connexion : {str(e)}"
