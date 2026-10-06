import json
import os

# Détecte le dossier parent (racine du projet) dynamiquement
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
CONFIG_FILE = os.path.join(SESSIONS_DIR, "app_config.json")

def load_config():
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        default_config = {
            "api_keys": {"openrouter": "", "groq": "", "gemini": ""},
            "smtp": {"host": "", "port": 587, "user": "", "password": ""},
            "custom_providers": []
        }
        save_config(default_config)
        return default_config
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(config_data):
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=4, ensure_ascii=False)