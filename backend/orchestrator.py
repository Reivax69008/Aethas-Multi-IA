import asyncio
import httpx
from openai import AsyncOpenAI
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from .models import SystemSettings, AIModel, FinancialLog
from datetime import datetime, timezone

def determine_domain(model_id: str) -> str:
    mid = model_id.lower()
    if "vision" in mid or "vl" in mid or "omni" in mid: return "Vision & Texte"
    if "coder" in mid or "code" in mid or "math" in mid: return "Code & Logique"
    if "audio" in mid or "whisper" in mid: return "Audio"
    return "Texte Polyvalent"

async def sync_finances(db: Session, settings: SystemSettings):
    async with httpx.AsyncClient(timeout=30.0) as client:
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
            
        if settings.groq_api_key: update_finance_db(db, "Groq", 999.0, 0.0)
        if settings.deepseek_api_key:
            try:
                resp = await client.get("https://api.deepseek.com/user/balance", headers={"Authorization": f"Bearer {settings.deepseek_api_key}"})
                if resp.status_code == 200:
                    infos = resp.json().get("balance_infos", [{}])[0]
                    update_finance_db(db, "DeepSeek", float(infos.get("total_balance", 0)), 0.0)
            except Exception: pass
        if settings.mistral_api_key: update_finance_db(db, "Mistral", 0.0, 0.0)
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
    models_to_process = {}
    async with httpx.AsyncClient(timeout=90.0) as client:
        if settings.openrouter_api_key:
            try:
                resp = await client.get("https://openrouter.ai/api/v1/models")
                if resp.status_code == 200:
                    for item in resp.json().get("data", []):
                        try:
                            m_id = item.get("id")
                            if not m_id: continue
                            pricing = item.get("pricing") or {}
                            pp = float(pricing.get("prompt") or 0.0) * 1000000
                            pc = float(pricing.get("completion") or 0.0) * 1000000
                            is_free = (pp == 0.0 and pc == 0.0)
                            desc = item.get("description", "Modèle OpenRouter.")[:200] + "..."
                            models_to_process[m_id] = {"provider": "openrouter", "name": item.get("name", "Inconnu"), "desc": desc, "domain": determine_domain(m_id), "is_free": is_free, "ctx": item.get("context_length", 0), "pp": pp, "pc": pc}
                        except: pass
            except Exception as e: print(f"Erreur OR Models: {e}")
            
        if settings.groq_api_key:
            try:
                resp = await client.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {settings.groq_api_key}"})
                if resp.status_code == 200:
                    for item in resp.json().get("data", []):
                        m_id = item["id"]
                        models_to_process[m_id] = {"provider": "groq", "name": m_id.capitalize(), "desc": "Modèle rapide LPU Groq.", "domain": determine_domain(m_id), "is_free": True, "ctx": 8192, "pp": 0.0, "pc": 0.0}
            except Exception: pass

        if settings.deepseek_api_key:
            try:
                resp = await client.get("https://api.deepseek.com/models", headers={"Authorization": f"Bearer {settings.deepseek_api_key}"})
                if resp.status_code == 200:
                    for item in resp.json().get("data", []):
                        m_id = item["id"]
                        models_to_process[m_id] = {"provider": "deepseek", "name": m_id.capitalize(), "desc": "Modèle officiel DeepSeek.", "domain": determine_domain(m_id), "is_free": False, "ctx": 64000, "pp": 0.14, "pc": 0.28}
            except Exception: pass

        if settings.mistral_api_key:
            try:
                resp = await client.get("https://api.mistral.ai/v1/models", headers={"Authorization": f"Bearer {settings.mistral_api_key}"})
                if resp.status_code == 200:
                    for item in resp.json().get("data", []):
                        m_id = item["id"]
                        models_to_process[m_id] = {"provider": "mistral", "name": m_id.capitalize(), "desc": "Modèle officiel Mistral AI.", "domain": determine_domain(m_id), "is_free": False, "ctx": 32000, "pp": 0.2, "pc": 0.6}
            except Exception: pass

        if settings.gemini_api_key:
            try:
                resp = await client.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={settings.gemini_api_key}")
                if resp.status_code == 200:
                    for item in resp.json().get("models", []):
                        m_id = item["name"].replace("models/", "")
                        desc = item.get("description", "Modèle Google Gemini.")[:200] + "..."
                        models_to_process[m_id] = {"provider": "gemini", "name": item.get("displayName", m_id), "desc": desc, "domain": determine_domain(m_id), "is_free": True, "ctx": item.get("inputTokenLimit", 32000), "pp": 0.0, "pc": 0.0}
            except Exception: pass

        if settings.cloudflare_account_id and settings.cloudflare_api_token:
            try:
                url = f"https://api.cloudflare.com/client/v4/accounts/{settings.cloudflare_account_id}/ai/models/search"
                resp = await client.get(url, headers={"Authorization": f"Bearer {settings.cloudflare_api_token}"})
                if resp.status_code == 200:
                    for item in resp.json().get("result", []):
                        m_id = item.get("name")
                        desc = item.get("description", "Modèle Cloudflare Workers AI.")[:200] + "..."
                        models_to_process[m_id] = {"provider": "cloudflare", "name": m_id.split("/")[-1], "desc": desc, "domain": determine_domain(m_id), "is_free": True, "ctx": 4096, "pp": 0.0, "pc": 0.0}
            except Exception: pass

    for m_id, data in models_to_process.items():
        try:
            existing = db.query(AIModel).filter(AIModel.model_id == m_id).first()
            if existing:
                existing.pricing_prompt = data["pp"]; existing.pricing_completion = data["pc"]; existing.is_free = data["is_free"]; existing.last_updated = datetime.now(timezone.utc)
            else:
                db.add(AIModel(provider=data["provider"], model_id=m_id, name=data["name"], description_fr=data["desc"], domain=data["domain"], is_free=data["is_free"], context_length=data["ctx"], pricing_prompt=data["pp"], pricing_completion=data["pc"]))
            added += 1
            if added % 50 == 0: db.commit()
        except IntegrityError: db.rollback()
        except Exception: db.rollback()

    try:
        settings.last_sync_date = datetime.now(timezone.utc)
        settings.last_sync_type = sync_type
        db.commit()
    except Exception as e:
        db.rollback()
        
    await sync_finances(db, settings)
    return {"status": "success", "models_processed": added}

