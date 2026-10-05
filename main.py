from fasthtml.common import *
import os
import requests
import json
import uuid
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# --- 1. GESTION DE L'HISTORIQUE ---
HISTORY_FILE = "history.json"

def load_history():
    if not os.path.exists(HISTORY_FILE): return {}
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        try: return json.load(f)
        except: return {}

def save_history(history_data):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history_data, f, indent=4, ensure_ascii=False)

def create_new_session():
    session_id = str(uuid.uuid4())
    history = load_history()
    history[session_id] = {
        "title": f"Discussion du {datetime.now().strftime('%d/%m %H:%M')}",
        "pinned": False,
        "messages": []
    }
    save_history(history)
    return session_id


# --- 2. GESTION DU CATALOGUE ---
MODELS_DATA = []

def init_models():
    global MODELS_DATA
    MODELS_DATA = [
        {"id": "groq|llama3-8b-8192", "name": "Groq - Llama 3 (8B)", "is_free": True},
        {"id": "gemini|gemini-1.5-flash", "name": "Google - Gemini 1.5 Flash", "is_free": True},
        {"id": "deepseek|deepseek-chat", "name": "DeepSeek - V3", "is_free": False},
        {"id": "mistral|open-mistral-nemo", "name": "Mistral - Nemo", "is_free": True},
    ]
    try:
        res = requests.get("https://openrouter.ai/api/v1/models", timeout=5)
        if res.status_code == 200:
            for m in res.json().get("data", []):
                m["id"] = f"openrouter|{m['id']}"
                m["name"] = f"OR - {m['name']}"
                MODELS_DATA.append(m)
    except: pass

init_models()

def check_if_free(model):
    if "is_free" in model: return model["is_free"]
    if "free" in model.get("id", "").lower(): return True
    return False

def get_model_options(filter_type="all"):
    options = []
    for m in sorted(MODELS_DATA, key=lambda x: x['name']):
        is_free = check_if_free(m)
        if filter_type == "free" and not is_free: continue
        if filter_type == "paid" and is_free: continue
        tag = "Gratuit" if is_free else "Payant"
        options.append(Option(f"{m['name']} ({tag})", value=m['id']))
    return Select(*options, name="model_id", cls="model-select", style="width: 100%;")


# --- 3. MOTEUR D'INTELLIGENCE & PIPELINE MINECRAFT ---
def get_budget():
    mgmt_key = os.getenv("OPENROUTER_MANAGEMENT_KEY")
    if not mgmt_key: return "Clé manquante"
    try:
        res = requests.get("https://openrouter.ai/api/v1/credits", headers={"Authorization": f"Bearer {mgmt_key}"}, timeout=5)
        if res.status_code == 200:
            data = res.json().get("data", {})
            return f"{data.get('total_credits', 0) - data.get('total_usage', 0):.4f} $"
    except: pass
    return "Erreur lecture"

def pipeline_minecraft(raw_msg):
    """Chaînage: Qwen (Fr->En) -> Phuzzy -> Qwen (En->Fr)"""
    try:
        # Étape 1 : Traduction et optimisation (Qwen)
        sys_in = "Translate and optimize this Minecraft modding request into a highly technical English prompt. Return ONLY the English text."
        en_prompt = requests.post("http://localhost:11434/api/generate", json={"model": "qwen2.5-coder:7b", "prompt": f"{sys_in}\n\n{raw_msg}", "stream": False}).json()["response"]
        
        # Étape 2 : Génération de l'expertise (Phuzzy)
        phuzzy_res = requests.post("http://localhost:11434/api/generate", json={"model": "phuzzy/minecraft", "prompt": en_prompt, "stream": False}).json()["response"]
        
        # Étape 3 : Retraduction en français (Qwen)
        sys_out = "Traduis cette réponse technique en français. IMPORTANT : Ne traduis SURTOUT PAS les blocs de code, les noms de variables, ou les commandes Minecraft."
        final_fr = requests.post("http://localhost:11434/api/generate", json={"model": "qwen2.5-coder:7b", "prompt": f"{sys_out}\n\n{phuzzy_res}", "stream": False}).json()["response"]
        
        return final_fr, "Qwen ➔ Phuzzy ➔ Qwen"
    except Exception as e:
        return f"Erreur Pipeline Minecraft: {e}", "Erreur"

