/* ═══════════════════════════════════════════════
   MOTEUR APPLICATIF WAPLUS — CORE ENGINE (JS)
   ═══════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {
    // Initialiser les icônes globales
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
    
    // Router simple basé sur la présence d'éléments spécifiques dans le DOM
    if (document.getElementById('dashboard-view')) {
        initDashboard();
    } else if (document.getElementById('contacts-view')) {
        initContacts();
    } else if (document.getElementById('send-bulk-view')) {
        initSendBulk();
    } else if (document.getElementById('history-view')) {
        initHistory();
    } else if (document.getElementById('settings-view')) {
        initSettings();
    }
});

/* ═══════════════════════════════════════════════
   SYSTÈME DE NOTIFICATIONS TOAST
   ═══════════════════════════════════════════════ */
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const iconName = type === 'success' ? 'check-circle' : 'alert-circle';
    toast.innerHTML = `
        <i data-lucide="${iconName}"></i>
        <span>${message}</span>
    `;
    
    container.appendChild(toast);
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }

    // Retirer le toast après 4 secondes avec animation
    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1) reverse forwards';
        toast.addEventListener('animationend', () => {
            toast.remove();
        });
    }, 4000);
}

/* ═══════════════════════════════════════════════
   FORMATAGE DES DATES (STYLE WHATSAPP)
   ═══════════════════════════════════════════════ */
function formatWhatsAppDate(isoString) {
    if (!isoString) return '';
    const date = new Date(isoString);
    const now = new Date();
    
    const isToday = date.toDateString() === now.toDateString();
    
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    const isYesterday = date.toDateString() === yesterday.toDateString();

    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const timeStr = `${hours}:${minutes}`;

    if (isToday) {
        return timeStr;
    } else if (isYesterday) {
        return `Hier à ${timeStr}`;
    } else {
        const day = String(date.getDate()).padStart(2, '0');
        const month = String(date.getMonth() + 1).padStart(2, '0');
        return `${day}/${month} à ${timeStr}`;
    }
}

/* ═══════════════════════════════════════════════
   MODULE 1 : TABLEAU DE BORD (DASHBOARD)
   ═══════════════════════════════════════════════ */
function initDashboard() {
    fetchDashboardStats();
    
    // Rafraîchir les statistiques toutes les 30 secondes automatiquement
    setInterval(fetchDashboardStats, 30000);
}

