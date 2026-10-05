from fasthtml.common import *
import os
import requests
import json
import uuid
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from auth import validate_password_strength, hash_password, verify_password, generate_totp_secret, verify_totp

load_dotenv()

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
        .htmx-indicator { display: none; position: absolute; bottom: 120px; left: 50%; transform: translateX(-50%); background: rgba(15, 23, 42, 0.9); border: 1px solid #00e5ff; padding: 15px 30px; border-radius: 50px; color: #00e5ff; font-weight: bold; z-index: 50;}
        .htmx-request .htmx-indicator { display: block; }
        .history-btn { background: #2a2a35; color: #e2e8f0; border: 1px solid #444; padding: 8px; border-radius: 5px; cursor: pointer; text-align: left; }
        .history-btn:hover { background: #38bdf8; color: #0f172a; }
        .export-btn { display: block; background: #0f172a; border: 1px solid #00e5ff; color: #00e5ff; font-weight: bold; padding: 10px; border-radius: 5px; text-align: center; cursor: pointer; transition: 0.2s; width: 100%;}
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
        async function downloadModels() {
            let tracker = document.getElementById('loading-tracker');
            let oldText = tracker.innerText;
            tracker.style.display = 'block';
            tracker.innerText = '⚙️ Extraction et traduction du catalogue (Patientez ~1 min)...';
            try {
                let res = await fetch('/export_models');
                let text = await res.text();
                let blob = new Blob([text], {type: 'text/plain'});
                let url = window.URL.createObjectURL(blob);
                let a = document.createElement('a');
                a.href = url;
                let d = new Date();
                let ds = d.getFullYear() + ("0"+(d.getMonth()+1)).slice(-2) + ("0"+d.getDate()).slice(-2) + "_" + ("0"+d.getHours()).slice(-2) + ("0"+d.getMinutes()).slice(-2);
                a.download = 'modeles_ia_' + ds + '.txt';
                a.click();
                window.URL.revokeObjectURL(url);
            } catch(e) {
                alert("Erreur lors de l'exportation.");
            }
            tracker.style.display = 'none';
            tracker.innerText = oldText;
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

# Activation des sessions chiffrées avec la clé définie dans le .env
app, rt = fast_app(secret_key=os.getenv("SESSION_SECRET", "super-secret-key-fallback"), hdrs=theme_hdrs)

# --- ROUTES D'AUTHENTIFICATION ---
@rt('/login')
def get():
    return Title("Connexion - AETHAS38"), Body(
        Div(
            H2("AETHAS 38 - Accès Sécurisé", style="color:#00e5ff; margin-bottom:20px; text-align:center;"),
            Form(
                Input(type="email", name="email", placeholder="E-mail", cls="input-box mb-3 w-full", required=True),
                Input(type="password", name="password", placeholder="Mot de passe", cls="input-box mb-3 w-full", required=True),
                Input(type="text", name="totp_code", placeholder="Code 2FA (6 chiffres)", cls="input-box mb-4 w-full", required=True),
                Button("Se connecter", type="submit", cls="send-btn w-full"),
                hx_post="/auth/login", hx_target="#auth-response"
            ),
            Div(id="auth-response", style="color:red; margin-top:10px; text-align:center;"),
            cls="sidebar", style="margin: auto; width: 400px; height: auto; border-radius: 10px; margin-top: 15vh;"
        ), style="background-color: #0f172a; height: 100vh; display: flex;"
    )

@rt('/auth/login')
def post(email: str, password: str, totp_code: str, session):
    # On utilise VOS noms de variables exacts
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_hash = os.getenv("ADMIN_PASSWORD_HASH")
    totp_secret = os.getenv("ADMIN_2FA_SECRET")

    if not admin_email or not admin_hash or not totp_secret:
        return Div("Configuration système incomplète (.env).", style="color:red; font-weight:bold;")

    if email == admin_email and verify_password(admin_hash, password) and verify_totp(totp_secret, totp_code):
        session["authenticated"] = True
        session["role"] = "admin"
        return Script("window.location.href = '/';")
    else:
        return Div("Identifiants ou code 2FA incorrects.", style="color:#ef4444; font-weight:bold;")

@rt('/logout')
def get(session):
    session.clear()
    return RedirectResponse('/login')

@rt('/check_updates')
def get():
    try:
        res = requests.get("https://api.github.com/repos/Reivax69008/Aethas-Multi-IA/commits/main", timeout=3).json()
        remote_commit = res.get("sha", "")
        local_commit = ""
        if os.path.exists(".git/refs/heads/main"):
            with open(".git/refs/heads/main", "r") as f:
                local_commit = f.read().strip()
        
        if local_commit and remote_commit and remote_commit != local_commit:
            return Span("🚀 MAJ disponible (GitHub)", style="color:#fbbf24;")
        elif local_commit == remote_commit:
            return Span("🟢 Système à jour", style="color:#10b981;")
        else:
            return Span(f"🟢 Connecté (Git: {remote_commit[:7]})", style="color:#38bdf8;")
    except:
        return Span("⚪ Statut réseau inconnu", style="color:#94a3b8;")

# --- DOSSIERS & LOGS ---
os.makedirs("sessions", exist_ok=True)
os.makedirs("logs", exist_ok=True)
APP_LAUNCH_TIME = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = f"logs/AETHAS38_Run_{APP_LAUNCH_TIME}.log"

def log_event(session_id, category, action):
    sid_short = session_id[:8] if session_id and session_id != "system" else "SYSTEM"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] [Session:{sid_short}] [{category}] {action}\n")

# --- HISTORIQUE ---
HISTORY_FILE = "history.json"
def load_index():
    if not os.path.exists(HISTORY_FILE): return {}
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        try: 
            idx = json.load(f)
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
    log_event(session_id, "USER_ACTION", "Nouvelle session initialisée.")
    return session_id
def render_history_list():
    idx = load_index()
    sorted_sessions = sorted(idx.items(), key=lambda x: (not x[1].get('pinned', False), x[1]['title']), reverse=False)
    items = [Button("➕ Nouvelle Discussion", cls="history-btn w-full mb-3 text-center", style="background:#00e5ff; color:#0f172a; font-weight:bold;", hx_get="/session/new", hx_target="#chat-history")]
    for sid, data in sorted_sessions:
        pin_icon, pin_color = ("📍", "#10b981") if data.get('pinned') else ("📌", "#94a3b8")
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

# --- CATALOGUE ---
MODELS_DATA = []
def init_models():
    global MODELS_DATA
    MODELS_DATA = [
        {"id": "groq|llama3-8b-8192", "name": "Groq - Llama 3 (8B)", "is_free": True, "description": "Modèle ultra-rapide hébergé par Groq.", "architecture": {"modality": "text"}},
        {"id": "gemini|gemini-1.5-flash", "name": "Google - Gemini 1.5 Flash", "is_free": True, "description": "Modèle multimodal léger de Google.", "architecture": {"modality": "text/vision"}},
        {"id": "deepseek|deepseek-coder", "name": "DeepSeek - Coder", "is_free": False, "description": "Génération de code complexe.", "architecture": {"modality": "text/code"}}
    ]
    try:
        res = requests.get("https://openrouter.ai/api/v1/models", timeout=5)
        if res.status_code == 200:
            for m in res.json().get("data", []):
                m["id"], m["name"] = f"openrouter|{m['id']}", f"OR - {m['name']}"
                MODELS_DATA.append(m)
    except Exception as e: log_event("system", "ERROR", f"Erreur catalogue OR : {e}")
init_models()
def get_model_options(filter_type="all"):
    options = []
    for m in sorted(MODELS_DATA, key=lambda x: x['name']):
        is_free = m.get("is_free", "free" in m.get("id", "").lower())
        if filter_type == "free" and not is_free: continue
        if filter_type == "paid" and is_free: continue
        options.append(Option(f"{m['name']} ({'Gratuit' if is_free else 'Payant'})", value=m['id']))
    return Select(*options, name="model_id", cls="model-select", style="width: 100%;")

# --- MOTEUR IA ---
def get_budget():
    mgmt_key = os.getenv("OPENROUTER_MANAGEMENT_KEY")
    if not mgmt_key: return "Clé manquante"
    try:
        data = requests.get("https://openrouter.ai/api/v1/credits", headers={"Authorization": f"Bearer {mgmt_key}"}, timeout=5).json().get("data", {})
        return f"{data.get('total_credits', 0) - data.get('total_usage', 0):.4f} $"
    except: return "Erreur lecture"

def handle_api_error(session_id, provider, raw_error):
    log_event(session_id, "ERROR", f"API {provider} : {raw_error}")
    sys_prompt = "Tu es un assistant technique. Traduis cette erreur d'API en français."
    try:
        qwen_res = requests.post("http://localhost:11434/api/generate", json={"model": "qwen2.5-coder:7b", "prompt": f"{sys_prompt}\n\nErreur ({provider}): {raw_error}", "stream": False}, timeout=15).json()["response"]
        return f"⚠️ **Alerte Serveur ({provider})**\n{qwen_res}"
    except: return f"⚠️ Erreur brute ({provider}) : {raw_error}"

async def async_ask_llm(session_id, provider, actual_model, msg):
    return await asyncio.to_thread(ask_llm, session_id, provider, actual_model, msg)

def ask_llm(session_id, provider, actual_model, msg):
    log_event(session_id, "API_REQ", f"Interrogation : {provider} | Modèle : {actual_model}")
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
    except Exception as e: return handle_api_error(session_id, provider, str(e))

def pipeline_minecraft(session_id, raw_msg):
    log_event(session_id, "PIPELINE", "Local Minecraft")
    try:
        en_prompt = requests.post("http://localhost:11434/api/generate", json={"model": "qwen2.5-coder:7b", "prompt": f"Translate this Minecraft modding request into technical English. Return ONLY English text.\n\n{raw_msg}", "stream": False}).json()["response"]
        phuzzy_res = requests.post("http://localhost:11434/api/generate", json={"model": "phuzzy:latest", "prompt": en_prompt, "stream": False}).json()["response"]
        final_fr = requests.post("http://localhost:11434/api/generate", json={"model": "qwen2.5-coder:7b", "prompt": f"Traduis les explications techniques en français. NE TRADUIS PAS le code.\n\n{phuzzy_res}", "stream": False}).json()["response"]
        return final_fr, "Qwen ➔ Phuzzy ➔ Qwen"
    except Exception as e: return handle_api_error(session_id, "Ollama Local", str(e)), "Erreur Locale"

async def pipeline_consolidated(session_id, raw_msg):
    log_event(session_id, "PIPELINE", "Consolidation Multi-IA")
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
    except Exception as e: return handle_api_error(session_id, "Pipeline Multi-IA", str(e)), "Erreur Consolidation"

# --- ROUTES PRINCIPALES (PROTÉGÉES) ---
@rt('/session/new')
def get(session):
    if not session.get("authenticated"): return RedirectResponse('/login')
    sid = create_new_session()
    return Div(), Input(type="hidden", name="session_id", value=sid, id="current-session-id", hx_swap_oob="true"), render_history_list()

@rt('/session/load/{sid}')
def get(sid: str, session):
    if not session.get("authenticated"): return RedirectResponse('/login')
    log_event(sid, "USER_ACTION", "Chargement de la session.")
    messages = load_session_data(sid)
    bubbles = [Div(P("Vous", cls="msg-user"), Div(NotStr(f"{msg['user']}{msg.get('info_fichiers', '')}{msg.get('info_local', '')}"), cls="bubble-user"), P(f"AETHAS38 ({msg.get('nom_affichage', 'IA')})", cls="msg-ia"), Div(msg['ia'], cls="bubble-ia")) for msg in messages]
    return tuple(bubbles) + (Input(type="hidden", name="session_id", value=sid, id="current-session-id", hx_swap_oob="true"),)

@rt('/history/pin/{sid}')
def post_pin(sid: str, session):
    if not session.get("authenticated"): return RedirectResponse('/login')
    idx = load_index()
    if sid in idx:
        idx[sid]['pinned'] = not idx[sid].get('pinned', False)
        save_index(idx)
        log_event(sid, "USER_ACTION", "Épinglage modifié.")
    return render_history_list()

@rt('/history/rename/{sid}')
def post_rename(sid: str, title: str, session):
    if not session.get("authenticated"): return RedirectResponse('/login')
    idx = load_index()
    if sid in idx:
        idx[sid]['title'] = title
        save_index(idx)
        log_event(sid, "USER_ACTION", f"Renommé en: {title}")
    return render_history_list()

@rt('/history/delete/{sid}')
def post_delete(sid: str, session):
    if not session.get("authenticated"): return RedirectResponse('/login')
    idx = load_index()
    if sid in idx:
        del idx[sid]
        save_index(idx)
        if os.path.exists(f"sessions/{sid}.json"): os.remove(f"sessions/{sid}.json")
        log_event(sid, "USER_ACTION", "Session supprimée.")
    return render_history_list()

@rt('/export_models')
def get(session):
    if not session.get("authenticated"): return RedirectResponse('/login')
    log_event("system", "SYSTEM", "Export catalogue.")
    txt_content = f"=== CATALOGUE ({datetime.now().strftime('%d/%m/%Y %H:%M:%S')}) ===\n\n"
    for m in MODELS_DATA: txt_content += f"Nom : {m.get('name')}\nID : {m.get('id')}\nDescription : {str(m.get('description', ''))[:150]}\n{'-'*60}\n"
    return Response(txt_content, media_type="text/plain")

@rt('/')
def get(session):
    if not session.get("authenticated"): return RedirectResponse('/login')
    
    session_id = create_new_session()
    return Title("AETHAS38 Multi-IA"), Body(
        Div(
            Div(
                H2("AETHAS 38", style="color:#00e5ff; font-weight:bold; font-size:24px;"),
                P("Tech Core - Multi IA", style="color:#a855f7; margin-bottom: 20px;"),
                
                Div(
                    P("STATUT SYSTÈME", style="color:#94a3b8; font-size:10px; font-weight:bold; margin-bottom:5px;"),
                    Div("⏳ Vérification GitHub...", hx_get="/check_updates", hx_trigger="load", style="font-size:12px; font-weight:bold; margin-bottom:15px;"),
                ),

                Div(
                    H3("Historique de Code", style="color:#94a3b8; font-size:12px; font-weight:bold; margin-bottom:10px;"),
                    render_history_list(),
                    style="display:flex; flex-direction:column; flex-grow:1; margin-bottom: 10px; overflow:hidden;"
                ),
                Button("📥 Exporter Modèles (.txt)", type="button", cls="export-btn w-full mt-2", onclick="downloadModels()"),
                A("Déconnexion", href="/logout", cls="export-btn w-full mt-2", style="color:#ef4444; border-color:#ef4444; margin-bottom:10px;"),
                Div(
                    P("BUDGET OPENROUTER", style="color:#94a3b8; font-size:10px; font-weight:bold; margin-bottom:5px;"),
                    P(get_budget(), id="budget-display", style="color:#10b981; font-size:18px; font-weight:bold;"),
                    cls="budget-box"
                ),
                cls="sidebar"
            ),
            Div(
                Div(id="chat-history", cls="chat-container"),
                Div("⚙️ Traitement de l'Architecture IA en cours...", id="loading-tracker", cls="htmx-indicator"),
                
                Form(
                    Input(type="hidden", name="session_id", value=session_id, id="current-session-id"),
                    Div(
                        Label(Input(type="radio", name="context_type", value="generic", checked=True, onchange="updateUI()"), " 💻 Code Générique"),
                        Label(Input(type="radio", name="context_type", value="consolidated", onchange="updateUI()"), " 🧠 Consolidation"),
                        Label(Input(type="radio", name="context_type", value="minecraft", onchange="updateUI()"), " ⛏ Minecraft"),
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
def get(filter_type: str, session):
    if not session.get("authenticated"): return RedirectResponse('/login')
    return get_model_options(filter_type)

@rt('/chat')
async def post(msg: str, model_id: str, session_id: str, session, context_type: str = "generic", fichiers: list[UploadFile] = None):
    if not session.get("authenticated"): return RedirectResponse('/login')
    log_event(session_id, "USER_ACTION", f"Message ({context_type})")
    
    files_context, noms_fichiers = "", []
    if fichiers:
        for f in fichiers:
            if f.filename:
                noms_fichiers.append(f.filename)
                try: files_context += f"\n--- {f.filename} ---\n{(await f.read()).decode('utf-8')}\n"
                except: files_context += f"\n--- {f.filename} (Binaire ignoré) ---\n"
    
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

    info_fichiers = f"<br><span style='color:#a855f7; font-size:10px;'>📎 {len(noms_fichiers)} fichier(s)</span>" if noms_fichiers else ""
    info_local = f"<br><span style='color:#38bdf8; font-size:10px;'>⚙️ Pipeline : {pipeline_info}</span>"
    
    session_data = load_session_data(session_id)
    session_data.append({"user": msg, "ia": ia_reponse, "nom_affichage": nom_affichage, "info_fichiers": info_fichiers, "info_local": info_local})
    save_session_data(session_id, session_data)

    chat_bubble = Div(P("Vous", cls="msg-user"), Div(NotStr(f"{msg}{info_fichiers}{info_local}"), cls="bubble-user"), P(f"AETHAS38 ({nom_affichage})", cls="msg-ia"), Div(ia_reponse, cls="bubble-ia"))
    return chat_bubble, P(get_budget(), id="budget-display", style="color:#10b981; font-size:18px; font-weight:bold;", hx_swap_oob="true")

if __name__ == '__main__':
    serve(port=5001)