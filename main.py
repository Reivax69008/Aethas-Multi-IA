from fasthtml.common import *
import os
import requests
from dotenv import load_dotenv

load_dotenv()

# En-têtes et CSS pour le style AETHAS38
theme_hdrs = [
    Script(src="https://cdn.tailwindcss.com"),
    Style("""
        body { background-color: #0f172a; color: #f8fafc; font-family: system-ui, sans-serif; }
        .sidebar { background-color: #1e293b; border-right: 1px solid #333; height: 100vh; padding: 20px; }
        .main-content { padding: 20px; height: 100vh; display: flex; flex-direction: column; }
        .chat-container { flex-grow: 1; overflow-y: auto; margin-bottom: 20px; border: 1px solid #333; padding: 15px; border-radius: 8px; background: #151e2e; }
        .input-row { display: flex; gap: 10px; align-items: flex-end; }
        .input-box { flex-grow: 1; padding: 12px; border-radius: 5px; background: #2a2a35; border: 1px solid #444; color: white; outline: none; }
        .send-btn { padding: 12px 24px; border-radius: 5px; background: #00e5ff; color: #0f172a; font-weight: bold; cursor: pointer; border: none; transition: 0.2s; }
        .send-btn:hover { background: #38bdf8; }
        /* Style des messages */
        .msg-user { color: #00e5ff; font-size: 12px; font-weight: bold; margin-bottom: 2px; margin-top: 15px;}
        .msg-ia { color: #a855f7; font-size: 12px; font-weight: bold; margin-bottom: 2px; margin-top: 15px;}
        .bubble-user { background: #1e293b; padding: 10px; border-radius: 5px; display: inline-block; color: white; }
        .bubble-ia { background: #2a2a35; padding: 10px; border-radius: 5px; display: inline-block; color: #e2e8f0; border-left: 3px solid #a855f7; }
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
                cls="sidebar"
            ),
            Div(
                Div(id="chat-history", cls="chat-container"),
                Form(
                    Input(type="text", name="msg", placeholder="Demandez moi de coder quelque chose...", cls="input-box", required=True),
                    Button("Envoyer", type="submit", cls="send-btn"),
                    cls="input-row",
                    hx_post="/chat", 
                    hx_target="#chat-history", 
                    hx_swap="beforeend"
                ),
                cls="main-content"
            ),
            style="display: grid; grid-template-columns: 250px 1fr;"
        )
    )

@rt('/chat')
def post(msg: str):
    # 1. Préparation de la requête vers l'API OpenRouter
    api_key = os.getenv("OPENROUTER_API_KEY")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Payload avec un modèle gratuit d'OpenRouter
    payload = {
        "model": "meta-llama/llama-3-8b-instruct:free",
        "messages": [{"role": "user", "content": msg}]
    }
    
    # 2. Envoi de la requête
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        if response.status_code == 200:
            ia_reponse = response.json()["choices"][0]["message"]["content"]
        else:
            ia_reponse = f"Erreur API ({response.status_code}) : Vérifiez votre clé dans le fichier .env"
    except Exception as e:
        ia_reponse = f"Erreur réseau : {e}"

    # 3. Injection de la réponse dans l'interface Web
    return Div(
        P("Vous", cls="msg-user"),
        Div(msg, cls="bubble-user"),
        P("AETHAS38 (Llama 3)", cls="msg-ia"),
        Div(ia_reponse, cls="bubble-ia")
    )

if __name__ == '__main__':
    serve(port=5001)