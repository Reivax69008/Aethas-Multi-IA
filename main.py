from fasthtml.common import *
import os
import requests
import base64
from dotenv import load_dotenv

load_dotenv()

# --- 1. GESTION DU CATALOGUE (Identique) ---
MODELS_DATA = []

def init_models():
    global MODELS_DATA
    MODELS_DATA = [
        {"id": "groq|llama3-8b-8192", "name": "Groq - Llama 3 (8B)", "is_free": True},
        {"id": "groq|llama3-70b-8192", "name": "Groq - Llama 3 (70B)", "is_free": True},
        {"id": "groq|mixtral-8x7b-32768", "name": "Groq - Mixtral 8x7B", "is_free": True},
        {"id": "gemini|gemini-1.5-flash", "name": "Google - Gemini 1.5 Flash", "is_free": True},
        {"id": "gemini|gemini-1.5-pro", "name": "Google - Gemini 1.5 Pro", "is_free": False},
        {"id": "deepseek|deepseek-chat", "name": "DeepSeek - V3", "is_free": False},
        {"id": "deepseek|deepseek-coder", "name": "DeepSeek - Coder", "is_free": False},
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
    try:
        pricing = model.get("pricing", {})
        if float(pricing.get("prompt", -1)) == 0.0 and float(pricing.get("completion", -1)) == 0.0: return True
    except: pass
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


# --- 2. MOTEUR D'INTELLIGENCE & FICHIERS ---

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

def optimize_prompt_with_ollama(raw_msg, files_context):
    """Envoie la requête brute à Qwen2.5 local pour générer un prompt expert parfait."""
    system_prompt = "Tu es un expert en ingénierie logicielle. Reformule la demande de l'utilisateur pour la rendre parfaite, technique et explicite pour un LLM codeur. Retourne UNIQUEMENT le prompt optimisé, sans bavardage."
    full_request = f"Fichiers fournis : {files_context}\n\nDemande utilisateur : {raw_msg}" if files_context else raw_msg
    
    try:
        res = requests.post("http://localhost:11434/api/generate", json={
            "model": "qwen2.5-coder:7b",
            "prompt": f"{system_prompt}\n\n{full_request}",
            "stream": False
        }, timeout=30)
        if res.status_code == 200:
            return res.json()["response"]
    except Exception as e:
        print(f"Erreur Ollama : {e}")
        return full_request # Fallback sur le prompt brut si Ollama est éteint
    return full_request

def ask_llm(provider, model, msg):
    """Aiguille vers les API distantes."""
    try:
        if provider == "openrouter":
            key = os.getenv("OPENROUTER_API_KEY")
            res = requests.post("https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": msg}]})
            return res.json()["choices"][0]["message"]["content"]
            
        elif provider == "groq":
            key = os.getenv("GROQ_API_KEY")
            res = requests.post("https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": msg}]})
            return res.json()["choices"][0]["message"]["content"]
            
        elif provider == "gemini":
            key = os.getenv("GEMINI_API_KEY")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            res = requests.post(url, headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": msg}]}]})
            return res.json()["candidates"][0]["content"]["parts"][0]["text"]
            
        elif provider == "deepseek":
            key = os.getenv("DEEPSEEK_API_KEY")
            res = requests.post("https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": msg}]})
            return res.json()["choices"][0]["message"]["content"]
            
        elif provider == "mistral":
            key = os.getenv("MISTRAL_API_KEY")
            res = requests.post("https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": msg}]})
            return res.json()["choices"][0]["message"]["content"]

        return f"Fournisseur API non reconnu : {provider}"
    except Exception as e:
        return f"Erreur API ({provider}) : {str(e)}"


# --- 3. INTERFACE UTILISATEUR & SERVEUR WEB ---

