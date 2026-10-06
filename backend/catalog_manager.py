# catalog_manager.py
import os
import json
import re
import requests

CATALOG_FILE = "sessions/catalog.json"
MODELS_DATA = []

def load_catalog():
    global MODELS_DATA
    if os.path.exists(CATALOG_FILE):
        with open(CATALOG_FILE, "r", encoding="utf-8") as f:
            try: MODELS_DATA = json.load(f)
            except: MODELS_DATA = []
    if not MODELS_DATA:
        MODELS_DATA = [
            {"id": "groq|llama-3.1-8b-instant", "name": "Groq - Llama 3.1 (8B)", "is_free": True, "provider": "Général / Texte", "description": "Modèle par défaut."},
            {"id": "gemini|gemini-1.5-flash", "name": "Google - Gemini 1.5 Flash", "is_free": True, "provider": "Vision", "description": "Modèle par défaut."}
        ]
load_catalog()

def save_catalog(data):
    global MODELS_DATA
    MODELS_DATA = data
    with open(CATALOG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)[cite: 11]

def get_budget():
    mgmt_key = os.getenv("OPENROUTER_MANAGEMENT_KEY")
    if not mgmt_key: return "Clé manquante[cite: 11]"
    try:
        data = requests.get("https://openrouter.ai/api/v1/credits", headers={"Authorization": f"Bearer {mgmt_key}"}, timeout=5).json().get("data", {})
        return f"{data.get('total_credits', 0) - data.get('total_usage', 0):.4f} $"[cite: 11]
    except: return "Erreur réseau[cite: 11]"

def parse_txt_catalog(content: str):
    lines = content.split('\n')
    models = []
    current = {}
    ext_date, ext_time = "Inconnue", ""
    
    for line in lines:
        line_trim = line.strip()
        if "Généré le" in line_trim:
            match = re.search(r"Généré le (\d{2}/\d{2}/\d{4}) à (\d{2}:\d{2}:\d{2})", line_trim)
            if match:
                ext_date, ext_time = match.group(1), match.group(2)
        if line_trim.startswith("Nom : "): current['name'] = line_trim.replace("Nom : ", "").strip()
        elif line_trim.startswith("ID : "): current['id'] = line_trim.replace("ID : ", "").strip()
        elif line_trim.startswith("Tarif : "): current['is_free'] = ("Gratuit" in line_trim)
        elif line_trim.startswith("Spécialité : "): current['provider'] = line_trim.replace("Spécialité : ", "").strip()
        elif line_trim.startswith("Description : "): current['description'] = line_trim.replace("Description : ", "").strip()
        elif line_trim.startswith("---"):
            if 'id' in current and 'name' in current: models.append(current)
            current = {}
    return models, ext_date, ext_time[cite: 11]