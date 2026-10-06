# ai_engine.py
import os
import requests
import asyncio
from datetime import datetime

os.makedirs("logs", exist_ok=True)
APP_LAUNCH_TIME = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = f"logs/AETHAS38_Run_{APP_LAUNCH_TIME}.log"

def log_event(session_id, category, action):
    sid_short = session_id[:8] if session_id and session_id != "system" else "SYSTEM"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] [Session:{sid_short}] [{category}] {action}\n")[cite: 11]

def ask_llm(session_id, full_id, msg):
    parts = full_id.split("|", 1)
    provider, actual_model = parts[0], parts[1] if len(parts) > 1 else full_id
    
    log_event(session_id, "API_REQ", f"Provider: {provider} | Modèle: {actual_model}")[cite: 11]
    try:
        if provider == "openrouter":
            res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"}, json={"model": actual_model, "messages": [{"role": "user", "content": msg}]})
            if res.status_code == 200: return res.json()["choices"][0]["message"]["content"]
            return f"⚠️ Erreur API ({provider}) : {res.text}"[cite: 11]
        elif provider == "groq":
            res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"}, json={"model": actual_model, "messages": [{"role": "user", "content": msg}]})
            if res.status_code == 200: return res.json()["choices"][0]["message"]["content"]
            return f"⚠️ Erreur API ({provider}) : {res.text}"[cite: 11]
        elif provider == "gemini":
            res = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{actual_model}:generateContent?key={os.getenv('GEMINI_API_KEY')}", json={"contents": [{"parts": [{"text": msg}]}]})
            if res.status_code == 200: return res.json()["candidates"][0]["content"]["parts"][0]["text"]
            return f"⚠️ Erreur API ({provider}) : {res.text}"[cite: 11]
        return "⚠️ Fournisseur API non implémenté ou ID invalide[cite: 11]."
    except Exception as e: return f"⚠ Erreur de connexion : {str(e)}"[cite: 11]

async def async_ask_llm(session_id, full_id, msg):
    return await asyncio.to_thread(ask_llm, session_id, full_id, msg)[cite: 11]