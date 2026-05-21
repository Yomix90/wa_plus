import csv
import io
import logging
from flask import Blueprint, request, jsonify
from database import db, Contact

logger = logging.getLogger(__name__)
contacts_bp = Blueprint('contacts', __name__)

def normalize_phone_e164(phone_str):
    """
    Normalise un numéro de téléphone au format E.164 (+33612345678).
    Nettoie les espaces, tirets et s'assure de la présence du préfixe +.
    """
    if not phone_str:
        return None
        
    # Conserver uniquement les chiffres et le signe '+'
    cleaned = "".join(c for c in str(phone_str) if c.isdigit() or c == '+')
    
    if not cleaned:
        return None
        
    # Gérer le cas du double zéro international (0033... -> +33...)
    if cleaned.startswith('00'):
        cleaned = '+' + cleaned[2:]
        
    # Si le numéro commence par un chiffre sans '+', on ajoute '+'
    # (En supposant que l'utilisateur a saisi l'indicatif pays comme 336...)
    if not cleaned.startswith('+'):
        # Si le numéro commence par un '0' local (ex: 0612345678 en France),
        # par sécurité, on le conserve mais on recommande la notation internationale.
        # Idéalement, les utilisateurs importent au format E.164 direct.
        # On ajoute le '+' devant par défaut.
        cleaned = '+' + cleaned
        
    return cleaned