def pipeline_generic(raw_msg, provider, actual_model):
    """Optimisation Qwen -> Modèle Distant"""
    sys_opt = "Tu es un expert en ingénierie logicielle. Optimise cette demande pour un LLM codeur. Retourne UNIQUEMENT le prompt."
    try:
        opt_prompt = requests.post("http://localhost:11434/api/generate", json={"model": "qwen2.5-coder:7b", "prompt": f"{sys_opt}\n\n{raw_msg}", "stream": False}).json()["response"]
    except:
        opt_prompt = raw_msg
        
    try:
        if provider == "openrouter":
            key = os.getenv("OPENROUTER_API_KEY")
            res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {key}"}, json={"model": actual_model, "messages": [{"role": "user", "content": opt_prompt}]})
            return res.json()["choices"][0]["message"]["content"]
        elif provider == "groq":
            key = os.getenv("GROQ_API_KEY")
            res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {key}"}, json={"model": actual_model, "messages": [{"role": "user", "content": opt_prompt}]})
            return res.json()["choices"][0]["message"]["content"]
        elif provider == "gemini":
            key = os.getenv("GEMINI_API_KEY")
            res = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{actual_model}:generateContent?key={key}", json={"contents": [{"parts": [{"text": opt_prompt}]}]})
            return res.json()["candidates"][0]["content"]["parts"][0]["text"]
        return f"API non reconnue : {provider}"
    except Exception as e:
        return f"Erreur API ({provider}) : {e}"


