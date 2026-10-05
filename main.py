from fasthtml.common import *
import os
import requests
import json
import uuid
import asyncio
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# --- 0. INITIALISATION DES DOSSIERS (BDD & LOGS) ---
os.makedirs("sessions", exist_ok=True)
os.makedirs("logs", exist_ok=True)

def log_event(session_id, action, level="INFO"):
    """Enregistre chaque action dans un fichier texte dédié à la session."""
    sid = session_id if session_id else "system"
    log_file = f"logs/session_{sid}.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] [{level}] {action}\n")

# --- 1. GESTION DE L'HISTORIQUE (INDEX & SESSIONS) ---
HISTORY_FILE = "history.json"

def load_index():
    if not os.path.exists(HISTORY_FILE): return {}
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        try: 
            idx = json.load(f)
            # Migration automatique si l'ancien format (avec "messages" dedans) est détecté
            for sid, data in list(idx.items()):
                if "messages" in data:
                    save_session_data(sid, data["messages"])
                    del data["messages"]
            return idx
        except: return {}

def save_index(idx):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(idx, f, indent=4, ensure_ascii=False)

def load_session_data(session_id):
    path = f"sessions/{session_id}.json"
    if not os.path.exists(path): return []
    with open(path, "r", encoding="utf-8") as f:
        try: return json.load(f)
        except: return []

def save_session_data(session_id, messages):
    with open(f"sessions/{session_id}.json", "w", encoding="utf-8") as f:
        json.dump(messages, f, indent=4, ensure_ascii=False)

def create_new_session():
    session_id = str(uuid.uuid4())
    idx = load_index()
    idx[session_id] = {"title": f"Discussion du {datetime.now().strftime('%d/%m %H:%M')}", "pinned": False}
    save_index(idx)
    save_session_data(session_id, [])
    log_event(session_id, "Nouvelle session initialisée.")
    return session_id

def render_history_list():
    idx = load_index()
    sorted_sessions = sorted(idx.items(), key=lambda x: (not x[1].get('pinned', False), x[1]['title']), reverse=False)
    
    items = [
        Button("➕ Nouvelle Discussion", cls="history-btn w-full mb-3 text-center", style="background:#00e5ff; color:#0f172a; font-weight:bold;", hx_get="/session/new", hx_target="#chat-history")
    ]
    
    for sid, data in sorted_sessions:
        pin_icon = "📍" if data.get('pinned') else "📌"
        pin_color = "#10b981" if data.get('pinned') else "#94a3b8"
        
        item = Div(
            Div(data['title'], cls="truncate flex-grow cursor-pointer hover:text-cyan-400", hx_get=f"/session/load/{sid}", hx_target="#chat-history"),
            Div(
                Button("✏️", cls="text-xs mx-1 hover:text-white", onclick=f"let name = prompt('Nouveau nom:'); if(name) {{ htmx.ajax('POST', '/history/rename/{sid}', {{values: {{title: name}}, target: '#history-list-container'}}); }}"),
                Button(pin_icon, style=f"color:{pin_color};", cls="text-xs mx-1 hover:text-white", hx_post=f"/history/pin/{sid}", hx_target="#history-list-container"),
                Button("🗑️", cls="text-xs hover:text-red-500", onclick=f"if(confirm('Supprimer définitivement cette discussion ?')) {{ htmx.ajax('POST', '/history/delete/{sid}', {{target: '#history-list-container'}}); }}"),
                cls="flex-shrink-0"
            ),
            cls="flex justify-between items-center history-btn w-full mb-1"
        )
        items.append(item)
    return Div(*items, id="history-list-container", hx_swap_oob="true")


# --- 2. GESTION DU CATALOGUE (GENERIQUE & OPENROUTER) ---
MODELS_DATA = []
def init_models():
    global MODELS_DATA
    MODELS_DATA = [
        {"id": "groq|llama3-8b-8192", "name": "Groq - Llama 3 (8B)", "is_free": True, "description": "Modèle ultra-rapide hébergé par Groq. Idéal pour les tâches générales, la structuration de données et le code basique.", "architecture": {"modality": "text"}},
        {"id": "gemini|gemini-1.5-flash", "name": "Google - Gemini 1.5 Flash", "is_free": True, "description": "Modèle multimodal très rapide et léger de Google. Parfait pour le raisonnement rapide, le code et l'analyse de longs contextes.", "architecture": {"modality": "text/vision"}},
        {"id": "deepseek|deepseek-coder", "name": "DeepSeek - Coder", "is_free": False, "description": "Modèle d'élite spécialisé dans l'ingénierie logicielle, la création d'algorithmes et la génération de code complexe.", "architecture": {"modality": "text/code"}}
    ]
    try:
        res = requests.get("https://openrouter.ai/api/v1/models", timeout=5)
        if res.status_code == 200:
            for m in res.json().get("data", []):
                m["id"] = f"openrouter|{m['id']}"
                m["name"] = f"OR - {m['name']}"
                MODELS_DATA.append(m)
    except Exception as e:
        log_event("system", f"Erreur chargement catalogue OpenRouter : {e}", "ERROR")