async function fetchDashboardStats() {
    try {
        const response = await fetch('/api/messages/stats');
        const data = await response.json();
        
        if (response.ok) {
            // Mettre à jour les KPIs
            document.getElementById('kpi-sent-24h').innerText = data.sent_24h;
            document.getElementById('kpi-received-24h').innerText = data.received_24h;
            document.getElementById('kpi-response-rate').innerText = data.response_rate;
            document.getElementById('kpi-active-campaigns').innerText = data.active_campaigns;
            
            // Mettre à jour le tableau des dernières conversations
            const tbody = document.getElementById('latest-conversations-tbody');
            if (tbody) {
                tbody.innerHTML = '';
                
                if (data.latest_conversations.length === 0) {
                    tbody.innerHTML = `
                        <tr>
                            <td colspan="4" style="text-align: center; color: var(--text-secondary); padding: 2rem;">
                                Aucune conversation active pour le moment.
                            </td>
                        </tr>
                    `;
                    return;
                }
                
                data.latest_conversations.forEach(msg => {
                    const directionBadge = msg.direction === 'in' 
                        ? '<span class="badge badge-success">Reçu</span>' 
                        : '<span class="badge badge-info">Envoyé</span>';
                        
                    const statusBadge = msg.direction === 'out' 
                        ? `<span class="badge badge-warning">${msg.status}</span>`
                        : '-';
                        
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td><strong>${msg.contact_name}</strong><br><small style="color: var(--text-muted)">${msg.contact_phone}</small></td>
                        <td>${directionBadge}</td>
                        <td style="max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${msg.content}</td>
                        <td>${formatWhatsAppDate(msg.sent_at)}</td>
                    `;
                    tbody.appendChild(tr);
                });
            }
        }
    } catch (error) {
        console.error("Erreur lors de la récupération des stats dashboard :", error);
    }
}

/* ═══════════════════════════════════════════════
   MODULE 2 : CONTACTS (CRUD, CSV IMPORT)
   ═══════════════════════════════════════════════ */
let currentContactsPage = 1;
let contactsSearchQuery = '';
let contactsGroupFilter = '';

function initContacts() {
    loadContactsList(1);
    loadContactGroups();
    
    // Recherche dynamique avec debouncing
    const searchInput = document.getElementById('contacts-search');
    let searchTimeout;
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                contactsSearchQuery = e.target.value;
                loadContactsList(1);
            }, 300);
        });
    }
    
    // Filtrage par groupe
    const groupSelect = document.getElementById('contacts-group-filter');
    if (groupSelect) {
        groupSelect.addEventListener('change', (e) => {
            contactsGroupFilter = e.target.value;
            loadContactsList(1);
        });
    }
    
    // Modal de création
    const openModalBtn = document.getElementById('btn-add-contact');
    const modal = document.getElementById('contact-modal');
    const closeModalBtn = document.getElementById('contact-modal-close');
    const cancelModalBtn = document.getElementById('contact-modal-cancel');
    const contactForm = document.getElementById('contact-form');
    
    if (openModalBtn && modal) {
        openModalBtn.addEventListener('click', () => {
            // Reset form
            contactForm.reset();
            document.getElementById('contact-id-field').value = '';
            document.getElementById('modal-title').innerText = "Ajouter un contact";
            modal.style.display = 'flex';
        });
    }
    
    const closeModal = () => { if(modal) modal.style.display = 'none'; };
    if (closeModalBtn) closeModalBtn.addEventListener('click', closeModal);
    if (cancelModalBtn) cancelModalBtn.addEventListener('click', closeModal);
    
    // Enregistrement du contact
    if (contactForm) {
        contactForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const contactId = document.getElementById('contact-id-field').value;
            const name = document.getElementById('contact-name-field').value;
            const phone = document.getElementById('contact-phone-field').value;
            const group_tag = document.getElementById('contact-group-field').value;
            
            const payload = { name, phone, group_tag };
            
            const url = contactId ? `/api/contacts/${contactId}` : '/api/contacts';
            const method = contactId ? 'PUT' : 'POST';
            
            try {
                const response = await fetch(url, {
                    method: method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                
                const result = await response.json();
                
                if (response.ok || response.status === 211) {
                    showToast(contactId ? "Contact mis à jour avec succès !" : "Contact créé avec succès !");
                    closeModal();
                    loadContactsList(currentContactsPage);
                    loadContactGroups();
                } else {
                    showToast(result.error || "Erreur lors de l'enregistrement", "error");
                }
            } catch (error) {
                showToast("Impossible d'enregistrer le contact.", "error");
            }
        });
    }

    // Gestionnaire de Drag & Drop CSV
    initCSVDragDrop();
}

async function loadContactGroups() {
    try {
        const response = await fetch('/api/contacts/groups');
        const groups = await response.json();
        
        const filterSelect = document.getElementById('contacts-group-filter');
        const formGroupSelect = document.getElementById('contact-group-field');
        
        if (filterSelect) {
            // Conserver l'option 'Tous'
            filterSelect.innerHTML = '<option value="">Tous les groupes</option>';
            groups.forEach(g => {
                const opt = document.createElement('option');
                opt.value = g;
                opt.innerText = g;
                if (g === contactsGroupFilter) opt.selected = true;
                filterSelect.appendChild(opt);
            });
        }
    } catch (e) {
        console.error("Erreur chargement des groupes :", e);
    }
}

async function loadContactsList(page) {
    currentContactsPage = page;
    const tbody = document.getElementById('contacts-tbody');
    if (!tbody) return;
    
    tbody.innerHTML = `
        <tr>
            <td colspan="5" style="text-align: center; padding: 2rem;">
                <div class="animate-pulse">Chargement des contacts...</div>
            </td>
        </tr>
    `;
    
    try {
        const url = `/api/contacts?page=${page}&search=${encodeURIComponent(contactsSearchQuery)}&group_tag=${encodeURIComponent(contactsGroupFilter)}`;
        const response = await fetch(url);
        const data = await response.json();
        
        if (response.ok) {
            tbody.innerHTML = '';
            
            if (data.contacts.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" style="text-align: center; color: var(--text-secondary); padding: 2rem;">
                            Aucun contact trouvé.
                        </td>
                    </tr>
                `;
                document.getElementById('contacts-pagination').innerHTML = '';
                return;
            }
            
            data.contacts.forEach(c => {
                const optOutBadge = c.opted_out 
                    ? '<span class="badge badge-danger">Désabonné</span>' 
                    : '<span class="badge badge-success">Abonné</span>';
                    
                const toggleOptText = c.opted_out ? 'Abonner' : 'Désabonner';
                const toggleOptIcon = c.opted_out ? 'user-check' : 'user-x';
                
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${c.name}</strong></td>
                    <td><code>${c.phone}</code></td>
                    <td><span class="badge badge-info">${c.group_tag}</span></td>
                    <td>${optOutBadge}</td>
                    <td>
                        <div style="display: flex; gap: 0.5rem;">
                            <button class="btn btn-secondary btn-edit-contact" style="padding: 0.4rem 0.6rem;" data-id="${c.id}" title="Modifier">
                                <i data-lucide="edit-2" style="width: 14px; height: 14px;"></i>
                            </button>
                            <button class="btn btn-secondary btn-optout-contact" style="padding: 0.4rem 0.6rem;" data-id="${c.id}" title="${toggleOptText}">
                                <i data-lucide="${toggleOptIcon}" style="width: 14px; height: 14px;"></i>
                            </button>
                            <button class="btn btn-danger btn-delete-contact" style="padding: 0.4rem 0.6rem;" data-id="${c.id}" title="Supprimer">
                                <i data-lucide="trash-2" style="width: 14px; height: 14px;"></i>
                            </button>
                        </div>
                    </td>
                `;
                tbody.appendChild(tr);
            });
            
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }
            
            // Attacher les gestionnaires d'événements
            attachContactRowListeners();
            
            // Rendu de la pagination
            renderContactsPagination(data.current_page, data.pages);
        }
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: #ef4444; padding: 2rem;">Erreur de chargement.</td></tr>`;
    }
}

function attachContactRowListeners() {
    // Modifier Contact
    document.querySelectorAll('.btn-edit-contact').forEach(btn => {
        btn.addEventListener('click', async () => {
            const id = btn.getAttribute('data-id');
            const row = btn.closest('tr');
            const name = row.cells[0].innerText;
            const phone = row.cells[1].innerText;
            const group = row.cells[2].innerText;
            
            document.getElementById('contact-id-field').value = id;
            document.getElementById('contact-name-field').value = name;
            document.getElementById('contact-phone-field').value = phone;
            document.getElementById('contact-group-field').value = group;
            
            document.getElementById('modal-title').innerText = "Modifier le contact";
            document.getElementById('contact-modal').style.display = 'flex';
        });
    });

    // Toggle Opt-Out
    document.querySelectorAll('.btn-optout-contact').forEach(btn => {
        btn.addEventListener('click', async () => {
            const id = btn.getAttribute('data-id');
            try {
                const response = await fetch(`/api/contacts/toggle-optout/${id}`, { method: 'POST' });
                const result = await response.json();
                if (response.ok) {
                    showToast(result.message);
                    loadContactsList(currentContactsPage);
                }
            } catch (e) {
                showToast("Échec du changement d'opt-out", "error");
            }
        });
    });

    // Supprimer Contact
    document.querySelectorAll('.btn-delete-contact').forEach(btn => {
        btn.addEventListener('click', async () => {
            const id = btn.getAttribute('data-id');
            if (confirm("Êtes-vous sûr de vouloir supprimer ce contact ? Tous ses messages seront également supprimés.")) {
                try {
                    const response = await fetch(`/api/contacts/${id}`, { method: 'DELETE' });
                    if (response.ok) {
                        showToast("Contact supprimé !");
                        loadContactsList(currentContactsPage);
                        loadContactGroups();
                    }
                } catch (e) {
                    showToast("Échec de la suppression.", "error");
                }
            }
        });
    });
}

function renderContactsPagination(current, total) {
    const nav = document.getElementById('contacts-pagination');
    if (!nav) return;
    nav.innerHTML = '';
    
    if (total <= 1) return;
    
    // Bouton Précédent
    const prevBtn = document.createElement('button');
    prevBtn.className = 'page-btn';
    prevBtn.disabled = current === 1;
    prevBtn.innerHTML = '<i data-lucide="chevron-left"></i>';
    prevBtn.addEventListener('click', () => loadContactsList(current - 1));
    nav.appendChild(prevBtn);
    
    // Numéros de pages
    for (let i = 1; i <= total; i++) {
        const pageBtn = document.createElement('button');
        pageBtn.className = `page-btn ${i === current ? 'active' : ''}`;
        pageBtn.innerText = i;
        pageBtn.addEventListener('click', () => loadContactsList(i));
        nav.appendChild(pageBtn);
    }
    
    // Bouton Suivant
    const nextBtn = document.createElement('button');
    nextBtn.className = 'page-btn';
    nextBtn.disabled = current === total;
    nextBtn.innerHTML = '<i data-lucide="chevron-right"></i>';
    nextBtn.addEventListener('click', () => loadContactsList(current + 1));
    nav.appendChild(nextBtn);
    
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
}

function initCSVDragDrop() {
    const zone = document.getElementById('csv-drag-zone');
    const input = document.getElementById('csv-file-input');
    
    if (!zone || !input) return;
    
    zone.addEventListener('click', () => input.click());
    
    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('dragover');
    });
    
    zone.addEventListener('dragleave', () => {
        zone.classList.remove('dragover');
    });
    
    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            handleCSVUpload(e.dataTransfer.files[0]);
        }
    });
    
    input.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleCSVUpload(e.target.files[0]);
        }
    });
}

