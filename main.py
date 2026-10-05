from fasthtml.common import *
import os
import requests
from dotenv import load_dotenv

load_dotenv()

# --- 1. GESTION DES MODELES (Mise en cache au démarrage) ---
MODELS_DATA = []

def init_models():
    """Télécharge la liste complète au lancement du serveur et la stocke en mémoire."""
    global MODELS_DATA
    try:
        res = requests.get("https://openrouter.ai/api/v1/models", timeout=5)
        if res.status_code == 200:
            MODELS_DATA = res.json().get("data", [])
    except:
        pass
    
    if not MODELS_DATA: # Sécurité si le réseau coupe au démarrage
        MODELS_DATA = [
            {"id": "meta-llama/llama-3.1-8b-instruct:free", "name": "Llama 3.1 8B", "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet", "pricing": {"prompt": "1", "completion": "1"}}
        ]

init_models()

def check_if_free(model):
    """Vérifie si le modèle est gratuit en analysant ses tarifs OpenRouter."""
    if "free" in model.get("id", "").lower():
        return True
    try:
        pricing = model.get("pricing", {})
        prompt = float(pricing.get("prompt", -1))
        completion = float(pricing.get("completion", -1))
        # Si le prix de lecture et d'écriture est à 0, c'est 100% gratuit
        if prompt == 0.0 and completion == 0.0:
            return True
    except:
        pass
    return False

def get_model_options(filter_type="all"):
    """Génère la liste déroulante des modèles avec leur étiquette, selon le filtre."""
    options = []
    for m in sorted(MODELS_DATA, key=lambda x: x['name']):
        is_free = check_if_free(m)
        
        # Application du filtre (Tous / Gratuits / Payants)
        if filter_type == "free" and not is_free: continue
        if filter_type == "paid" and is_free: continue
        
        # Ajout de l'étiquette
        tag = "Gratuit" if is_free else "Payant"
        label = f"{m['name']} ({tag})"
        
        options.append(Option(label, value=m['id']))
        
    return Select(*options, name="model_id", cls="model-select", style="width: 100%;")


# --- 2. GESTION DU BUDGET ---
def get_budget():
    mgmt_key = os.getenv("OPENROUTER_MANAGEMENT_KEY")
    if not mgmt_key: return "Clé manquante"
    try:
        res = requests.get("https://openrouter.ai/api/v1/credits", headers={"Authorization": f"Bearer {mgmt_key}"}, timeout=5)
        if res.status_code == 200:
            data = res.json().get("data", {})
            return f"{data.get('total_credits', 0) - data.get('total_usage', 0):.4f} $"
    except:
        pass
    return "Erreur lecture"


# --- 3. INTERFACE UTILISATEUR (UI) ---
theme_hdrs = [
    Script(src="https://cdn.tailwindcss.com"),
    Style("""
        body { background-color: #0f172a; color: #f8fafc; font-family: system-ui, sans-serif; }
        .sidebar { background-color: #1e293b; border-right: 1px solid #333; height: 100vh; padding: 20px; display: flex; flex-direction: column;}
        .main-content { padding: 20px; height: 100vh; display: flex; flex-direction: column; }
        .chat-container { flex-grow: 1; overflow-y: auto; margin-bottom: 20px; border: 1px solid #333; padding: 15px; border-radius: 8px; background: #151e2e; }
        .input-row { display: flex; gap: 10px; align-items: flex-end; width: 100%; }
        .input-box { flex-grow: 1; padding: 12px; border-radius: 5px; background: #2a2a35; border: 1px solid #444; color: white; outline: none; }
        .model-select { padding: 12px; border-radius: 5px; background: #2a2a35; border: 1px solid #444; color: #00e5ff; outline: none; font-weight: bold; cursor: pointer;}
        .send-btn { padding: 12px 24px; border-radius: 5px; background: #00e5ff; color: #0f172a; font-weight: bold; cursor: pointer; border: none; transition: 0.2s; }
        .send-btn:hover { background: #38bdf8; }
        .msg-user { color: #00e5ff; font-size: 12px; font-weight: bold; margin-bottom: 2px; margin-top: 15px;}
        .msg-ia { color: #a855f7; font-size: 12px; font-weight: bold; margin-bottom: 2px; margin-top: 15px;}
        .bubble-user { background: #1e293b; padding: 10px; border-radius: 5px; display: inline-block; color: white; }
        .bubble-ia { background: #2a2a35; padding: 10px; border-radius: 5px; display: inline-block; color: #e2e8f0; border-left: 3px solid #a855f7; white-space: pre-wrap; }
        .budget-box { background: #151e2e; padding: 15px; border-radius: 8px; border: 1px solid #333; margin-top: auto; }
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
                Form(
                    # Ligne 1 : Filtre et Liste dynamique des modèles
                    Div(
                        Select(
                            Option("Tous les modèles", value="all"),
                            Option("Gratuits uniquement", value="free"),
                            Option("Payants uniquement", value="paid"),
                            name="filter_type",
                            cls="model-select",
                            hx_get="/filter_models",           # Demande la mise à jour à HTMX...
                            hx_target="#model-select-wrapper", # ...pour l'injecter dans cet élément
                            hx_swap="innerHTML",
                            style="width: 250px;"
                        ),
                        Div(get_model_options("all"), id="model-select-wrapper", style="flex-grow: 1;"),
                        cls="flex gap-2 mb-2 w-full"
                    ),
                    # Ligne 2 : Saisie texte et Bouton d'envoi
                    Div(
                        Input(type="text", name="msg", placeholder="Demandez moi de coder quelque chose...", cls="input-box", required=True),
                        Button("Envoyer", type="submit", cls="send-btn"),
                        cls="input-row"
                    ),
                    hx_post="/chat", 
                    hx_target="#chat-history", 
                    hx_swap="beforeend"
                ),
                cls="main-content"
            ),
            style="display: grid; grid-template-columns: 250px 1fr;"
        )
    )


# --- 4. ROUTES DYNAMIQUES (HTMX) ---

@rt('/filter_models')
def get(filter_type: str):
    """Route appelée automatiquement quand on change le filtre (Gratuit/Payant)"""
    return get_model_options(filter_type)

@rt('/chat')
def post(msg: str, model_id: str):
    api_key = os.getenv("OPENROUTER_API_KEY")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": msg}]
    }
    
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        if response.status_code == 200:
            ia_reponse = response.json()["choices"][0]["message"]["content"]
        else:
            ia_reponse = f"Erreur API ({response.status_code}) : {response.text}"
    except Exception as e:
        ia_reponse = f"Erreur réseau : {e}"

    nom_modele = model_id.split('/')[-1]

    # 1. On prépare la bulle de chat
    chat_bubble = Div(
        P("Vous", cls="msg-user"),
        Div(msg, cls="bubble-user"),
        P(f"AETHAS38 ({nom_modele})", cls="msg-ia"),
        Div(ia_reponse, cls="bubble-ia")
    )
    
    # 2. On recalcule le budget financier et on lui ordonne de s'actualiser avec hx_swap_oob
    updated_budget = P(get_budget(), id="budget-display", style="color:#10b981; font-size:18px; font-weight:bold;", hx_swap_oob="true")

    return chat_bubble, updated_budget

if __name__ == '__main__':
    serve(port=5001)