@contacts_bp.route('/contacts', methods=['GET'])
def get_contacts():
    """
    Retourne la liste des contacts paginée avec recherche et filtres.
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 15, type=int)
    search = request.args.get('search', '')
    group_tag = request.args.get('group_tag', '')
    opt_filter = request.args.get('opted_out', '') # 'true' ou 'false'
    
    query = Contact.query
    
    if search:
        query = query.filter(
            (Contact.name.like(f"%{search}%")) |
            (Contact.phone.like(f"%{search}%"))
        )
    if group_tag:
        query = query.filter(Contact.group_tag == group_tag)
    if opt_filter:
        opt_bool = opt_filter.lower() == 'true'
        query = query.filter(Contact.opted_out == opt_bool)
        
    pagination = query.order_by(Contact.name.asc()).paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        "contacts": [c.to_dict() for c in pagination.items],
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": pagination.page
    })

@contacts_bp.route('/contacts', methods=['POST'])
def create_contact():
    """
    Crée un nouveau contact.
    """
    data = request.get_json() or {}
    name = data.get('name')
    phone_raw = data.get('phone')
    group_tag = data.get('group_tag', 'Prospect')
    
    if not phone_raw:
        return jsonify({"error": "Le numéro de téléphone est obligatoire"}), 400
        
    phone = normalize_phone_e164(phone_raw)
    if not phone:
        return jsonify({"error": "Numéro de téléphone invalide"}), 400
        
    # Vérifier l'unicité
    existing = Contact.query.filter_by(phone=phone).first()
    if existing:
        return jsonify({"error": f"Un contact existe déjà avec le numéro {phone}"}), 400
        
    contact = Contact(
        name=name or "Sans nom",
        phone=phone,
        group_tag=group_tag,
        opted_out=False
    )
    
    try:
        db.session.add(contact)
        db.session.commit()
        return jsonify(contact.to_dict()), 211
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Erreur lors de la création : {str(e)}"}), 500

@contacts_bp.route('/contacts/<int:contact_id>', methods=['PUT'])
def update_contact(contact_id):
    """
    Met à jour un contact existant.
    """
    contact = Contact.query.get_or_404(contact_id)
    data = request.get_json() or {}
    
    name = data.get('name')
    phone_raw = data.get('phone')
    group_tag = data.get('group_tag')
    opted_out = data.get('opted_out')
    
    if name is not None:
        contact.name = name
    if group_tag is not None:
        contact.group_tag = group_tag
    if opted_out is not None:
        contact.opted_out = bool(opted_out)
        
    if phone_raw:
        phone = normalize_phone_e164(phone_raw)
        if not phone:
            return jsonify({"error": "Numéro de téléphone invalide"}), 400
        # Vérifier l'unicité si modifié
        if phone != contact.phone:
            existing = Contact.query.filter_by(phone=phone).first()
            if existing:
                return jsonify({"error": f"Un autre contact utilise déjà le numéro {phone}"}), 400
            contact.phone = phone
            
    try:
        db.session.commit()
        return jsonify(contact.to_dict())
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Erreur lors de la mise à jour : {str(e)}"}), 500

@contacts_bp.route('/contacts/<int:contact_id>', methods=['DELETE'])
def delete_contact(contact_id):
    """
    Supprime un contact (les messages associés sont supprimés en cascade).
    """
    contact = Contact.query.get_or_404(contact_id)
    try:
        db.session.delete(contact)
        db.session.commit()
        return jsonify({"success": True, "message": "Contact supprimé avec succès."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Erreur lors de la suppression : {str(e)}"}), 500

@contacts_bp.route('/contacts/toggle-optout/<int:contact_id>', methods=['POST'])
def toggle_contact_optout(contact_id):
    """
    Alterne l'état d'opt-out du contact.
    """
    contact = Contact.query.get_or_404(contact_id)
    contact.opted_out = not contact.opted_out
    try:
        db.session.commit()
        status = "désabonné" if contact.opted_out else "réabonné"
        return jsonify({
            "success": True, 
            "opted_out": contact.opted_out, 
            "message": f"Le contact a été {status} avec succès."
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@contacts_bp.route('/contacts/groups', methods=['GET'])
def get_contact_groups():
    """
    Renvoie la liste de tous les groupes (tags) distincts.
    """
    # Récupérer les tags de groupe uniques non vides
    groups = db.session.query(Contact.group_tag).distinct().all()
    group_list = [g[0] for g in groups if g[0]]
    # S'assurer d'avoir au moins le tag par défaut
    if not group_list:
        group_list = ["Prospect", "Client", "Nouveau"]
    return jsonify(list(set(group_list)))

@contacts_bp.route('/contacts/import', methods=['POST'])
def import_contacts_csv():
    """
    Importe des contacts depuis un fichier CSV.
    Attend un payload multipart form avec un fichier 'file'.
    Le CSV doit contenir une colonne 'phone' (obligatoire). 'name' et 'group' sont optionnels.
    Délimiteurs tolérés : virgule ou point-virgule.
    """
    if 'file' not in request.files:
        return jsonify({"error": "Aucun fichier téléversé"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Aucun fichier sélectionné"}), 400
        
    if not file.filename.endswith('.csv'):
        return jsonify({"error": "Seuls les fichiers CSV sont acceptés"}), 400

    try:
        # Lire le fichier dans un stream texte
        stream = io.StringIO(file.stream.read().decode("utf-8"), newline=None)
        
        # Détection du délimiteur (virgule ou point-virgule)
        first_line = stream.readline()
        delimiter = ';' if ';' in first_line else ','
        stream.seek(0) # Revenir au début
        
        reader = csv.DictReader(stream, delimiter=delimiter)
        
        # Nettoyage des headers (supprimer espaces et forcer minuscules)
        reader.fieldnames = [field.strip().lower() for field in reader.fieldnames]
        
        # Vérifier si la colonne obligatoire 'phone' existe (ou 'téléphone' / 'telephone')
        phone_col = None
        for col in ['phone', 'telephone', 'téléphone', 'tel']:
            if col in reader.fieldnames:
                phone_col = col
                break
                
        if not phone_col:
            return jsonify({"error": "Le fichier CSV doit contenir une colonne nommée 'phone' (ou 'telephone')."}), 400
            
        # Trouver les autres colonnes optionnelles
        name_col = None
        for col in ['name', 'nom', 'prenom', 'prénom']:
            if col in reader.fieldnames:
                name_col = col
                break
                
        group_col = None
        for col in ['group', 'groupe', 'group_tag', 'tag']:
            if col in reader.fieldnames:
                group_col = col
                break

        imported_count = 0
        updated_count = 0
        failed_count = 0
        errors = []
        
        for idx, row in enumerate(reader, start=1):
            phone_raw = row.get(phone_col)
            if not phone_raw:
                failed_count += 1
                errors.append(f"Ligne {idx} : Numéro de téléphone vide.")
                continue
                
            phone = normalize_phone_e164(phone_raw)
            if not phone:
                failed_count += 1
                errors.append(f"Ligne {idx} : Numéro de téléphone invalide '{phone_raw}'.")
                continue
                
            name = row.get(name_col, "").strip() if name_col else "Contact Importé"
            if not name:
                name = "Sans nom"
                
            group_tag = row.get(group_col, "Importé").strip() if group_col else "Importé"
            if not group_tag:
                group_tag = "Importé"

            # Recherche d'un doublon pour faire un Upsert (mise à jour)
            contact = Contact.query.filter_by(phone=phone).first()
            if contact:
                # Mise à jour
                contact.name = name
                contact.group_tag = group_tag
                updated_count += 1
            else:
                # Création
                contact = Contact(
                    name=name,
                    phone=phone,
                    group_tag=group_tag,
                    opted_out=False
                )
                db.session.add(contact)
                imported_count += 1
                
        db.session.commit()
        logger.info(f"Import CSV terminé: {imported_count} importés, {updated_count} mis à jour, {failed_count} échoués.")
        
        return jsonify({
            "success": True,
            "imported": imported_count,
            "updated": updated_count,
            "failed": failed_count,
            "errors": errors[:50] # Limiter la taille des erreurs renvoyées
        })
        
    except Exception as e:
        logger.error(f"Erreur lors de l'import CSV: {e}")
        return jsonify({"error": f"Erreur lors de la lecture du fichier CSV : {str(e)}"}), 500
