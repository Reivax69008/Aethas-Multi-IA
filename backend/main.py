# main.py
from fasthtml.common import *
import os
import time
import requests
from dotenv import load_dotenv

from auth import verify_password, verify_totp
from catalog_manager import MODELS_DATA, load_catalog, save_catalog, get_budget, parse_txt_catalog
from history_manager import load_index, save_index, load_session_data, save_session_data, create_new_session
from ai_engine import ask_llm, async_ask_llm, log_event

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
        .file-upload-btn { background: #2a2a35; border: 1px solid #444; color: #94a3b8; padding: 12px; border-radius: 5px; cursor: pointer; font-size:14px; display: flex; align-items:center; justify-content:center;}
        .model-selector { padding: 8px; border-radius: 5px; background: #1e293b; border: 1px solid #444; color: #00e5ff; width: 100%; font-size: 12px; outline:none; }
        .send-btn { padding: 12px 24px; border-radius: 5px; background: #00e5ff; color: #0f172a; font-weight: bold; cursor: pointer; border: none; }
        .msg-user { color: #00e5ff; font-size: 12px; font-weight: bold; margin-bottom: 2px; margin-top: 15px;}
        .msg-ia { color: #a855f7; font-size: 12px; font-weight: bold; margin-bottom: 2px; margin-top: 15px;}
        .bubble-user { background: #1e293b; padding: 10px; border-radius: 5px; display: inline-block; color: white; border: 1px solid #333;}
        .bubble-ia { background: #1e293b; padding: 15px; border-radius: 8px; display: block; color: #e2e8f0; border: 1px solid #333;}
        .htmx-indicator { display: none; position: absolute; bottom: 180px; left: 50%; transform: translateX(-50%); background: rgba(15, 23, 42, 0.9); border: 1px solid #00e5ff; padding: 15px 30px; border-radius: 50px; color: #00e5ff; font-weight: bold; z-index: 50;}
        .htmx-request .htmx-indicator { display: block; }
        .export-btn { display: block; background: #0f172a; border: 1px solid #00e5ff; color: #00e5ff; font-weight: bold; padding: 10px; border-radius: 5px; text-align: center; cursor: pointer; width: 100%;}
    """),
    Script("""
        function filterModels() {
            let filter = document.querySelector('input[name="filter_type"]:checked').value;
            document.querySelectorAll('.model-selector option').forEach(opt => {
                if(opt.value === "") return;
                let isFree = opt.getAttribute('data-free') === 'true';
                if(filter === 'free' && !isFree) opt.style.display = 'none';
                else if(filter === 'paid' && isFree) opt.style.display = 'none';
                else opt.style.display = 'block';
            });
        }
        function validateMultiIA() {
            let wCount = 0;
            for(let i=1; i<=2; i++) { if(document.getElementById('worker'+i).value !== "") wCount++; }
            if(wCount === 0) { alert("Erreur : Sélectionnez au moins une IA de travail."); return false; }
            return true;
        }
        function updateFileCount(input) {
            let label = document.getElementById('file-label-text');
            if(input.files && input.files.length > 0) { label.innerText = `📎 ${input.files.length} fichier(s)`; label.style.color = '#00e5ff'; } 
        }
    """)
]

app, rt = fast_app(secret_key=os.getenv("SESSION_SECRET", "super-secret-key-fallback"), hdrs=theme_hdrs)

os.makedirs("sessions", exist_ok=True)

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
    if email == os.getenv("ADMIN_EMAIL") and verify_password(os.getenv("ADMIN_PASSWORD_HASH"), password) and verify_totp(os.getenv("ADMIN_2FA_SECRET"), totp_code):
        session["authenticated"] = True
        session["role"] = "admin"
        return Script("window.location.href = '/';")
    return Div("Identifiants ou code 2FA incorrects.", style="color:#ef4444; font-weight:bold;")

@rt('/logout')
def get(session):
    session.clear()
    return RedirectResponse('/login')

@rt('/check_updates')
def get(session):
    if not session.get("authenticated"): return Span("")
    try:
        res = requests.get("https://gitea.aethas38.duckdns.org/api/v1/repos/xavier/MULTI-IA-CODAGE/commits?limit=1", timeout=3)
        if res.status_code == 200:
            return Span(f"🟢 Gitea Connecté ({res.json()[0].get('sha', '')[:7]})", style="color:#10b981;")
    except: pass
    return Span("🟠 Gitea hors ligne", style="color:#fbbf24;")

def render_history_list():
    idx = load_index()
    items = [Button("➕ Nouveau Projet", cls="export-btn mb-3", style="background:#10b981; color:#0f172a;", hx_get="/session/new", hx_target="#chat-history")]
    for sid, data in idx.items():
        items.append(Div(Div(data['title'], cls="truncate flex-grow cursor-pointer text-sm hover:text-cyan-400", hx_get=f"/session/load/{sid}", hx_target="#chat-history"), cls="flex justify-between items-center w-full mb-2 bg-[#2a2a35] p-2 rounded border border-[#444]"))
    return Div(*items, id="history-list-container", hx_swap_oob="true")

def render_model_dropdown(field_id, placeholder):
    groups = {}
    for m in MODELS_DATA:
        prov = m.get('provider', 'Général')
        if prov not in groups: groups[prov] = []
        groups[prov].append(m)
    opts = [Option("--- Laisser vide ---", value="")]
    for prov in sorted(groups.keys()):
        grp_opts = [Option(f"{m['name']} ({'Gratuit' if str(m.get('is_free'))=='True' else 'Payant'})", value=m['id'], **{"data-free": str(m.get('is_free', False)).lower()}) for m in groups[prov]]
        opts.append(Optgroup(label=prov)(*grp_opts))
    return Div(P(placeholder, style="color:#94a3b8; font-size:10px; font-weight:bold; margin-bottom:2px;"), Select(*opts, name=field_id, id=field_id, cls="model-selector", onchange="filterModels()"), style="margin-bottom: 8px;")

SESSION_PROGRESS = {}

@rt('/status/{sid}')
def get_status(sid: str):
    return SESSION_PROGRESS.get(sid, "⚙️ Traitement en cours...")

@rt('/')
def get(session):
    if not session.get("authenticated"): return RedirectResponse('/login')
    session_id = create_new_session()
    return Title("AETHAS38 Orchestrateur"), Body(
        Div(
            Div(
                H2("AETHAS 38", style="color:#00e5ff; font-weight:bold; font-size:24px;"),
                Div("⏳ Vérification GitHub...", hx_get="/check_updates", hx_trigger="load", style="font-size:10px; margin-bottom:15px;"),
                Div(H3("Historique", style="color:#94a3b8; font-size:12px; font-weight:bold; margin-bottom:10px;"), render_history_list(), style="flex-grow:1; overflow:hidden;"),
                Button("📥 Exporter Modèles", type="button", cls="export-btn mb-2", onclick="window.location.href='/export_models'"),
                A("Déconnexion", href="/logout", cls="export-btn text-center", style="color:#ef4444; border-color:#ef4444;"),
                Div(P("BUDGET", style="color:#94a3b8; font-size:10px; font-weight:bold; margin-top:8px;"), P(get_budget(), id="budget-display", style="color:#10b981; font-size:16px; font-weight:bold;")),
                cls="sidebar"
            ),
            Div(
                Div(id="chat-history", cls="chat-container"),
                Div(Span("⚙️ Préparation...", id="loading-text"), id="loading-tracker", cls="htmx-indicator"),
                Form(
                    Input(type="hidden", name="session_id", value=session_id, id="current-session-id"),
                    Div(
                        Div(render_model_dropdown("writer", "1. Rédacteur"), render_model_dropdown("synthesizer", "7. Concaténeur"), style="border-right: 1px solid #444; padding-right:15px;"),
                        Div(render_model_dropdown("worker1", "2. Travailleur 1"), render_model_dropdown("worker2", "3. Travailleur 2"), style="padding: 0 15px;"),
                        cls="grid grid-cols-2 gap-4 mb-4 bg-[#151e2e] p-4 rounded border border-[#333]"
                    ),
                    Div(
                        Input(type="file", name="fichiers", id="file-upload", multiple=True, style="display:none;", onchange="updateFileCount(this)"),
                        Label(Span("📎 Fichiers", id="file-label-text"), _for="file-upload", cls="file-upload-btn w-40"),
                        Input(type="text", name="msg", placeholder="Votre consigne...", cls="input-box", required=True),
                        Button("Lancer", type="submit", cls="send-btn"),
                        cls="input-row"
                    ),
                    hx_post="/chat", hx_target="#chat-history", hx_swap="beforeend", hx_indicator="#loading-tracker", enctype="multipart/form-data",
                    onsubmit="return validateMultiIA();"
                ),
                cls="main-content"
            ),
            style="display: grid; grid-template-columns: 280px 1fr;"
        )
    )

@rt('/chat')
async def post(msg: str, session_id: str, session, writer: str = "", worker1: str = "", worker2: str = "", synthesizer: str = "", fichiers: list[UploadFile] = None):
    if not session.get("authenticated"): return RedirectResponse('/login')
    workers = [w for w in [worker1, worker2] if w]
    
    SESSION_PROGRESS[session_id] = "⚡ Traitement des IA en cours..."
    tasks = [async_ask_llm(session_id, w, msg) for w in workers]
    results = await asyncio.gather(*tasks)
    final_response = results[0] if results else "Aucun travailleur configuré."

    session_data = load_session_data(session_id)
    session_data.append({"user": msg, "ia": final_response})
    save_session_data(session_id, session_data)

    return Div(P("Vous", cls="msg-user"), Div(msg, cls="bubble-user"), P("AETHAS38", cls="msg-ia"), Div(final_response, cls="bubble-ia")), P(get_budget(), id="budget-display", style="color:#10b981; font-size:16px; font-weight:bold;", hx_swap_oob="true")

@rt('/export_models')
def get(session):
    if not session.get("authenticated"): return RedirectResponse('/login')
    return Response("=== CATALOGUE ===\nID: groq|llama-3.1-8b-instant\nTarif: Gratuit", media_type="text/plain", headers={"Content-Disposition": "attachment; filename=modeles.txt"})

@rt('/session/new')
def get(session):
    if not session.get("authenticated"): return RedirectResponse('/login')
    sid = create_new_session()
    return Div(), Input(type="hidden", name="session_id", value=sid, id="current-session-id", hx_swap_oob="true"), render_history_list()

@rt('/session/load/{sid}')
def get(sid: str, session):
    if not session.get("authenticated"): return RedirectResponse('/login')
    messages = load_session_data(sid)
    return tuple(Div(P("Vous", cls="msg-user"), Div(m['user'], cls="bubble-user"), P("AETHAS38", cls="msg-ia"), Div(m['ia'], cls="bubble-ia")) for m in messages) + (Input(type="hidden", name="session_id", value=sid, id="current-session-id", hx_swap_oob="true"),)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)