import asyncio
import httpx
from openai import AsyncOpenAI
from fastapi import HTTPException
from sqlalchemy.orm import Session
from .models import SystemSettings, AIModel, FinancialLog
from datetime import datetime, timezone

def determine_domain(model_id: str) -> str:
    mid = model_id.lower()
    if "vision" in mid or "vl" in mid: return "Vision & Texte"
    if "coder" in mid or "code" in mid or "math" in mid: return "Code & Logique"
    if "audio" in mid or "whisper" in mid: return "Audio"
    return "Texte Polyvalent"

async def sync_finances(db: Session, settings: SystemSettings):
    """Interroge les fournisseurs pour récupérer le solde financier exact."""
    async with httpx.AsyncClient() as client:
        if settings.openrouter_management_key or settings.openrouter_api_key:
            try:
                key = settings.openrouter_management_key or settings.openrouter_api_key
                # Test de l'endpoint des crédits prépayés en priorité
                cred_resp = await client.get("https://openrouter.ai/api/v1/credits", headers={"Authorization": f"Bearer {key}"})
                balance = 0.0
                usage = 0.0
                
                if cred_resp.status_code == 200 and cred_resp.json().get("data"):
                    data = cred_resp.json().get("data", {})
                    balance = float(data.get("total_credits") or 0.0) - float(data.get("total_usage") or 0.0)
                    usage = float(data.get("total_usage") or 0.0)
                else:
                    # Fallback sur l'usage de la clé si pas de crédits prépayés
                    key_resp = await client.get("https://openrouter.ai/api/v1/auth/key", headers={"Authorization": f"Bearer {key}"})
                    if key_resp.status_code == 200:
                        data = key_resp.json().get("data", {})
                        limit = data.get("limit")
                        usage = float(data.get("usage") or 0.0)
                        balance = (float(limit) - usage) if limit is not None else -usage
                
                update_finance_db(db, "OpenRouter", balance, usage)
            except Exception as e: print(f"Erreur Finance OR: {e}")
            
        if settings.groq_api_key: update_finance_db(db, "Groq", 999.0, 0.0) # Gratuit en Beta
            
        if settings.deepseek_api_key:
            try:
                resp = await client.get("https://api.deepseek.com/user/balance", headers={"Authorization": f"Bearer {settings.deepseek_api_key}"})
                if resp.status_code == 200:
                    infos = resp.json().get("balance_infos", [{}])[0]
                    update_finance_db(db, "DeepSeek", float(infos.get("total_balance", 0)), 0.0)
            except Exception: pass
    db.commit()

def update_finance_db(db, provider, balance, usage):
    log = db.query(FinancialLog).filter(FinancialLog.provider == provider).first()
    if log:
        log.balance = balance; log.total_usage = usage; log.checked_at = datetime.now(timezone.utc)
    else:
        db.add(FinancialLog(provider=provider, balance=balance, total_usage=usage))

async def sync_providers_models(db: Session, settings: SystemSettings, sync_type: str = "Automatique"):
    added = 0
    async with httpx.AsyncClient() as client:
        if settings.openrouter_api_key:
            try:
                resp = await client.get("https://openrouter.ai/api/v1/models")
                if resp.status_code == 200:
                    for item in resp.json().get("data", []):
                        pricing = item.get("pricing") or {}
                        pp = float(pricing.get("prompt") or 0.0) * 1000000
                        pc = float(pricing.get("completion") or 0.0) * 1000000
                        is_free = (pp == 0.0 and pc == 0.0)
                        desc = item.get("description", "Modèle IA générique.")[:200] + "..."
                        process_model(db, "openrouter", item["id"], item["name"], desc, determine_domain(item["id"]), is_free, item.get("context_length", 0), pp, pc)
                        added += 1
            except Exception as e: print(f"Erreur Modèles OR: {e}")
            
        if settings.groq_api_key:
            try:
                resp = await client.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {settings.groq_api_key}"})
                if resp.status_code == 200:
                    for item in resp.json().get("data", []):
                        process_model(db, "groq", item["id"], item["id"].capitalize(), "Modèle ultra-rapide exécuté sur LPU Groq.", determine_domain(item["id"]), True, 8192, 0.0, 0.0)
                        added += 1
            except Exception: pass

    settings.last_sync_date = datetime.now(timezone.utc)
    settings.last_sync_type = sync_type
    db.commit()
    await sync_finances(db, settings)
    return {"status": "success", "models_processed": added}

def process_model(db, provider, mod_id, name, desc, domain, is_free, ctx, pp, pc):
    existing = db.query(AIModel).filter(AIModel.model_id == mod_id).first()
    if existing:
        existing.pricing_prompt = pp; existing.pricing_completion = pc; existing.is_free = is_free; existing.last_updated = datetime.now(timezone.utc)
    else:
        db.add(AIModel(provider=provider, model_id=mod_id, name=name, description_fr=desc, domain=domain, is_free=is_free, context_length=ctx, pricing_prompt=pp, pricing_completion=pc))

def get_client_for_model(model_id: str, settings: SystemSettings):
    if "gemini" in model_id.lower() and settings.gemini_api_key: return AsyncOpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=settings.gemini_api_key)
    elif "groq" in model_id.lower() or "llama" in model_id.lower(): return AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=settings.groq_api_key)
    return AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=settings.openrouter_api_key)

async def ask_agent(client, model_id, messages, is_openrouter=False):
    kwargs = {"model": model_id, "messages": messages}
    if is_openrouter: kwargs["extra_headers"] = {"HTTP-Referer": "https://aethas38.duckdns.org", "X-Title": "AETHAS38 Orchestrator"}
    resp = await client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content

async def run_orchestrator(db: Session, history: list, settings: SystemSettings, config: dict) -> str:
    workers = config.get("workers", ["gemini-3.5-flash-lite"])
    user_prompt = history[-1].content
    formatted_history = [{"role": msg.role, "content": msg.content} for msg in history[:-1]]

    final_response = ""
    if len(workers) == 1:
        w_mod = workers[0]
        final_response = await ask_agent(get_client_for_model(w_mod, settings), w_mod, formatted_history + [{"role": "user", "content": user_prompt}], "openrouter" in w_mod.lower())
    else:
        p_mod = config.get("prompter", "gemini-3.5-flash-lite")
        optimized = await ask_agent(get_client_for_model(p_mod, settings), p_mod, [{"role": "system", "content": "Optimise cette requête."}, {"role": "user", "content": user_prompt}])

        w_tasks = [ask_agent(get_client_for_model(w, settings), w, formatted_history + [{"role": "user", "content": optimized}], "openrouter" in w.lower()) for w in workers]
        responses = await asyncio.gather(*w_tasks, return_exceptions=True)

        c_mod = config.get("concatenator", "gemini-3.5-flash-lite")
        synth = f"Requête: {user_prompt}\n\n" + "\n".join([f"--- EXPERT {i+1} ---\n{r}" for i, r in enumerate(responses)]) + "\n\nFais une synthèse finale."
        final_response = await ask_agent(get_client_for_model(c_mod, settings), c_mod, [{"role": "user", "content": synth}])
    
    # MAJ Financière après requête
    await sync_finances(db, settings)
    return final_response