def get_client_for_model(db: Session, model_id: str, settings: SystemSettings):
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
        # Étape 1 : Le prompteur traduit et optimise la requête en ANGLAIS pour les travailleurs
        p_mod = config.get("prompter", "gemini-3.5-flash-lite")
        p_client, p_prov = get_client_for_model(db, p_mod, settings)
        prompt_system = "You are an expert prompt engineer. Translate and optimize the user request into clear, precise English tailored for AI execution."
        optimized = await ask_agent(p_client, p_mod, [{"role": "system", "content": prompt_system}, {"role": "user", "content": user_prompt}], p_prov)

        if len(workers) == 1:
            w_mod = workers[0]
            client, provider = get_client_for_model(db, w_mod, settings)
            worker_response = await ask_agent(client, w_mod, formatted_history + [{"role": "user", "content": optimized}], provider)
            responses = [worker_response]
        else:
            w_tasks = []
            for w in workers:
                w_client, w_prov = get_client_for_model(db, w, settings)
                w_tasks.append(ask_agent(w_client, w, formatted_history + [{"role": "user", "content": optimized}], w_prov))
            responses = await asyncio.gather(*w_tasks, return_exceptions=True)

        # Étape 2 : Le concaténeur synthétise et traduit le retour en FRANÇAIS (en préservant le code et les commentaires)
        c_mod = config.get("concatenator", "gemini-3.5-flash-lite")
        c_client, c_prov = get_client_for_model(db, c_mod, settings)
        
        concat_system = (
            "You are a master lead developer and technical synthesizer. "
            "Synthesize the provided expert responses into a single cohesive response. "
            "Translate all explanatory text, descriptions, and user-facing prose into natural French. "
            "CRITICAL: Do NOT translate code blocks, programming keywords, or source code contents. "
            "You may translate code comments into French if appropriate, but leave code syntax strictly intact."
        )
        
        synth = f"User Request: {user_prompt}\n\n" + "\n".join([f"--- EXPERT {i+1} ---\n{r}" for i, r in enumerate(responses)])
        final_response = await ask_agent(c_client, c_mod, [{"role": "system", "content": concat_system}, {"role": "user", "content": synth}], c_prov)

    except Exception as e:
        final_response = f"L'IA a rencontré une erreur critique: {str(e)}"
    
    await sync_finances(db, settings)
    return final_response