async function handleCSVUpload(file) {
    if (!file.name.endsWith('.csv')) {
        showToast("Seuls les fichiers CSV sont acceptés.", "error");
        return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    
    showToast("Importation en cours...");
    
    try {
        const response = await fetch('/api/contacts/import', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (response.ok) {
            let msg = `${result.imported} contacts importés, ${result.updated} mis à jour.`;
            if (result.failed > 0) msg += ` ${result.failed} échecs.`;
            
            showToast(msg);
            loadContactsList(1);
            loadContactGroups();
        } else {
            showToast(result.error || "Erreur d'importation CSV", "error");
        }
    } catch (e) {
        showToast("Impossible d'importer le fichier CSV.", "error");
    }
}

/* ═══════════════════════════════════════════════
   MODULE 3 : ENVOI GROUPÉ (BULK SEND & SSE PROGRESS)
   ═══════════════════════════════════════════════ */
function initSendBulk() {
    loadBulkGroups();
    
    const targetTypeSelect = document.getElementById('bulk-target-type');
    const groupSelectContainer = document.getElementById('group-select-container');
    const bulkForm = document.getElementById('bulk-form');
    
    if (targetTypeSelect) {
        targetTypeSelect.addEventListener('change', (e) => {
            if (e.target.value === 'group') {
                groupSelectContainer.style.display = 'block';
            } else {
                groupSelectContainer.style.display = 'none';
            }
        });
    }
    
    if (bulkForm) {
        bulkForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const submitBtn = bulkForm.querySelector('button[type="submit"]');
            submitBtn.disabled = true;
            
            const name = document.getElementById('bulk-name').value;
            const message = document.getElementById('bulk-message').value;
            const target_type = document.getElementById('bulk-target-type').value;
            const target_group = document.getElementById('bulk-group-select').value;
            
            // Gestion de la programmation
            const scheduleInput = document.getElementById('bulk-schedule').value;
            let scheduled_at = null;
            if (scheduleInput) {
                // Convertir la date locale en format ISO UTC requis par le backend
                scheduled_at = new Date(scheduleInput).toISOString();
            }
            
            const payload = {
                name,
                message,
                target_type,
                target_group: target_type === 'group' ? target_group : null,
                scheduled_at
            };
            
            try {
                const response = await fetch('/api/messages/bulk', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                
                const result = await response.json();
                
                if (response.ok) {
                    if (result.scheduled) {
                        showToast(result.message, "success");
                        bulkForm.reset();
                        submitBtn.disabled = false;
                    } else {
                        // Lancer l'écoute de la progression en direct via SSE
                        showToast("Envoi immédiat commencé !");
                        listenToCampaignProgress(result.campaign_id, submitBtn);
                    }
                } else {
                    showToast(result.error || "Erreur de validation", "error");
                    submitBtn.disabled = false;
                }
            } catch (error) {
                showToast("Échec de connexion avec le serveur.", "error");
                submitBtn.disabled = false;
            }
        });
    }
}

async function loadBulkGroups() {
    try {
        const response = await fetch('/api/contacts/groups');
        const groups = await response.json();
        
        const groupSelect = document.getElementById('bulk-group-select');
        if (groupSelect) {
            groupSelect.innerHTML = '<option value="">Sélectionnez un groupe</option>';
            groups.forEach(g => {
                const opt = document.createElement('option');
                opt.value = g;
                opt.innerText = g;
                groupSelect.appendChild(opt);
            });
        }
    } catch (e) {
        console.error(e);
    }
}

function listenToCampaignProgress(campaignId, submitBtn) {
    const progressPanel = document.getElementById('progress-panel');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    const progressContact = document.getElementById('progress-contact');
    
    if (!progressPanel) return;
    
    // Afficher le panel
    progressPanel.style.display = 'block';
    progressBar.style.width = '0%';
    progressText.innerText = '0%';
    progressContact.innerText = 'Initialisation...';
    
    const eventSource = new EventSource(`/api/messages/progress/${campaignId}`);
    
    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if (data.status === 'sending' || data.status === 'completed') {
            const percent = data.percent || 0;
            progressBar.style.width = `${percent}%`;
            progressText.innerText = `${percent}% (${data.current}/${data.total})`;
            progressContact.innerText = `Envoi à : ${data.contact}`;
        }
        
        if (data.status === 'completed') {
            showToast("Campagne d'envoi groupé terminée avec succès !");
            eventSource.close();
            
            setTimeout(() => {
                progressPanel.style.display = 'none';
                document.getElementById('bulk-form').reset();
                submitBtn.disabled = false;
            }, 3000);
        }
    };
    
    eventSource.onerror = (err) => {
        console.error("Erreur SSE :", err);
        eventSource.close();
        progressContact.innerText = "Traitement asynchrone achevé ou interrompu.";
        setTimeout(() => {
            progressPanel.style.display = 'none';
            document.getElementById('bulk-form').reset();
            submitBtn.disabled = false;
        }, 3000);
    };
}

