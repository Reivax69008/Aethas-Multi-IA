import asyncio
import httpx
from openai import AsyncOpenAI
from fastapi import HTTPException
from sqlalchemy.orm import Session
from .models import SystemSettings, AIModel, FinancialLog
from datetime import datetime, timezone

def determine_domain(model_id: str) -> str:
    mid = model_id.lower()
    if "vision" in mid or "vl" in mid or "omni" in mid: return "Vision & Texte"
    if "coder" in mid or "code" in mid or "math" in mid: return "Code & Logique"
    if "audio" in mid or "whisper" in mid: return "Audio"
    return "Texte Polyvalent"

async def sync_finances(db: Session, settings: SystemSettings):
    """Interroge les fournisseurs pour récupérer le solde financier exact."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # OpenRouter
        if settings.openrouter_management_key or settings.openrouter_api_key:
            try:
                key = settings.openrouter_management_key or settings.openrouter_api_key
                cred_resp = await client.get("https://openrouter.ai/api/v1/credits", headers={"Authorization": f"Bearer {key}"})
                balance = 0.0
                usage = 0.0
                if cred_resp.status_code == 200 and cred_resp.json().get("data"):
                    c_data = cred_resp.json().get("data", {})
                    balance = float(c_data.get("total_credits") or 0.0) - float(c_data.get("total_usage") or 0.0)
                    usage = float(c_data.get("total_usage") or 0.0)
                else:
                    key_resp = await client.get("https://openrouter.ai/api/v1/auth/key", headers={"Authorization": f"Bearer {key}"})
                    if key_resp.status_code == 200:
                        data = key_resp.json().get("data", {})
                        limit = data.get("limit")
                        usage = float(data.get("usage") or 0.0)
                        balance = (float(limit) - usage) if limit is not None else -usage
                update_finance_db(db, "OpenRouter", balance, usage)
            except Exception as e: print(f"Erreur Finance OR: {e}")
            
        # Groq (Gratuit Beta)
        if settings.groq_api_key: update_finance_db(db, "Groq", 999.0, 0.0)
            
        # DeepSeek
        if settings.deepseek_api_key:
            try:
                resp = await client.get("https://api.deepseek.com/user/balance", headers={"Authorization": f"Bearer {settings.deepseek_api_key}"})
                if resp.status_code == 200:
                    infos = resp.json().get("balance_infos", [{}])[0]
                    update_finance_db(db, "DeepSeek", float(infos.get("total_balance", 0)), 0.0)
            except Exception: pass

        # Mistral AI (Pas de route standard simple pour le budget public, on mock)
        if settings.mistral_api_key: update_finance_db(db, "Mistral", 0.0, 0.0)
        
        # Gemini (Quota lié à GCP, pas de budget direct simple via API clé)
        if settings.gemini_api_key: update_finance_db(db, "Gemini", 0.0, 0.0)

    try: db.commit()
    except: db.rollback()

def update_finance_db(db, provider, balance, usage):
    try:
        log = db.query(FinancialLog).filter(FinancialLog.provider == provider).first()
        if log:
            log.balance = balance; log.total_usage = usage; log.checked_at = datetime.now(timezone.utc)
        else:
            db.add(FinancialLog(provider=provider, balance=balance, total_usage=usage))
    except Exception as e: print(f"Finance DB Error: {e}")

async def sync_providers_models(db: Session, settings: SystemSettings, sync_type: str = "Automatique"):
    added = 0
    # TIMEOUT PASSÉ À 90 SECONDES
    async with httpx.AsyncClient(timeout=90.0) as client:
        # 1. OpenRouter
        if settings.openrouter_api_key:
            try:
                resp = await client.get("https://openrouter.ai/api/v1/models")
                if resp.status_code == 200:
                    for item in resp.json().get("data", []):
                        try:
                            pricing = item.get("pricing") or {}
                            try: pp = float(pricing.get("prompt") or 0.0) * 1000000
                            except: pp = 0.0
                            try: pc = float(pricing.get("completion") or 0.0) * 1000000
                            except: pc = 0.0
                            is_free = (pp == 0.0 and pc == 0.0)
                            desc = item.get("description", "Modèle OpenRouter.")[:200] + "..."
                            process_model(db, "openrouter", item.get("id", "inconnu"), item.get("name", "Inconnu"), desc, determine_domain(item.get("id", "")), is_free, item.get("context_length", 0), pp, pc)
                            added += 1
                        except: pass
            except Exception as e: print(f"Erreur OR Models: {e}")
            
        # 2. Groq
        if settings.groq_api_key:
            try:
                resp = await client.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {settings.groq_api_key}"})
                if resp.status_code == 200:
                    for item in resp.json().get("data", []):
                        try:
                            process_model(db, "groq", item["id"], item["id"].capitalize(), "Modèle rapide LPU Groq.", determine_domain(item["id"]), True, 8192, 0.0, 0.0)
                            added += 1
                        except: pass
            except Exception: pass

        # 3. DeepSeek
        if settings.deepseek_api_key:
            try:
                resp = await client.get("https://api.deepseek.com/models", headers={"Authorization": f"Bearer {settings.deepseek_api_key}"})
                if resp.status_code == 200:
                    for item in resp.json().get("data", []):
                        try:
                            process_model(db, "deepseek", item["id"], item["id"].capitalize(), "Modèle officiel DeepSeek.", determine_domain(item["id"]), False, 64000, 0.14, 0.28)
                            added += 1
                        except: pass
            except Exception: pass

        # 4. Mistral
        if settings.mistral_api_key:
            try:
                resp = await client.get("https://api.mistral.ai/v1/models", headers={"Authorization": f"Bearer {settings.mistral_api_key}"})
                if resp.status_code == 200:
                    for item in resp.json().get("data", []):
                        try:
                            process_model(db, "mistral", item["id"], item["id"].capitalize(), "Modèle officiel Mistral AI.", determine_domain(item["id"]), False, 32000, 0.2, 0.6)
                            added += 1
                        except: pass
            except Exception: pass

        # 5. Gemini (Google)
        if settings.gemini_api_key:
            try:
                resp = await client.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={settings.gemini_api_key}")
                if resp.status_code == 200:
                    for item in resp.json().get("models", []):
                        try:
                            m_id = item["name"].replace("models/", "")
                            desc = item.get("description", "Modèle Google Gemini.")[:200] + "..."
                            ctx = item.get("inputTokenLimit", 32000)
                            process_model(db, "gemini", m_id, item.get("displayName", m_id), desc, determine_domain(m_id), True, ctx, 0.0, 0.0)
                            added += 1
                        except: pass
            except Exception: pass

        # 6. Cloudflare
        if settings.cloudflare_account_id and settings.cloudflare_api_token:
            try:
                url = f"https://api.cloudflare.com/client/v4/accounts/{settings.cloudflare_account_id}/ai/models/search"
                resp = await client.get(url, headers={"Authorization": f"Bearer {settings.cloudflare_api_token}"})
                if resp.status_code == 200:
                    for item in resp.json().get("result", []):
                        try:
                            m_id = item.get("name")
                            desc = item.get("description", "Modèle Cloudflare Workers AI.")[:200] + "..."
                            process_model(db, "cloudflare", m_id, m_id.split("/")[-1], desc, determine_domain(m_id), True, 4096, 0.0, 0.0)
                            added += 1
                        except: pass
            except Exception: pass

    try:
        settings.last_sync_date = datetime.now(timezone.utc)
        settings.last_sync_type = sync_type
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Erreur DB Commit Sync: {e}")
        
    await sync_finances(db, settings)
    return {"status": "success", "models_processed": added}

def process_model(db, provider, mod_id, name, desc, domain, is_free, ctx, pp, pc):
    try:
        existing = db.query(AIModel).filter(AIModel.model_id == mod_id).first()
        if existing:
            existing.pricing_prompt = pp; existing.pricing_completion = pc; existing.is_free = is_free; existing.last_updated = datetime.now(timezone.utc)
        else:
            db.add(AIModel(provider=provider, model_id=mod_id, name=name, description_fr=desc, domain=domain, is_free=is_free, context_length=ctx, pricing_prompt=pp, pricing_completion=pc))
    except Exception: pass

def get_client_for_model(db: Session, model_id: str, settings: SystemSettings):
    """Récupère dynamiquement le bon client OpenAI en fonction du fournisseur du modèle."""
    model_db = db.query(AIModel).filter(AIModel.model_id == model_id).first()
    provider = model_db.provider if model_db else "openrouter"

    if provider == "gemini" and settings.gemini_api_key:
        return AsyncOpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=settings.gemini_api_key), "gemini"
    elif provider == "groq" and settings.groq_api_key:
        return AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=settings.groq_api_key), "groq"
    elif provider == "deepseek" and settings.deepseek_api_key:
        return AsyncOpenAI(base_url="https://api.deepseek.com/v1", api_key=settings.deepseek_api_key), "deepseek"
    elif provider == "mistral" and settings.mistral_api_key:
        return AsyncOpenAI(base_url="https://api.mistral.ai/v1", api_key=settings.mistral_api_key), "mistral"
    elif provider == "cloudflare" and settings.cloudflare_account_id and settings.cloudflare_api_token:
        return AsyncOpenAI(base_url=f"https://api.cloudflare.com/client/v4/accounts/{settings.cloudflare_account_id}/ai/v1", api_key=settings.cloudflare_api_token), "cloudflare"
    
    return AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=settings.openrouter_api_key), "openrouter"

async def ask_agent(client, model_id, messages, provider="openrouter"):
    kwargs = {"model": model_id, "messages": messages}
    if provider == "openrouter": 
        kwargs["extra_headers"] = {"HTTP-Referer": "https://aethas38.duckdns.org", "X-Title": "AETHAS38 Orchestrator"}
    resp = await client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content

async def run_orchestrator(db: Session, history: list, settings: SystemSettings, config: dict) -> str:
    workers = config.get("workers", ["gemini-3.5-flash-lite"])
    user_prompt = history[-1].content
    formatted_history = [{"role": msg.role, "content": msg.content} for msg in history[:-1]]

    final_response = ""
    try:
        if len(workers) == 1:
            w_mod = workers[0]
            client, provider = get_client_for_model(db, w_mod, settings)
            final_response = await ask_agent(client, w_mod, formatted_history + [{"role": "user", "content": user_prompt}], provider)
        else:
            p_mod = config.get("prompter", "gemini-3.5-flash-lite")
            p_client, p_prov = get_client_for_model(db, p_mod, settings)
            optimized = await ask_agent(p_client, p_mod, [{"role": "system", "content": "Optimise cette requête."}, {"role": "user", "content": user_prompt}], p_prov)

            w_tasks = []
            for w in workers:
                w_client, w_prov = get_client_for_model(db, w, settings)
                w_tasks.append(ask_agent(w_client, w, formatted_history + [{"role": "user", "content": optimized}], w_prov))
                
            responses = await asyncio.gather(*w_tasks, return_exceptions=True)

            c_mod = config.get("concatenator", "gemini-3.5-flash-lite")
            c_client, c_prov = get_client_for_model(db, c_mod, settings)
            synth = f"Requête: {user_prompt}\n\n" + "\n".join([f"--- EXPERT {i+1} ---\n{r}" for i, r in enumerate(responses)]) + "\n\nFais une synthèse finale."
            final_response = await ask_agent(c_client, c_mod, [{"role": "user", "content": synth}], c_prov)
    except Exception as e:
        final_response = f"L'IA a rencontré une erreur critique: {str(e)}"
    
    await sync_finances(db, settings)
    return final_response