import logging
import google.generativeai as genai
from flask import current_app
from database import AIConfig, Message, Contact

logger = logging.getLogger(__name__)

def get_gemini_api_key():
    """Récupère la clé API Gemini depuis la BDD (AIConfig) ou à défaut depuis la config Flask."""
    try:
        config = AIConfig.get_config()
        api_key = config.gemini_api_key or current_app.config.get('GEMINI_API_KEY', '')
        return api_key.strip()
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de la clé Gemini: {e}")
        return current_app.config.get('GEMINI_API_KEY', '')

def generate_reply(contact_id, incoming_message):
    """
    Génère une réponse intelligente en utilisant Gemini 1.5 Flash.
    Prend en compte l'historique des 5 derniers messages avec le contact.
    
    :param contact_id: ID du contact dans la BDD
    :param incoming_message: Message texte entrant du contact
    :return: Texte de la réponse générée par l'IA
    """
    api_key = get_gemini_api_key()
    if not api_key or api_key == 'AIza_PLACEHOLDER':
        logger.error("Clé API Gemini manquante ou non configurée.")
        return "Désolé, l'assistant intelligent n'est pas configuré actuellement."

    try:
        # Récupération de la configuration d'IA
        config = AIConfig.get_config()
        system_prompt = config.system_prompt
        
        # Récupérer l'historique des 5 derniers messages avec ce contact (triés par date)
        # Exclure le message courant s'il a déjà été enregistré, pour éviter les doublons dans le prompt
        history_messages = Message.query.filter_by(contact_id=contact_id)\
            .order_by(Message.sent_at.desc())\
            .limit(5)\
            .all()
            
        # Les messages du plus ancien au plus récent
        history_messages.reverse()
        
        # Construction du contexte historique pour le prompt
        history_context = ""
        if history_messages:
            history_context = "\nHistorique récent de la conversation :\n"
            for msg in history_messages:
                role = "Client" if msg.direction == "in" else "Assistant (Toi)"
                history_context += f"- {role}: {msg.content}\n"
        
        # Configuration du client Gemini
        genai.configure(api_key=api_key)
        
        # Prompt enrichi
        prompt = (
            f"Tu discutes avec un client sur WhatsApp.{history_context}\n"
            f"Nouveau message du Client : \"{incoming_message}\"\n\n"
            f"Rédige ta réponse directe en français, sans préfixe (ne mets pas 'Assistant:' ni 'Réponse:'). "
            f"Sois naturel, courtois et synthétique."
        )
        
        # Boucle de repli (fallback) sur plusieurs modèles de génération
        model_names = ['gemini-1.5-flash', 'gemini-1.5-flash-latest', 'gemini-2.0-flash', 'gemini-pro']
        last_error = None
        
        for m_name in model_names:
            try:
                logger.info(f"Tentative d'appel à Gemini avec le modèle {m_name}...")
                model = genai.GenerativeModel(
                    model_name=m_name,
                    system_instruction=system_prompt
                )
                response = model.generate_content(prompt)
                
                if response and response.text:
                    reply_text = response.text.strip()
                    # Nettoyer d'éventuels résidus ou préfixes
                    if reply_text.startswith("Assistant:"):
                        reply_text = reply_text.replace("Assistant:", "", 1).strip()
                    logger.info(f"Réponse générée avec succès via {m_name} !")
                    return reply_text
            except Exception as e:
                logger.warning(f"Le modèle {m_name} a échoué: {e}")
                last_error = str(e)
                continue
                
        # Si aucun modèle n'a fonctionné
        logger.error(f"Tous les modèles Gemini ont échoué. Dernière erreur: {last_error}")
        return "Désolé, je n'ai pas pu formuler de réponse suite à une contrainte technique."
            
    except Exception as e:
        logger.error(f"Erreur lors de la génération de réponse Gemini: {e}")
        return "Désolé, j'ai rencontré une erreur en formulant ma réponse."

def test_gemini_connection(test_prompt="Bonjour, fais un test court."):
    """
    Vérifie la validité de la clé API Gemini en envoyant une requête simple avec boucle de repli.
    """
    api_key = get_gemini_api_key()
    if not api_key or api_key == 'AIza_PLACEHOLDER':
        return False, "La clé API Gemini n'est pas configurée ou est par défaut."
        
    model_names = ['gemini-1.5-flash', 'gemini-1.5-flash-latest', 'gemini-2.0-flash', 'gemini-pro']
    last_error = None
    
    for m_name in model_names:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name=m_name)
            response = model.generate_content(test_prompt)
            if response and response.text:
                return True, f"Connexion Gemini réussie avec le modèle '{m_name}' ! Réponse test : {response.text.strip()}"
        except Exception as e:
            logger.warning(f"Le modèle de test {m_name} a échoué: {e}")
            last_error = str(e)
            continue
            
    return False, f"Erreur de connexion Gemini (Tous les modèles ont échoué). Dernière erreur : {last_error}"