init_models()

def get_model_options(filter_type="all"):
    options = []
    for m in sorted(MODELS_DATA, key=lambda x: x['name']):
        is_free = m.get("is_free", "free" in m.get("id", "").lower())
        if filter_type == "free" and not is_free: continue
        if filter_type == "paid" and is_free: continue
        tag = "Gratuit" if is_free else "Payant"
        options.append(Option(f"{m['name']} ({tag})", value=m['id']))
    return Select(*options, name="model_id", cls="model-select", style="width: 100%;")


# --- 3. MOTEUR D'INTELLIGENCE & GESTION DES ERREURS ---
def get_budget():
    mgmt_key = os.getenv("OPENROUTER_MANAGEMENT_KEY")
    if not mgmt_key: return "Clé manquante"
    try:
        data = requests.get("https://openrouter.ai/api/v1/credits", headers={"Authorization": f"Bearer {mgmt_key}"}, timeout=5).json().get("data", {})
        return f"{data.get('total_credits', 0) - data.get('total_usage', 0):.4f} $"
    except: return "Erreur lecture"

def handle_api_error(session_id, provider, raw_error):
    log_event(session_id, f"Erreur API {provider} : {raw_error}", "ERROR")
    sys_prompt = "Tu es un assistant technique. Une API distante a renvoyé l'erreur suivante. Traduis-la en français simplement et propose une explication claire pour aider l'utilisateur."
    try:
        qwen_res = requests.post("http://localhost:11434/api/generate", json={"model": "qwen2.5-coder:7b", "prompt": f"{sys_prompt}\n\nErreur ({provider}): {raw_error}", "stream": False}, timeout=15).json()["response"]
        return f"⚠️ **Alerte Serveur ({provider})**\n{qwen_res}"
    except:
        return f"⚠️ Erreur brute ({provider}) : {raw_error}"

async def async_ask_llm(session_id, provider, actual_model, msg):
    return await asyncio.to_thread(ask_llm, session_id, provider, actual_model, msg)

def ask_llm(session_id, provider, actual_model, msg):
    log_event(session_id, f"Interrogation API distantes : {provider} | Modèle : {actual_model}")
    try:
        if provider == "openrouter":
            res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"}, json={"model": actual_model, "messages": [{"role": "user", "content": msg}]})
            if res.status_code != 200: return handle_api_error(session_id, provider, res.text)
            return res.json()["choices"][0]["message"]["content"]
            
        elif provider == "groq":
            res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"}, json={"model": actual_model, "messages": [{"role": "user", "content": msg}]})
            if res.status_code != 200: return handle_api_error(session_id, provider, res.text)
            return res.json()["choices"][0]["message"]["content"]
            
        elif provider == "gemini":
            res = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{actual_model}:generateContent?key={os.getenv('GEMINI_API_KEY')}", json={"contents": [{"parts": [{"text": msg}]}]})
            if res.status_code != 200: return handle_api_error(session_id, provider, res.text)
            return res.json()["candidates"][0]["content"]["parts"][0]["text"]
            
        return handle_api_error(session_id, provider, "Fournisseur non implémenté.")
    except Exception as e:
        return handle_api_error(session_id, provider, str(e))


# --- 4. PIPELINES DE TRAITEMENT ---
def pipeline_minecraft(session_id, raw_msg):
    log_event(session_id, "Lancement Pipeline 100% Local Minecraft (Qwen -> Phuzzy -> Qwen)")
    try:
        en_prompt = requests.post("http://localhost:11434/api/generate", json={"model": "qwen2.5-coder:7b", "prompt": f"Translate this Minecraft modding request into technical English. Return ONLY English text.\n\n{raw_msg}", "stream": False}).json()["response"]
        phuzzy_res = requests.post("http://localhost:11434/api/generate", json={"model": "phuzzy:latest", "prompt": en_prompt, "stream": False}).json()["response"]
        final_fr = requests.post("http://localhost:11434/api/generate", json={"model": "qwen2.5-coder:7b", "prompt": f"Traduis les explications techniques en français. NE TRADUIS PAS le code.\n\n{phuzzy_res}", "stream": False}).json()["response"]
        return final_fr, "Qwen ➔ Phuzzy ➔ Qwen"
    except Exception as e:
        return handle_api_error(session_id, "Ollama Local", str(e)), "Erreur Locale"

