import logging
from flask import Blueprint, request, jsonify
from database import db, AIConfig
from services.whatsapp import test_whatsapp_connection
from services.gemini import test_gemini_connection

logger = logging.getLogger(__name__)
ai_bp = Blueprint('ai', __name__)

def mask_credential(value, prefix_len=6, suffix_len=4):
    """
    Masque un token ou une clé API pour la sécurité d'affichage (ex: AIzaxxx...abcd).
    """
    if not value or value == 'EAA_PLACEHOLDER' or value == 'AIza_PLACEHOLDER':
        return ""
    if len(value) <= (prefix_len + suffix_len):
        return "********"
    return f"{value[:prefix_len]}...{value[-suffix_len:]}"

@ai_bp.route('/ai/config', methods=['GET'])
def get_ai_config():
    """
    Retourne la configuration active en masquant les clés sensibles.
    """
    config = AIConfig.get_config()
    
    return jsonify({
        "id": config.id,
        "system_prompt": config.system_prompt,
        "auto_reply_enabled": config.auto_reply_enabled,
        # Paramètres OpenWA
        "openwa_api_url": config.openwa_api_url or "",
        "openwa_api_key": mask_credential(config.openwa_api_key),
        "openwa_session_id": config.openwa_session_id or "",
        # Paramètres Gemini
        "gemini_api_key": mask_credential(config.gemini_api_key)
    })

@ai_bp.route('/ai/config', methods=['POST'])
def update_ai_config():
    """
    Met à jour la configuration de l'IA et les identifiants de la passerelle OpenWA.
    Intègre une sécurité : si les champs d'API renvoient la forme masquée
    (ex: contient '...'), on ne modifie pas la valeur existante en BDD.
    """
    data = request.get_json() or {}
    config = AIConfig.get_config()
    
    # 1. Mise à jour des bascules standards et prompts
    if 'system_prompt' in data:
        config.system_prompt = data.get('system_prompt', '').strip()
        
    if 'auto_reply_enabled' in data:
        config.auto_reply_enabled = bool(data.get('auto_reply_enabled'))
        
    # 2. Mise à jour sécurisée des variables OpenWA (sans écraser si masqué)
    openwa_api_url = data.get('openwa_api_url', '').strip()
    if openwa_api_url:
        config.openwa_api_url = openwa_api_url
        
    openwa_api_key = data.get('openwa_api_key', '').strip()
    if openwa_api_key and '...' not in openwa_api_key and '*' not in openwa_api_key:
        config.openwa_api_key = openwa_api_key
        
    openwa_session_id = data.get('openwa_session_id', '').strip()
    if openwa_session_id:
        config.openwa_session_id = openwa_session_id
        
    # 3. Mise à jour sécurisée de la clé Gemini
    gemini_api_key = data.get('gemini_api_key', '').strip()
    if gemini_api_key and '...' not in gemini_api_key and '*' not in gemini_api_key:
        config.gemini_api_key = gemini_api_key
        
    try:
        db.session.commit()
        return jsonify({
            "success": True,
            "message": "Configuration OpenWA et Gemini sauvegardée avec succès.",
            "config": {
                "auto_reply_enabled": config.auto_reply_enabled,
                "system_prompt": config.system_prompt,
                "openwa_api_url": config.openwa_api_url,
                "openwa_api_key": mask_credential(config.openwa_api_key),
                "openwa_session_id": config.openwa_session_id,
                "gemini_api_key": mask_credential(config.gemini_api_key)
            }
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erreur lors de la mise à jour d'AIConfig pour OpenWA: {e}")
        return jsonify({"error": f"Erreur de sauvegarde : {str(e)}"}), 500

@ai_bp.route('/ai/test-whatsapp', methods=['POST'])
def test_whatsapp_api():
    """
    Déclenche le ping test d'API OpenWA.
    """
    success, message = test_whatsapp_connection()
    return jsonify({
        "success": success,
        "message": message
    })

@ai_bp.route('/ai/test-gemini', methods=['POST'])
def test_gemini_api():
    """
    Déclenche le ping test de génération intelligente Gemini.
    """
    data = request.get_json() or {}
    test_prompt = data.get('prompt', 'Bonjour, ceci est un test de l\'application WaPlus.')
    
    success, message = test_gemini_connection(test_prompt)
    return jsonify({
        "success": success,
        "message": message
    })
