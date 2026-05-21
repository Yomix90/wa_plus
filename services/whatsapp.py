import logging
import requests
from flask import current_app
from database import db, AIConfig, Message

logger = logging.getLogger(__name__)

def get_whatsapp_credentials():
    """Récupère les identifiants OpenWA depuis la BDD (AIConfig) ou à défaut depuis la config Flask."""
    try:
        config = AIConfig.get_config()
        api_url = config.openwa_api_url or current_app.config.get('OPENWA_API_URL', 'https://openwa-waplus-hmvwgl-24722a-51-210-177-24.sslip.io')
        api_key = config.openwa_api_key or current_app.config.get('OPENWA_API_KEY', '')
        session_id = config.openwa_session_id or current_app.config.get('OPENWA_SESSION_ID', 'default')
        
        # S'assurer que l'URL ne se termine pas par un slash
        api_url = api_url.strip().rstrip('/')
        return api_url, api_key.strip(), session_id.strip()
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des identifiants OpenWA: {e}")
        return (
            current_app.config.get('OPENWA_API_URL', 'https://openwa-waplus-hmvwgl-24722a-51-210-177-24.sslip.io').rstrip('/'),
            current_app.config.get('OPENWA_API_KEY', ''),
            current_app.config.get('OPENWA_SESSION_ID', 'default')
        )

def clean_phone_for_openwa(phone):
    """
    Nettoie le numéro pour OpenWA (uniquement les chiffres, suivi de @c.us).
    Le numéro en BDD est au format E.164 (ex: +33612345678).
    """
    if not phone:
        return ""
    # Ne garder que les chiffres
    digits = "".join(c for c in str(phone) if c.isdigit())
    if not digits.endswith("@c.us"):
        return f"{digits}@c.us"
    return digits

def send_whatsapp_message(contact, message_text):
    """
    Envoie un message WhatsApp via la passerelle OpenWA.
    Enregistre ou met à jour le statut du message en BDD.
    
    :param contact: Instance du modèle Contact
    :param message_text: Contenu texte du message
    :return: (success_bool, message_id_or_error_message)
    """
    if contact.opted_out:
        logger.warning(f"Tentative d'envoi à un contact opt-out: {contact.phone}")
        return False, "Le contact s'est désabonné (opt-out)"
        
    api_url, api_key, session_id = get_whatsapp_credentials()
    
    if not api_url:
        logger.error("URL de l'API OpenWA manquante.")
        return False, "URL de l'API OpenWA manquante"

    cleaned_phone = clean_phone_for_openwa(contact.phone)
    url = f"{api_url}/api/sessions/{session_id}/messages/send-text"
    
    headers = {
        "Content-Type": "application/json"
    }
    if api_key:
        headers["X-API-Key"] = api_key
    
    payload = {
        "chatId": cleaned_phone,
        "text": message_text
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
        logger.info(f"Envoi du message à OpenWA : {url}")
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        
        try:
            response_data = response.json()
        except ValueError:
            new_message.status = "failed"
            db.session.commit()
            logger.error(f"La passerelle OpenWA a retourné une réponse non-JSON (Code HTTP {response.status_code})")
            return False, f"Réponse non-JSON de la passerelle (Code HTTP {response.status_code})"
        
        # D'après la spécification OpenWA, la réponse est au format { "success": true, "data": { "id": "..." } }
        if response.status_code in (200, 201) and response_data.get('success'):
            # Succès d'envoi
            msg_data = response_data.get('data', {})
            openwa_msg_id = msg_data.get('id') if isinstance(msg_data, dict) else 'unknown'
            new_message.status = "sent"
            new_message.openwa_message_id = openwa_msg_id
            db.session.commit()
            logger.info(f"Message envoyé avec succès via OpenWA à {contact.phone}. Message ID: {openwa_msg_id}")
            return True, openwa_msg_id
        else:
            # Erreur renvoyée par OpenWA
            error_details = response_data.get('error', {}).get('message', 'Erreur de la passerelle OpenWA')
            new_message.status = "failed"
            db.session.commit()
            logger.error(f"Erreur API OpenWA ({response.status_code}): {error_details}")
            return False, error_details
            
    except requests.exceptions.RequestException as e:
        # Erreur réseau ou timeout
        new_message.status = "failed"
        db.session.commit()
        logger.error(f"Erreur réseau lors de l'envoi OpenWA à {contact.phone}: {e}")
        return False, str(e)

def test_whatsapp_connection():
    """
    Vérifie la connexion à la passerelle OpenWA et le statut de la session.
    """
    api_url, api_key, session_id = get_whatsapp_credentials()
    if not api_url:
        return False, "URL de l'API OpenWA non configurée."
        
    url = f"{api_url}/api/sessions/{session_id}"
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    
    try:
        logger.info(f"Vérification de la connexion OpenWA sur : {url}")
        response = requests.get(url, headers=headers, timeout=10)
        
        try:
            response_data = response.json()
        except ValueError:
            return False, f"La passerelle OpenWA a retourné une réponse non-JSON (Code HTTP {response.status_code}). Veuillez vérifier l'URL de votre instance."
        
        if response.status_code == 200 and response_data.get('success'):
            status_data = response_data.get('data', {})
            session_status = status_data.get('status', 'unknown')
            return True, f"Connexion à OpenWA réussie ! Statut de la session '{session_id}' : {session_status}"
        else:
            error_msg = response_data.get('error', {}).get('message', 'Erreur d\'autorisation OpenWA')
            if response.status_code == 401:
                error_msg = "Clé d'API (X-API-Key) invalide ou manquante."
            elif response.status_code == 404:
                error_msg = f"La session '{session_id}' n'a pas été trouvée sur l'instance."
            return False, f"Erreur de connexion ({response.status_code}) : {error_msg}"
    except Exception as e:
        return False, f"Exception de connexion à OpenWA : {str(e)}"