theme_hdrs = [
    Script(src="https://cdn.tailwindcss.com"),
    Script(src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"),
    Script(src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"),
    Link(rel="stylesheet", href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/tokyo-night-dark.min.css"),
    Style("""
        body { background-color: #0f172a; color: #f8fafc; font-family: system-ui, sans-serif; }
        .sidebar { background-color: #1e293b; border-right: 1px solid #333; height: 100vh; padding: 20px; display: flex; flex-direction: column;}
        .main-content { padding: 20px; height: 100vh; display: flex; flex-direction: column; position: relative;}
        .chat-container { flex-grow: 1; overflow-y: auto; margin-bottom: 20px; border: 1px solid #333; padding: 15px; border-radius: 8px; background: #151e2e; }
        .input-row { display: flex; gap: 10px; align-items: flex-end; width: 100%; background: #1e293b; padding: 10px; border-radius: 10px; border: 1px solid #333;}
        .input-box { flex-grow: 1; padding: 12px; border-radius: 5px; background: #2a2a35; border: 1px solid #444; color: white; outline: none; }
        .file-upload-btn { background: #2a2a35; border: 1px solid #444; color: #94a3b8; padding: 12px; border-radius: 5px; cursor: pointer; transition: 0.2s;}
        .file-upload-btn:hover { background: #38bdf8; color: #0f172a; }
        .model-select { padding: 12px; border-radius: 5px; background: #2a2a35; border: 1px solid #444; color: #00e5ff; outline: none; font-weight: bold; cursor: pointer;}
        .send-btn { padding: 12px 24px; border-radius: 5px; background: #00e5ff; color: #0f172a; font-weight: bold; cursor: pointer; border: none; transition: 0.2s; }
        
        .msg-user { color: #00e5ff; font-size: 12px; font-weight: bold; margin-bottom: 2px; margin-top: 15px;}
        .msg-ia { color: #a855f7; font-size: 12px; font-weight: bold; margin-bottom: 2px; margin-top: 15px;}
        .bubble-user { background: #1e293b; padding: 10px; border-radius: 5px; display: inline-block; color: white; border: 1px solid #333;}
        .bubble-ia { background: #1e293b; padding: 15px; border-radius: 8px; display: block; color: #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
        
        /* Outils Code (Inspiration Gemini) */
        .bubble-ia pre { background: #111827; padding: 15px; border-radius: 8px; margin-top: 10px; position: relative; border: 1px solid #333;}
        .code-toolbar { display: flex; justify-content: flex-end; gap: 10px; background: #1f2937; padding: 5px 10px; border-radius: 8px 8px 0 0; border-bottom: 1px solid #333; margin: -15px -15px 10px -15px;}
        .code-btn { background: none; border: none; color: #94a3b8; font-size: 12px; cursor: pointer; display: flex; align-items: center; gap: 5px;}
        .code-btn:hover { color: #00e5ff; }
        
        /* Fenêtre de progression (HTMX) */
        .htmx-indicator { display: none; position: absolute; bottom: 100px; left: 50%; transform: translateX(-50%); background: rgba(15, 23, 42, 0.9); border: 1px solid #00e5ff; padding: 15px 30px; border-radius: 50px; color: #00e5ff; font-weight: bold; box-shadow: 0 0 20px rgba(0, 229, 255, 0.2); backdrop-filter: blur(5px);}
        .htmx-request .htmx-indicator { display: block; }
    """),
    
    Script("""
        htmx.onLoad(function(content) {
            content.querySelectorAll('.bubble-ia:not(.rendered)').forEach(function(el) {
                el.innerHTML = marked.parse(el.textContent);
                el.classList.add('rendered');
                
                // Injection des outils de code (Copier / Télécharger)
                el.querySelectorAll('pre code').forEach((block) => {
                    hljs.highlightElement(block);
                    
                    let pre = block.parentElement;
                    let toolbar = document.createElement('div');
                    toolbar.className = 'code-toolbar';
                    
                    // Bouton Copier
                    let copyBtn = document.createElement('button');
                    copyBtn.className = 'code-btn';
                    copyBtn.innerHTML = '📋 Copier';
                    copyBtn.onclick = () => { navigator.clipboard.writeText(block.innerText); copyBtn.innerHTML = '✅ Copié!'; setTimeout(()=> copyBtn.innerHTML = '📋 Copier', 2000); };
                    
                    // Bouton Télécharger
                    let dlBtn = document.createElement('button');
                    dlBtn.className = 'code-btn';
                    dlBtn.innerHTML = '💾 .txt';
                    dlBtn.onclick = () => {
                        let blob = new Blob([block.innerText], {type: 'text/plain'});
                        let a = document.createElement('a');
                        a.href = URL.createObjectURL(blob);
                        a.download = 'code_aethas38.txt';
                        a.click();
                    };
                    
                    toolbar.appendChild(copyBtn);
                    toolbar.appendChild(dlBtn);
                    pre.insertBefore(toolbar, block);
                });
                
                let chat = document.getElementById('chat-history');
                chat.scrollTop = chat.scrollHeight;
            });
        });
    """)
]

app, rt = fast_app(hdrs=theme_hdrs)

@rt('/')
def get():
    return Title("AETHAS38 Multi-IA"), Body(
        Div(
            Div(
                H2("AETHAS 38", style="color:#00e5ff; font-weight:bold; font-size:24px;"),
                P("Tech Core - Multi IA", style="color:#a855f7; margin-bottom: 20px;"),
                Div(
                    P("BUDGET OPENROUTER", style="color:#94a3b8; font-size:10px; font-weight:bold; margin-bottom:5px;"),
                    P(get_budget(), id="budget-display", style="color:#10b981; font-size:18px; font-weight:bold;"),
                    cls="budget-box"
                ),
                cls="sidebar"
            ),
            Div(
                Div(id="chat-history", cls="chat-container"),
                
                # Fenêtre de progression qui s'affiche pendant le traitement HTMX
                Div("⚙️ Traitement de la requête en cours (Qwen + LLM)...", id="loading-tracker", cls="htmx-indicator"),
                
                Form(
                    Div(
                        Select(
                            Option("Tous les modèles", value="all"), Option("Gratuits", value="free"), Option("Payants", value="paid"),
                            name="filter_type", cls="model-select", hx_get="/filter_models", hx_target="#model-select-wrapper", style="width: 250px;"
                        ),
                        Div(get_model_options("all"), id="model-select-wrapper", style="flex-grow: 1;"),
                        cls="flex gap-2 mb-2 w-full"
                    ),
                    Div(
                        # Bouton d'upload de fichiers multiples
                        Input(type="file", name="fichiers", id="file-upload", multiple=True, style="display:none;"),
                        Label("📎 Fichiers", _for="file-upload", cls="file-upload-btn"),
                        
                        Input(type="text", name="msg", placeholder="Instructions pour le code...", cls="input-box", required=True),
                        Button("Envoyer", type="submit", cls="send-btn"),
                        cls="input-row"
                    ),
                    hx_post="/chat", hx_target="#chat-history", hx_swap="beforeend", hx_indicator="#loading-tracker", enctype="multipart/form-data"
                ),
                cls="main-content"
            ),
            style="display: grid; grid-template-columns: 250px 1fr;"
        )
    )

@rt('/filter_models')
def get(filter_type: str): return get_model_options(filter_type)

@rt('/chat')
async def post(msg: str, model_id: str, fichiers: list[UploadFile] = None):
    # 1. Traitement des fichiers (Extraction de texte pour les formats lisibles)
    files_context = ""
    noms_fichiers = []
    if fichiers:
        for f in fichiers:
            if f.filename:
                noms_fichiers.append(f.filename)
                content = await f.read()
                try:
                    # Tente de lire comme du texte (code, txt, csv, md)
                    text_content = content.decode('utf-8')
                    files_context += f"--- Fichier: {f.filename} ---\n{text_content}\n\n"
                except:
                    files_context += f"--- Fichier binaire non lisible: {f.filename} ---\n\n"

    # 2. Pipeline Optimisation (Ollama Qwen2.5) -> LLM Distant
    optimized_prompt = optimize_prompt_with_ollama(msg, files_context)
    
    parts = model_id.split("|", 1)
    provider, actual_model = parts[0], parts[1] if len(parts) > 1 else model_id
    
    # Exécution finale
    ia_reponse = ask_llm(provider, actual_model, optimized_prompt)
    nom_affichage = f"{provider.capitalize()} - {actual_model.split('/')[-1]}"

    # Affichage utilisateur enrichi
    info_fichiers = f"<br><span style='color:#a855f7; font-size:10px;'>📎 Fichiers joints : {', '.join(noms_fichiers)}</span>" if noms_fichiers else ""
    info_qwen = "<br><span style='color:#38bdf8; font-size:10px;'>⚙️ Prompt optimisé par Ollama (Qwen2.5)</span>"
    
    chat_bubble = Div(
        P("Vous", cls="msg-user"),
        Div(NotStr(f"{msg}{info_fichiers}{info_qwen}"), cls="bubble-user"),
        P(f"AETHAS38 ({nom_affichage})", cls="msg-ia"),
        Div(ia_reponse, cls="bubble-ia")
    )
    
    updated_budget = P(get_budget(), id="budget-display", style="color:#10b981; font-size:18px; font-weight:bold;", hx_swap_oob="true")
    
    return chat_bubble, updated_budget

if __name__ == '__main__':
    serve(port=5001)