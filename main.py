from fasthtml.common import *
import os
from dotenv import load_dotenv

load_dotenv()

# En-têtes pour le style visuel
theme_hdrs = [
    Script(src="https://cdn.tailwindcss.com"),
    Style("""
        body { background-color: #0f172a; color: #f8fafc; font-family: system-ui, sans-serif; }
        .sidebar { background-color: #1e293b; border-right: 1px solid #333; height: 100vh; padding: 20px; }
        .main-content { padding: 20px; height: 100vh; display: flex; flex-direction: column; }
    """)
]

# Initialisation de l'application FastHTML
app, rt = fast_app(hdrs=theme_hdrs)

@rt('/')
def get():
    return Title("AETHAS38 Multi-IA"), Body(
        Div(  # On utilise Div au lieu de Grid
            Div(
                H2("AETHAS 38", style="color:#00e5ff; font-weight:bold; font-size:24px;"),
                P("Tech Core - Multi IA", style="color:#a855f7; margin-bottom: 20px;"),
                cls="sidebar"
            ),
            Div(
                H3("Interface prête pour l'intégration des modèles", style="font-size:20px; margin-bottom:10px;"),
                P("Le serveur local FastHTML fonctionne correctement."),
                cls="main-content"
            ),
            style="display: grid; grid-template-columns: 250px 1fr;" # C'est ici qu'on définit la grille
        )
    )

if __name__ == '__main__':
    serve()