async def pipeline_consolidated(session_id, raw_msg):
    log_event(session_id, "Lancement Pipeline Consolidation Multi-IA")
    try:
        opt_prompt = requests.post("http://localhost:11434/api/generate", json={"model": "qwen2.5-coder:7b", "prompt": f"Optimise cette demande pour des LLM codeurs. Sois ultra précis.\n\n{raw_msg}", "stream": False}).json()["response"]
        rep_groq, rep_gemini = await asyncio.gather(
            async_ask_llm(session_id, "groq", "llama3-8b-8192", opt_prompt),
            async_ask_llm(session_id, "gemini", "gemini-1.5-flash", opt_prompt)
        )
        sys_synth = "Tu es un Architecte Logiciel Senior. Voici la même demande traitée par deux IA différentes. Lis leurs propositions, corrige les erreurs potentielles, garde le meilleur des deux, et génère le code final absolu et parfait en français."
        final_prompt = f"{sys_synth}\n\n--- IA 1 (Groq) ---\n{rep_groq}\n\n--- IA 2 (Gemini) ---\n{rep_gemini}"
        final_res = requests.post("http://localhost:11434/api/generate", json={"model": "qwen2.5-coder:7b", "prompt": final_prompt, "stream": False}).json()["response"]
        return final_res, "Qwen ➔ [Groq + Gemini] ➔ Synthèse Qwen"
    except Exception as e:
        return handle_api_error(session_id, "Pipeline Multi-IA", str(e)), "Erreur Consolidation"