/* ═══════════════════════════════════════════════
   MODULE 4 : HISTORIQUE ET CHAT INTERACTIF (HISTORY.HTML)
   ═══════════════════════════════════════════════ */
let activeChatContactId = null;

function initHistory() {
    loadChatHistoryContacts();
    
    // Lier la barre d'envoi interactive du chat
    const chatInputForm = document.getElementById('chat-input-form');
    if (chatInputForm) {
        chatInputForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const input = document.getElementById('chat-input-text');
            const text = input.value.trim();
            if (!text || !activeChatContactId) return;
            
            input.value = ''; // Clear instantané
            
            // Envoyer un message direct à ce contact
            try {
                const response = await fetch('/api/messages/bulk', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: "Chat Direct",
                        message: text,
                        target_type: "manual",
                        contacts: [activeChatContactId]
                    })
                });
                
                if (response.ok) {
                    // Recharger instantanément les messages pour cette conversation
                    loadActiveChatThread(activeChatContactId);
                } else {
                    showToast("Échec de l'envoi du message.", "error");
                }
            } catch (err) {
                showToast("Erreur de connexion.", "error");
            }
        });
    }
}

async function loadChatHistoryContacts() {
    const listContainer = document.getElementById('chat-list-items');
    if (!listContainer) return;
    
    try {
        // Obtenir toutes les dernières conversations actives du dashboard stats
        const response = await fetch('/api/messages/stats');
        const data = await response.json();
        
        if (response.ok) {
            listContainer.innerHTML = '';
            
            if (data.latest_conversations.length === 0) {
                listContainer.innerHTML = '<div style="padding:1.5rem; text-align:center; color:var(--text-secondary);">Aucun message historique.</div>';
                return;
            }
            
            // Mapper les conversations uniques
            const processedContacts = new Set();
            
            data.latest_conversations.forEach(msg => {
                if (processedContacts.has(msg.contact_id)) return;
                processedContacts.add(msg.contact_id);
                
                const item = document.createElement('div');
                item.className = `chat-item ${activeChatContactId === msg.contact_id ? 'active' : ''}`;
                item.setAttribute('data-contact-id', msg.contact_id);
                
                item.innerHTML = `
                    <div class="chat-item-header">
                        <span class="chat-item-name">${msg.contact_name}</span>
                        <span class="chat-item-time">${formatWhatsAppDate(msg.sent_at)}</span>
                    </div>
                    <div class="chat-item-preview">${msg.content}</div>
                `;
                
                item.addEventListener('click', () => {
                    document.querySelectorAll('.chat-item').forEach(el => el.classList.remove('active'));
                    item.classList.add('active');
                    activeChatContactId = msg.contact_id;
                    
                    // charger le thread
                    loadActiveChatThread(msg.contact_id, msg.contact_name, msg.contact_phone);
                });
                
                listContainer.appendChild(item);
            });
        }
    } catch (e) {
        console.error(e);
    }
}