# --- 4. INTERFACE UTILISATEUR & SERVEUR WEB ---
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
        .model-select { padding: 12px; border-radius: 5px; background: #2a2a35; border: 1px solid #444; color: #00e5ff; outline: none; font-weight: bold; cursor: pointer;}
        .send-btn { padding: 12px 24px; border-radius: 5px; background: #00e5ff; color: #0f172a; font-weight: bold; cursor: pointer; border: none; transition: 0.2s; }
        .msg-user { color: #00e5ff; font-size: 12px; font-weight: bold; margin-bottom: 2px; margin-top: 15px;}
        .msg-ia { color: #a855f7; font-size: 12px; font-weight: bold; margin-bottom: 2px; margin-top: 15px;}
        .bubble-user { background: #1e293b; padding: 10px; border-radius: 5px; display: inline-block; color: white; border: 1px solid #333;}
        .bubble-ia { background: #1e293b; padding: 15px; border-radius: 8px; display: block; color: #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
        .bubble-ia pre { background: #111827; padding: 15px; border-radius: 8px; margin-top: 10px; position: relative; border: 1px solid #333;}
        .context-radio-group { display: flex; gap: 15px; background: #1e293b; padding: 10px 15px; border-radius: 8px; border: 1px solid #333; margin-bottom: 10px; width: fit-content; }
        .htmx-indicator { display: none; position: absolute; bottom: 120px; left: 50%; transform: translateX(-50%); background: rgba(15, 23, 42, 0.9); border: 1px solid #00e5ff; padding: 15px 30px; border-radius: 50px; color: #00e5ff; font-weight: bold;}
        .htmx-request .htmx-indicator { display: block; }
        .history-btn { background: #2a2a35; color: #e2e8f0; border: 1px solid #444; padding: 8px; border-radius: 5px; cursor: pointer; text-align: left; margin-bottom: 5px; font-size: 13px; }
        .history-btn:hover { background: #38bdf8; color: #0f172a; }
    """),
    Script("""
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

@rt('/')
def get():
    session_id = create_new_session()
    history = load_history()
    
    # Rendu de la liste d'historique
    history_list = []
    for sid, data in sorted(history.items(), key=lambda x: x[1]['title'], reverse=True):
        pin_icon = "📌 " if data.get('pinned') else "💬 "
        history_list.append(Button(pin_icon + data['title'], cls="history-btn w-full"))

    return Title("AETHAS38 Multi-IA"), Body(
        Div(
            Div(
                H2("AETHAS 38", style="color:#00e5ff; font-weight:bold; font-size:24px;"),
                P("Tech Core - Multi IA", style="color:#a855f7; margin-bottom: 20px;"),
                
                # Zone Historique
                Div(
                    H3("Historique", style="color:#94a3b8; font-size:12px; font-weight:bold; margin-bottom:10px;"),
                    Div(*history_list, style="flex-grow: 1; overflow-y: auto;"),
                    style="display:flex; flex-direction:column; flex-grow:1; margin-bottom: 10px;"
                ),
                
                Div(
                    P("BUDGET OPENROUTER", style="color:#94a3b8; font-size:10px; font-weight:bold; margin-bottom:5px;"),
                    P(get_budget(), id="budget-display", style="color:#10b981; font-size:18px; font-weight:bold;"),
                    cls="budget-box"
                ),
                cls="sidebar"
            ),
            Div(
                Div(id="chat-history", cls="chat-container"),
                Div("⚙️ Traitement IA en cours...", id="loading-tracker", cls="htmx-indicator"),
                
                Form(
                    Input(type="hidden", name="session_id", value=session_id),
                    Div(
                        Label(Input(type="radio", name="context_type", value="generic", checked=True), " 💻 Code Générique (Local+Distant)"),
                        Label(Input(type="radio", name="context_type", value="minecraft"), " ⛏️ Minecraft (100% Local Phuzzy)"),
                        cls="context-radio-group text-sm text-white flex gap-4"
                    ),
                    Div(
                        Select(Option("Tous les modèles", value="all"), Option("Gratuits", value="free"), Option("Payants", value="paid"), name="filter_type", cls="model-select", hx_get="/filter_models", hx_target="#model-select-wrapper", style="width: 250px;"),
                        Div(get_model_options("all"), id="model-select-wrapper", style="flex-grow: 1;"),
                        cls="flex gap-2 mb-2 w-full"
                    ),
                    Div(
                        Input(type="text", name="msg", placeholder="Instructions...", cls="input-box", required=True),
                        Button("Envoyer", type="submit", cls="send-btn"),
                        cls="input-row"
                    ),
                    hx_post="/chat", hx_target="#chat-history", hx_swap="beforeend", hx_indicator="#loading-tracker"
                ),
                cls="main-content"
            ),
            style="display: grid; grid-template-columns: 250px 1fr;"
        )
    )

@rt('/filter_models')
def get(filter_type: str): return get_model_options(filter_type)

@rt('/chat')
async def post(msg: str, model_id: str, session_id: str, context_type: str = "generic"):
    
    # 1. Sélection du traitement selon le contexte
    if context_type == "minecraft":
        ia_reponse, pipeline_info = pipeline_minecraft(msg)
        nom_affichage = "Local - Phuzzy/Minecraft"
    else:
        parts = model_id.split("|", 1)
        provider, actual_model = parts[0], parts[1] if len(parts) > 1 else model_id
        ia_reponse = pipeline_generic(msg, provider, actual_model)
        nom_affichage = f"{provider.capitalize()} - {actual_model.split('/')[-1]}"
        pipeline_info = "Qwen ➔ API Distante"

    # 2. Sauvegarde dans l'historique
    history = load_history()
    if session_id in history:
        history[session_id]["messages"].append({"user": msg, "ia": ia_reponse})
        save_history(history)

    # 3. Affichage
    info_local = f"<br><span style='color:#38bdf8; font-size:10px;'>⚙️ Pipeline : {pipeline_info}</span>"
    chat_bubble = Div(
        P("Vous", cls="msg-user"), Div(NotStr(f"{msg}{info_local}"), cls="bubble-user"),
        P(f"AETHAS38 ({nom_affichage})", cls="msg-ia"), Div(ia_reponse, cls="bubble-ia")
    )
    
    updated_budget = P(get_budget(), id="budget-display", style="color:#10b981; font-size:18px; font-weight:bold;", hx_swap_oob="true")
    return chat_bubble, updated_budget

if __name__ == '__main__':
    serve(port=5001)