# --- 5. INTERFACE UTILISATEUR & ROUTES ---
theme_hdrs = [
    Script(src="https://cdn.tailwindcss.com"),
    Script(src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"),
    Script(src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"),
    Link(rel="stylesheet", href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/tokyo-night-dark.min.css"),
    Style("""
        body { background-color: #0f172a; color: #f8fafc; font-family: system-ui, sans-serif; margin: 0;}
        .sidebar { background-color: #1e293b; border-right: 1px solid #333; height: 100vh; padding: 20px; display: flex; flex-direction: column;}
        .main-content { padding: 20px; height: 100vh; display: flex; flex-direction: column; position: relative;}
        .chat-container { flex-grow: 1; overflow-y: auto; margin-bottom: 20px; border: 1px solid #333; padding: 15px; border-radius: 8px; background: #151e2e; }
        .input-row { display: flex; gap: 10px; align-items: flex-end; width: 100%; background: #1e293b; padding: 10px; border-radius: 10px; border: 1px solid #333;}
        .input-box { flex-grow: 1; padding: 12px; border-radius: 5px; background: #2a2a35; border: 1px solid #444; color: white; outline: none; }
        .file-upload-btn { background: #2a2a35; border: 1px solid #444; color: #94a3b8; padding: 12px; border-radius: 5px; cursor: pointer; font-size:14px; display: flex; align-items:center;}
        .model-select { padding: 12px; border-radius: 5px; background: #2a2a35; border: 1px solid #444; color: #00e5ff; outline: none; font-weight: bold; cursor: pointer;}
        .send-btn { padding: 12px 24px; border-radius: 5px; background: #00e5ff; color: #0f172a; font-weight: bold; cursor: pointer; border: none; }
        .msg-user { color: #00e5ff; font-size: 12px; font-weight: bold; margin-bottom: 2px; margin-top: 15px;}
        .msg-ia { color: #a855f7; font-size: 12px; font-weight: bold; margin-bottom: 2px; margin-top: 15px;}
        .bubble-user { background: #1e293b; padding: 10px; border-radius: 5px; display: inline-block; color: white; border: 1px solid #333;}
        .bubble-ia { background: #1e293b; padding: 15px; border-radius: 8px; display: block; color: #e2e8f0; }
        .bubble-ia pre { background: #111827; padding: 15px; border-radius: 8px; margin-top: 10px; position: relative; border: 1px solid #333;}
        .context-radio-group { display: flex; gap: 15px; background: #1e293b; padding: 10px 15px; border-radius: 8px; border: 1px solid #333; margin-bottom: 10px; width: fit-content; }
        .htmx-indicator { display: none; position: absolute; bottom: 120px; left: 50%; transform: translateX(-50%); background: rgba(15, 23, 42, 0.9); border: 1px solid #00e5ff; padding: 15px 30px; border-radius: 50px; color: #00e5ff; font-weight: bold;}
        .htmx-request .htmx-indicator { display: block; }
        .history-btn { background: #2a2a35; color: #e2e8f0; border: 1px solid #444; padding: 8px; border-radius: 5px; cursor: pointer; text-align: left; }
        .history-btn:hover { background: #38bdf8; color: #0f172a; }
        .export-btn { display: block; background: #0f172a; border: 1px solid #00e5ff; color: #00e5ff; font-weight: bold; padding: 10px; border-radius: 5px; text-align: center; text-decoration: none; transition: 0.2s;}
        .export-btn:hover { background: #00e5ff; color: #0f172a; }
    """),
    Script("""
        function updateUI() {
            let ctx = document.querySelector('input[name="context_type"]:checked').value;
            let modBox = document.getElementById('model-selection-area');
            if(ctx === 'minecraft' || ctx === 'consolidated') { modBox.style.display = 'none'; } 
            else { modBox.style.display = 'flex'; }
        }
        
        function updateFileCount(input) {
            let label = document.getElementById('file-label-text');
            if(input && input.files && input.files.length > 0) { 
                label.innerText = `📎 ${input.files.length} fichier(s)`; 
                label.style.color = '#00e5ff'; 
            } else { 
                label.innerText = '📎 Fichiers'; 
                label.style.color = '#94a3b8'; 
            }
        }

        htmx.onLoad(function(content) {
            content.querySelectorAll('.bubble-ia:not(.rendered)').forEach(function(el) {
                el.innerHTML = marked.parse(el.textContent);
                el.classList.add('rendered');
                el.querySelectorAll('pre code').forEach((block) => { hljs.highlightElement(block); });
                let chat = document.getElementById('chat-history'); chat.scrollTop = chat.scrollHeight;
            });
        });
    """)
]

app, rt = fast_app(hdrs=theme_hdrs)

@rt('/session/new')
def get():
    sid = create_new_session()
    new_hidden = Input(type="hidden", name="session_id", value=sid, id="current-session-id", hx_swap_oob="true")
    return Div(), new_hidden, render_history_list()

@rt('/session/load/{sid}')
def get(sid: str):
    log_event(sid, "Chargement de la session.")
    messages = load_session_data(sid)
    bubbles = []
    for msg in messages:
        bubbles.append(Div(
            P("Vous", cls="msg-user"), Div(NotStr(f"{msg['user']}{msg.get('info_fichiers', '')}{msg.get('info_local', '')}"), cls="bubble-user"),
            P(f"AETHAS38 ({msg.get('nom_affichage', 'IA')})", cls="msg-ia"), Div(msg['ia'], cls="bubble-ia")
        ))
    new_hidden = Input(type="hidden", name="session_id", value=sid, id="current-session-id", hx_swap_oob="true")
    return tuple(bubbles) + (new_hidden,)

@rt('/history/pin/{sid}')
def post_pin(sid: str):
    idx = load_index()
    if sid in idx:
        idx[sid]['pinned'] = not idx[sid].get('pinned', False)
        save_index(idx)
        log_event(sid, "Épinglage modifié.")
    return render_history_list()

@rt('/history/rename/{sid}')
def post_rename(sid: str, title: str):
    idx = load_index()
    if sid in idx:
        idx[sid]['title'] = title
        save_index(idx)
        log_event(sid, f"Renommé en: {title}")
    return render_history_list()

@rt('/history/delete/{sid}')
def post_delete(sid: str):
    idx = load_index()
    if sid in idx:
        del idx[sid]
        save_index(idx)
        if os.path.exists(f"sessions/{sid}.json"): os.remove(f"sessions/{sid}.json")
        log_event(sid, "Session supprimée définitivement.", "WARNING")
    return render_history_list()

@rt('/export_models')
def get():
    log_event("system", "Demande d'exportation du catalogue de modèles.")
    now = datetime.now()
    date_str = now.strftime('%d/%m/%Y à %H:%M:%S')
    file_date = now.strftime('%Y%m%d_%H%M%S')
    
    txt_content = f"=== CATALOGUE COMPLET DES MODÈLES (Généré le {date_str}) ===\n\n"
    
    for m in MODELS_DATA:
        name = m.get('name', 'Inconnu')
        m_id = m.get('id', 'Inconnu')
        
        usage = "Général / Texte"
        arch_mod = str(m.get('architecture', {}).get('modality', '')).lower()
        m_id_lower = m_id.lower()
        
        if "vision" in arch_mod or "vision" in m_id_lower or "vl" in m_id_lower or "image" in arch_mod:
            usage = "Vision (Analyse d'images & Multimodal)"
        elif "coder" in m_id_lower or "code" in m_id_lower or "math" in m_id_lower:
            usage = "Codage & Mathématiques"
        elif "video" in m_id_lower:
            usage = "Vidéo"
        elif "rp" in m_id_lower or "uncensored" in m_id_lower or "roleplay" in m_id_lower:
            usage = "Non-censuré / Roleplay"
            
        is_free = m.get("is_free")
        if is_free is None:
            pricing = m.get('pricing', {})
            p_prompt = float(pricing.get('prompt', -1))
            p_comp = float(pricing.get('completion', -1))
            cout = "Gratuit" if p_prompt == 0.0 and p_comp == 0.0 else f"Payant (In: {p_prompt}, Out: {p_comp})"
        else:
            cout = "Gratuit" if is_free else "Payant"
            
        desc = str(m.get('description', '')).replace('\n', ' ')
        desc_courte = desc[:150] + "..." if len(desc) > 150 else desc
        desc_fr = desc_courte
        
        if "openrouter" in m_id and desc_courte:
            try:
                # Appel direct Google Translate
                url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=fr&dt=t&q=" + requests.utils.quote(desc_courte)
                trans_res = requests.get(url, timeout=2)
                if trans_res.status_code == 200:
                    desc_fr = "".join([x[0] for x in trans_res.json()[0]])
            except: pass
                
        if not desc_fr: desc_fr = "Aucune description fournie."
        
        txt_content += f"Nom : {name}\nID : {m_id}\nTarif : {cout}\nSpécialité : {usage}\nDescription : {desc_fr}\n{'-'*60}\n"

    return Response(txt_content, media_type="text/plain", headers={"Content-Disposition": f"attachment; filename=modeles_ia_{file_date}.txt"})


@rt('/')
def get():
    session_id = create_new_session()
    return Title("AETHAS38 Multi-IA"), Body(
        Div(
            Div(
                H2("AETHAS 38", style="color:#00e5ff; font-weight:bold; font-size:24px;"),
                P("Tech Core - Multi IA", style="color:#a855f7; margin-bottom: 20px;"),
                
                Div(
                    H3("Historique de Code", style="color:#94a3b8; font-size:12px; font-weight:bold; margin-bottom:10px;"),
                    render_history_list(),
                    style="display:flex; flex-direction:column; flex-grow:1; margin-bottom: 10px; overflow:hidden;"
                ),
                
                # hx_disable=True autorise le navigateur à télécharger le fichier généré
                A("📥 Exporter Modèles (.txt)", cls="export-btn w-full mt-2", href="/export_models", hx_disable=True),
                
                Div(
                    P("BUDGET OPENROUTER", style="color:#94a3b8; font-size:10px; font-weight:bold; margin-bottom:5px;"),
                    P(get_budget(), id="budget-display", style="color:#10b981; font-size:18px; font-weight:bold;"),
                    cls="budget-box", style="margin-top:15px;"
                ),
                cls="sidebar"
            ),
            Div(
                Div(id="chat-history", cls="chat-container"),
                Div("⚙️ Traitement de l'Architecture IA en cours...", id="loading-tracker", cls="htmx-indicator"),
                
                Form(
                    Input(type="hidden", name="session_id", value=session_id, id="current-session-id"),
                    Div(
                        Label(Input(type="radio", name="context_type", value="generic", checked=True, onchange="updateUI()"), " 💻 Code Générique (Modèle Unique)"),
                        Label(Input(type="radio", name="context_type", value="consolidated", onchange="updateUI()"), " 🧠 Consolidation (Multi-IA ➔ Qwen)"),
                        Label(Input(type="radio", name="context_type", value="minecraft", onchange="updateUI()"), " ⛏ Minecraft (100% Local)"),
                        cls="context-radio-group text-sm text-white flex gap-4"
                    ),
                    Div(
                        Select(Option("Tous les modèles", value="all"), Option("Gratuits", value="free"), Option("Payants", value="paid"), name="filter_type", cls="model-select", hx_get="/filter_models", hx_target="#model-select-wrapper", style="width: 250px;"),
                        Div(get_model_options("all"), id="model-select-wrapper", style="flex-grow: 1;"),
                        cls="flex gap-2 mb-2 w-full", id="model-selection-area"
                    ),
                    Div(
                        Input(type="file", name="fichiers", id="file-upload", multiple=True, style="display:none;", onchange="updateFileCount(this)"),
                        Label(Span("📎 Fichiers", id="file-label-text"), _for="file-upload", cls="file-upload-btn"),
                        Input(type="text", name="msg", placeholder="Insérez votre requête...", cls="input-box", required=True),
                        Button("Envoyer", type="submit", cls="send-btn"),
                        cls="input-row"
                    ),
                    hx_post="/chat", hx_target="#chat-history", hx_swap="beforeend", hx_indicator="#loading-tracker", enctype="multipart/form-data",
                    **{"hx-on:htmx:afterRequest": "if(event.detail.successful) { this.reset(); updateFileCount(document.getElementById('file-upload')); }"}
                ),
                cls="main-content"
            ),
            style="display: grid; grid-template-columns: 250px 1fr;"
        )
    )

@rt('/filter_models')
def get(filter_type: str): return get_model_options(filter_type)

@rt('/chat')
async def post(msg: str, model_id: str, session_id: str, context_type: str = "generic", fichiers: list[UploadFile] = None):
    log_event(session_id, f"Envoi d'un message (Contexte: {context_type})")
    
    files_context = ""
    noms_fichiers = []
    if fichiers:
        for f in fichiers:
            if f.filename:
                noms_fichiers.append(f.filename)
                try: files_context += f"\n--- {f.filename} ---\n{(await f.read()).decode('utf-8')}\n"
                except: 
                    files_context += f"\n--- {f.filename} (Binaire ignoré) ---\n"
                    log_event(session_id, f"Fichier non lisible : {f.filename}", "WARNING")
    
    full_req = f"Fichiers fournis:\n{files_context}\nDemande: {msg}" if files_context else msg

    if context_type == "minecraft":
        ia_reponse, pipeline_info = pipeline_minecraft(session_id, full_req)
        nom_affichage = "Local - Phuzzy/Minecraft"
    
    elif context_type == "consolidated":
        ia_reponse, pipeline_info = await pipeline_consolidated(session_id, full_req)
        nom_affichage = "Qwen Synthèse (via Groq/Gemini)"
        
    else:
        opt_prompt = requests.post("http://localhost:11434/api/generate", json={"model": "qwen2.5-coder:7b", "prompt": f"Optimise cette demande pour un LLM codeur. Retourne UNIQUEMENT le prompt.\n\n{full_req}", "stream": False}).json()["response"]
        parts = model_id.split("|", 1)
        provider, actual_model = parts[0], parts[1] if len(parts) > 1 else model_id
        ia_reponse = ask_llm(session_id, provider, actual_model, opt_prompt)
        nom_affichage = f"{provider.capitalize()} - {actual_model.split('/')[-1]}"
        pipeline_info = "Qwen ➔ API Distante Unique"

    info_fichiers = f"<br><span style='color:#a855f7; font-size:10px;'>📎 {len(noms_fichiers)} fichier(s) joint(s)</span>" if noms_fichiers else ""
    info_local = f"<br><span style='color:#38bdf8; font-size:10px;'>⚙️ Pipeline : {pipeline_info}</span>"
    
    # Séparation et sauvegarde des données complètes pour la session
    session_data = load_session_data(session_id)
    session_data.append({
        "user": msg, 
        "ia": ia_reponse, 
        "nom_affichage": nom_affichage, 
        "info_fichiers": info_fichiers, 
        "info_local": info_local
    })
    save_session_data(session_id, session_data)
    log_event(session_id, "Réponse sauvegardée avec succès.")

    chat_bubble = Div(
        P("Vous", cls="msg-user"), Div(NotStr(f"{msg}{info_fichiers}{info_local}"), cls="bubble-user"),
        P(f"AETHAS38 ({nom_affichage})", cls="msg-ia"), Div(ia_reponse, cls="bubble-ia")
    )
    
    updated_budget = P(get_budget(), id="budget-display", style="color:#10b981; font-size:18px; font-weight:bold;", hx_swap_oob="true")
    return chat_bubble, updated_budget

if __name__ == '__main__':
    serve(port=5001)