async function loadActiveChatThread(contactId, name = '', phone = '') {
    const emptyWindow = document.getElementById('chat-empty-state');
    const activeWindow = document.getElementById('chat-active-state');
    const messagesContainer = document.getElementById('chat-messages-container');
    
    if (!messagesContainer) return;
    
    if (emptyWindow && activeWindow) {
        emptyWindow.style.display = 'none';
        activeWindow.style.display = 'flex';
    }
    
    // Mettre à jour l'en-tête du chat
    if (name) document.getElementById('chat-header-name').innerText = name;
    if (phone) document.getElementById('chat-header-phone').innerText = phone;
    
    try {
        // Chercher l'historique complet trié par date pour ce contact spécifique
        const response = await fetch(`/api/messages/history?per_page=100&search=${encodeURIComponent(phone)}`);
        const data = await response.json();
        
        if (response.ok) {
            messagesContainer.innerHTML = '';
            
            // Le backend renvoie du plus récent au plus ancien, on inverse pour l'affichage chronologique
            const messages = data.messages || [];
            messages.reverse();
            
            if (messages.length === 0) {
                messagesContainer.innerHTML = '<div style="text-align:center; color:var(--text-secondary); margin-top:2rem;">Aucun message historique.</div>';
                return;
            }
            
            messages.forEach(msg => {
                const bubble = document.createElement('div');
                bubble.className = `message-bubble ${msg.direction}`;
                
                let checkmarks = '';
                if (msg.direction === 'out') {
                    if (msg.status === 'read') {
                        checkmarks = '<i data-lucide="check-check" style="color: var(--accent-color);"></i>';
                    } else if (msg.status === 'delivered') {
                        checkmarks = '<i data-lucide="check-check"></i>';
                    } else if (msg.status === 'sent') {
                        checkmarks = '<i data-lucide="check"></i>';
                    } else { // failed
                        checkmarks = '<i data-lucide="alert-circle" style="color: #ef4444;"></i>';
                    }
                }
                
                const hours = new Date(msg.sent_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                
                bubble.innerHTML = `
                    <div class="msg-text">${msg.content}</div>
                    <div class="msg-meta">
                        <span>${hours}</span>
                        ${checkmarks}
                    </div>
                `;
                messagesContainer.appendChild(bubble);
            });
            
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }
            
            // Scroll en bas automatique pour voir les derniers messages
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    } catch (e) {
        console.error(e);
    }
}

/* ═══════════════════════════════════════════════
   MODULE 5 : PARAMÈTRES ET CONFIGURATION (SETTINGS.HTML)
   ═══════════════════════════════════════════════ */
function initSettings() {
    loadSettingsData();
    
    const settingsForm = document.getElementById('settings-form');
    const testWhatsAppBtn = document.getElementById('btn-test-whatsapp');
    const testGeminiBtn = document.getElementById('btn-test-gemini');
    
    if (settingsForm) {
        settingsForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const submitBtn = settingsForm.querySelector('button[type="submit"]');
            submitBtn.disabled = true;
            
            const auto_reply_enabled = document.getElementById('setting-auto-reply').checked;
            const system_prompt = document.getElementById('setting-prompt').value;
            const openwa_api_url = document.getElementById('setting-openwa-url').value;
            const openwa_api_key = document.getElementById('setting-openwa-key').value;
            const openwa_session_id = document.getElementById('setting-openwa-session').value;
            const gemini_api_key = document.getElementById('setting-gemini-key').value;
            
            const payload = {
                auto_reply_enabled,
                system_prompt,
                openwa_api_url,
                openwa_api_key,
                openwa_session_id,
                gemini_api_key
            };
            
            try {
                const response = await fetch('/api/ai/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                
                const result = await response.json();
                if (response.ok) {
                    showToast("Configuration sauvegardée !");
                    // Recharger pour voir les clés masquées nettoyées
                    loadSettingsData();
                } else {
                    showToast(result.error || "Erreur de sauvegarde", "error");
                }
            } catch (err) {
                showToast("Échec de connexion.", "error");
            } finally {
                submitBtn.disabled = false;
            }
        });
    }

    // Ping WhatsApp
    if (testWhatsAppBtn) {
        testWhatsAppBtn.addEventListener('click', async () => {
            testWhatsAppBtn.disabled = true;
            const text = testWhatsAppBtn.innerHTML;
            testWhatsAppBtn.innerHTML = '<span class="animate-pulse">Validation...</span>';
            
            try {
                const response = await fetch('/api/ai/test-whatsapp', { method: 'POST' });
                const result = await response.json();
                
                if (result.success) {
                    showToast(result.message, "success");
                } else {
                    showToast(result.message, "error");
                }
            } catch (e) {
                showToast("Erreur lors de la validation WhatsApp.", "error");
            } finally {
                testWhatsAppBtn.innerHTML = text;
                testWhatsAppBtn.disabled = false;
            }
        });
    }

    // Ping Gemini
    if (testGeminiBtn) {
        testGeminiBtn.addEventListener('click', async () => {
            testGeminiBtn.disabled = true;
            const text = testGeminiBtn.innerHTML;
            testGeminiBtn.innerHTML = '<span class="animate-pulse">Validation...</span>';
            
            try {
                const response = await fetch('/api/ai/test-gemini', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt: "Génère un message d'une phrase disant 'Intégration Gemini réussie !'" })
                });
                const result = await response.json();
                
                if (result.success) {
                    showToast(result.message, "success");
                } else {
                    showToast(result.message, "error");
                }
            } catch (e) {
                showToast("Erreur lors de la validation Gemini.", "error");
            } finally {
                testGeminiBtn.innerHTML = text;
                testGeminiBtn.disabled = false;
            }
        });
    }
}

async function loadSettingsData() {
    try {
        const response = await fetch('/api/ai/config');
        const data = await response.json();
        
        if (response.ok) {
            document.getElementById('setting-auto-reply').checked = data.auto_reply_enabled;
            document.getElementById('setting-prompt').value = data.system_prompt;
            document.getElementById('setting-openwa-url').value = data.openwa_api_url || '';
            document.getElementById('setting-openwa-key').value = data.openwa_api_key || '';
            document.getElementById('setting-openwa-session').value = data.openwa_session_id || '';
            document.getElementById('setting-gemini-key').value = data.gemini_api_key || '';
        }
    } catch (e) {
        console.error("Erreur de chargement des paramètres :", e);
    }
}
