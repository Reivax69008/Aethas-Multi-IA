# history_manager.py
import os
import json
import uuid
from datetime import datetime

HISTORY_FILE = "sessions/history.json"

def load_index():
    if not os.path.exists(HISTORY_FILE): return {}
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        try: return json.load(f)
        except: return {}[cite: 11]

def save_index(idx):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(idx, f, indent=4, ensure_ascii=False)[cite: 11]

def load_session_data(session_id):
    path = f"sessions/{session_id}.json"
    if not os.path.exists(path): return []
    with open(path, "r", encoding="utf-8") as f:
        try: return json.load(f)
        except: return [][cite: 11]

def save_session_data(session_id, messages):
    with open(f"sessions/{session_id}.json", "w", encoding="utf-8") as f:
        json.dump(messages, f, indent=4, ensure_ascii=False)[cite: 11]

def create_new_session():
    session_id = str(uuid.uuid4())
    idx = load_index()
    idx[session_id] = {"title": f"Projet du {datetime.now().strftime('%d/%m %H:%M')}", "pinned": False}
    save_index(idx)
    save_session_data(session_id, [])
    return session_id[cite: 11]