import asyncio
import httpx
import urllib.parse
import traceback
from openai import AsyncOpenAI
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from .models import SystemSettings, AIModel, FinancialLog
from .logger import system_logger
from datetime import datetime, timezone

# --- LOGGER GLOBAL (Mémoire UI + Fichier Système) ---
activity_logs = []

def log_activity(msg: str):
    ts = datetime.now(timezone.utc).strftime('%H:%M:%S')
    formatted_msg = f"[{ts}] {msg}"
    activity_logs.append(formatted_msg)
    if len(activity_logs) > 100:
        activity_logs.pop(0)
    # Écriture effective dans le fichier de log (logs/aethas38_system.log)
    system_logger.info(msg)
# --------------------------------------

def determine_domain(model_id: str) -> str:
    if not model_id: return "Texte Polyvalent"
    mid = model_id.lower()
    if "vision" in mid or "vl" in mid or "omni" in mid: return "Vision & Texte"
    if "coder" in mid or "code" in mid or "math" in mid: return "Code & Logique"
    if "audio" in mid or "whisper" in mid: return "Audio"
    return "Texte Polyvalent"

async def translate_en_to_fr(client: httpx.AsyncClient, text: str) -> str:
    if not text: return "Aucune description fournie."
    try:
        short_text = text[:300].strip()
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=fr&dt=t&q={urllib.parse.quote(short_text)}"
        resp = await client.get(url, timeout=4.0)
        if resp.status_code == 200:
            data = resp.json()
            if data and isinstance(data, list) and data[0]:
                translated = "".join([s[0] for s in data[0] if s and s[0]])
                return translated + ("..." if len(text) > 300 else "")
    except Exception:
        pass
    return text[:200] + "..."

async def sync_finances(db: Session, settings: SystemSettings):
    if not settings: return
    async with httpx.AsyncClient(timeout=30.0) as client:
        if settings.openrouter_management_key or settings.openrouter_api_key:
            try:
                key = settings.openrouter_management_key or settings.openrouter_api_key
                cred_resp = await client.get("https://openrouter.ai/api/v1/credits", headers={"Authorization": f"Bearer {key}"})
                balance = 0.0
                usage = 0.0
                cred_json = cred_resp.json() if cred_resp.status_code == 200 else {}
                if cred_json and isinstance(cred_json, dict) and cred_json.get("data"):
                    c_data = cred_json.get("data") or {}
                    balance = float(c_data.get("total_credits") or 0.0) - float(c_data.get("total_usage") or 0.0)
                    usage = float(c_data.get("total_usage") or 0.0)
                else:
                    key_resp = await client.get("https://openrouter.ai/api/v1/auth/key", headers={"Authorization": f"Bearer {key}"})
                    key_json = key_resp.json() if key_resp.status_code == 200 else {}
                    if key_json and isinstance(key_json, dict):
                        data = key_json.get("data") or {}
                        limit = data.get("limit")
                        usage = float(data.get("usage") or 0.0)
                        balance = (float(limit) - usage) if limit is not None else -usage
                update_finance_db(db, "OpenRouter", balance, usage)
            except Exception as e: print(f"Erreur Finance OR: {e}")
            
        if settings.groq_api_key: update_finance_db(db, "Groq", 999.0, 0.0)
        if settings.deepseek_api_key:
            try:
                resp = await client.get("https://api.deepseek.com/user/balance", headers={"Authorization": f"Bearer {settings.deepseek_api_key}"})
                ds_json = resp.json() if resp.status_code == 200 else {}
                if ds_json and isinstance(ds_json, dict):
                    balance_infos = ds_json.get("balance_infos") or []
                    if balance_infos and len(balance_infos) > 0 and balance_infos[0]:
                        infos = balance_infos[0]
                        update_finance_db(db, "DeepSeek", float(infos.get("total_balance") or 0.0), 0.0)
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
    if not settings: return {"status": "error", "models_processed": 0}
    log_activity(f"Lancement de la synchronisation des modèles ({sync_type})...")
    added = 0
    models_to_process = {}
    async with httpx.AsyncClient(timeout=90.0) as client:
        if settings.openrouter_api_key:
            try:
                resp = await client.get("https://openrouter.ai/api/v1/models")
                if resp.status_code == 200 and resp.json():
                    for item in (resp.json().get("data") or []):
                        try:
                            if not item: continue
                            m_id = item.get("id")
                            if not m_id: continue
                            pricing = item.get("pricing") or {}
                            pp = float(pricing.get("prompt") or 0.0) * 1000000
                            pc = float(pricing.get("completion") or 0.0) * 1000000
                            is_free = (pp == 0.0 and pc == 0.0)
                            desc_en = item.get("description") or "Generic AI Model."
                            models_to_process[m_id] = {"provider": "openrouter", "name": item.get("name") or "Inconnu", "desc_en": desc_en, "domain": determine_domain(m_id), "is_free": is_free, "ctx": item.get("context_length") or 0, "pp": pp, "pc": pc}
                        except: pass
            except Exception as e: print(f"Erreur OR Models: {e}")
            
        if settings.groq_api_key:
            try:
                resp = await client.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {settings.groq_api_key}"})
                if resp.status_code == 200 and resp.json():
                    for item in (resp.json().get("data") or []):
                        if not item or "id" not in item: continue
                        m_id = item["id"]
                        models_to_process[m_id] = {"provider": "groq", "name": m_id.capitalize(), "desc": "Modèle très rapide hébergé sur LPU Groq.", "domain": determine_domain(m_id), "is_free": True, "ctx": 8192, "pp": 0.0, "pc": 0.0}
            except Exception: pass

        if settings.deepseek_api_key:
            try:
                resp = await client.get("https://api.deepseek.com/models", headers={"Authorization": f"Bearer {settings.deepseek_api_key}"})
                if resp.status_code == 200 and resp.json():
                    for item in (resp.json().get("data") or []):
                        if not item or "id" not in item: continue
                        m_id = item["id"]
                        models_to_process[m_id] = {"provider": "deepseek", "name": m_id.capitalize(), "desc": "Modèle officiel du fournisseur DeepSeek.", "domain": determine_domain(m_id), "is_free": False, "ctx": 64000, "pp": 0.14, "pc": 0.28}
            except Exception: pass

        if settings.mistral_api_key:
            try:
                resp = await client.get("https://api.mistral.ai/v1/models", headers={"Authorization": f"Bearer {settings.mistral_api_key}"})
                if resp.status_code == 200 and resp.json():
                    for item in (resp.json().get("data") or []):
                        if not item or "id" not in item: continue
                        m_id = item["id"]
                        models_to_process[m_id] = {"provider": "mistral", "name": m_id.capitalize(), "desc": "Modèle officiel développé par Mistral AI.", "domain": determine_domain(m_id), "is_free": False, "ctx": 32000, "pp": 0.2, "pc": 0.6}
            except Exception: pass

        if settings.gemini_api_key:
            try:
                resp = await client.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={settings.gemini_api_key}")
                if resp.status_code == 200 and resp.json():
                    for item in (resp.json().get("models") or []):
                        if not item or "name" not in item: continue
                        m_id = item["name"].replace("models/", "")
                        models_to_process[m_id] = {"provider": "gemini", "name": item.get("displayName") or m_id, "desc": "Modèle natif de l'écosystème Google Gemini.", "domain": determine_domain(m_id), "is_free": True, "ctx": item.get("inputTokenLimit") or 32000, "pp": 0.0, "pc": 0.0}
            except Exception: pass

        if settings.cloudflare_account_id and settings.cloudflare_api_token:
            try:
                url = f"https://api.cloudflare.com/client/v4/accounts/{settings.cloudflare_account_id}/ai/models/search"
                resp = await client.get(url, headers={"Authorization": f"Bearer {settings.cloudflare_api_token}"})
                if resp.status_code == 200 and resp.json():
                    for item in (resp.json().get("result") or []):
                        if not item or not item.get("name"): continue
                        m_id = item.get("name")
                        models_to_process[m_id] = {"provider": "cloudflare", "name": m_id.split("/")[-1], "desc": "Modèle Serverless Cloudflare Workers AI.", "domain": determine_domain(m_id), "is_free": True, "ctx": 4096, "pp": 0.0, "pc": 0.0}
            except Exception: pass

    sem = asyncio.Semaphore(15)
    async def process_and_translate(m_id, data, client_session):
        async with sem:
            if "desc_en" in data:
                data["desc"] = await translate_en_to_fr(client_session, data["desc_en"])
            return m_id, data

    async with httpx.AsyncClient(timeout=30.0) as client_trans:
        tasks = [process_and_translate(m_id, data, client_trans) for m_id, data in models_to_process.items()]
        translated_results = await asyncio.gather(*tasks)

    for m_id, data in translated_results:
        try:
            existing = db.query(AIModel).filter(AIModel.model_id == m_id).first()
            if existing:
                existing.pricing_prompt = data["pp"]; existing.pricing_completion = data["pc"]; existing.is_free = data["is_free"]; existing.description_fr = data["desc"]; existing.last_updated = datetime.now(timezone.utc)
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
    log_activity(f"Synchronisation terminée : {added} modèles analysés.")
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

def extract_safe_content(resp) -> str:
    """Extrait le texte de la réponse OpenAI/OpenRouter en évitant toute erreur NoneType."""
    if not resp:
        raise ValueError("Réponse API vide (None).")
    if getattr(resp, "error", None):
        err_info = resp.error
        if isinstance(err_info, dict):
            raise ValueError(f"Erreur fournisseur: {err_info.get('message', err_info)}")
        raise ValueError(f"Erreur fournisseur: {err_info}")
    choices = getattr(resp, "choices", None)
    if not choices or not isinstance(choices, list) or len(choices) == 0 or choices[0] is None:
        raise ValueError("Aucun choix (choices) retourné par le modèle.")
    msg = getattr(choices[0], "message", None)
    if not msg:
        raise ValueError("Objet message manquant dans la réponse.")
    content = getattr(msg, "content", None)
    if content is None:
        raise ValueError("Le modèle a renvoyé un contenu vide (None).")
    return str(content)

async def ask_agent(client, model_id, messages, provider="openrouter", enable_web=True) -> str:
    kwargs = {"model": model_id, "messages": messages}
    if provider == "openrouter": 
        kwargs["extra_headers"] = {"HTTP-Referer": "https://aethas38.duckdns.org", "X-Title": "AETHAS38 Orchestrator"}
        plugins = [{"id": "context-compression"}]
        if enable_web:
            plugins.append({"id": "web"})
        kwargs["extra_body"] = {"plugins": plugins}
        
        try:
            resp = await client.chat.completions.create(**kwargs)
            return extract_safe_content(resp)
        except Exception as e:
            if enable_web:
                log_activity(f"Repli sans plugin web pour {model_id} : {str(e)[:80]}")
                kwargs["extra_body"] = {"plugins": [{"id": "context-compression"}]}
                resp = await client.chat.completions.create(**kwargs)
                return extract_safe_content(resp)
            raise e
    else:
        resp = await client.chat.completions.create(**kwargs)
        return extract_safe_content(resp)

async def run_orchestrator(db: Session, history: list, settings: SystemSettings, config: dict, extracted_files: list = None) -> str:
    if not config: config = {}
    workers = config.get("workers") or ["gemini-3.5-flash-lite"]
    user_prompt = (history[-1].content or "") if history else ""
    original_user_text = user_prompt.split("\n\n[Fichiers joints")[0] if "[Fichiers joints" in user_prompt else user_prompt
    formatted_history = [{"role": msg.role, "content": msg.content or ""} for msg in history[:-1]] if len(history) > 1 else []

    final_response = ""
    try:
        p_mod = config.get("prompter")
        if not p_mod: p_mod = "gemini-3.5-flash-lite"
        
        log_activity(f"Démarrage de l'orchestration. Modèle Prompteur: {p_mod}")
        p_client, p_prov = get_client_for_model(db, p_mod, settings)

        files_context = ""
        if extracted_files:
            log_activity(f"Traitement Map-Reduce de {len(extracted_files)} fichier(s) joint(s).")
            async def process_single_file(f):
                if not f or not isinstance(f, dict): return ""
                fname = f.get('name') or 'Fichier_inconnu'
                content = f.get('content') or ''
                file_sys = "You are an expert data analyst and senior developer. Extract the most important technical information from the file without losing critical code syntax."
                chunk_size = 150000 
                
                if len(content) > chunk_size:
                    chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]
                    chunk_analyses = []
                    log_activity(f"Fichier lourd ({fname}): Chunking en {len(chunks)} morceaux.")
                    for idx, chunk in enumerate(chunks):
                        file_prompt = f"Demande de l'utilisateur : '{original_user_text}'.\n\nPartie {idx+1}/{len(chunks)} du fichier '{fname}'. Analysez, extrayez et résumez le code, VBA, SQL ou les données pertinentes.\n\nContenu :\n```\n{chunk}\n```"
                        try:
                            analysis = await ask_agent(p_client, p_mod, [{"role": "system", "content": file_sys}, {"role": "user", "content": file_prompt}], p_prov, enable_web=False)
                            chunk_analyses.append(analysis or "[ Analyse vide ]")
                            log_activity(f"Analyse chunk {idx+1}/{len(chunks)} pour {fname} réussie.")
                        except Exception as e:
                            chunk_analyses.append(f"[Erreur sur la partie {idx+1}: {str(e)}]")
                            log_activity(f"Erreur chunk {idx+1}/{len(chunks)} pour {fname}: {str(e)}")
                        
                        await asyncio.sleep(1.5) 
                    
                    return f"\n\n--- Extraction du fichier {fname} (en {len(chunks)} parties) ---\n" + "\n".join(chunk_analyses)
                else:
                    file_prompt = f"Demande de l'utilisateur : '{original_user_text}'.\n\nAnalysez le fichier ci-dessous. Extrayez, résumez et conservez méticuleusement tout le code, les macros VBA, les requêtes SQL, ou les données métier pertinentes pour répondre à la demande.\n\nFichier : {fname}\nContenu :\n```\n{content}\n```"
                    try:
                        analysis = await ask_agent(p_client, p_mod, [{"role": "system", "content": file_sys}, {"role": "user", "content": file_prompt}], p_prov, enable_web=False)
                        log_activity(f"Analyse intégrale de {fname} réussie.")
                        return f"\n\n--- Extraction du fichier {fname} ---\n{analysis}"
                    except Exception as e:
                        log_activity(f"Erreur d'analyse sur {fname}: {str(e)}")
                        return f"\n\n--- Erreur sur {fname} ---\n{str(e)}"

            file_analyses = []
            for f in extracted_files:
                analysis = await process_single_file(f)
                file_analyses.append(analysis or "")
                await asyncio.sleep(1.5)
            
            files_context = "".join(file_analyses)
            user_prompt = f"{original_user_text}\n\nVoici les données pré-traitées des fichiers joints :\n{files_context}"

        log_activity(f"Optimisation/Traduction de la requête via Prompteur...")
        prompt_system = "You are an expert prompt engineer. Translate and optimize the user request and any file context into clear, precise English tailored for AI execution. Keep all code blocks intact."
        optimized = await ask_agent(p_client, p_mod, [{"role": "system", "content": prompt_system}, {"role": "user", "content": user_prompt}], p_prov, enable_web=False)

        log_activity(f"Lancement de {len(workers)} travailleur(s) en parallèle...")
        if len(workers) == 1:
            w_mod = workers[0]
            client, provider = get_client_for_model(db, w_mod, settings)
            worker_response = await ask_agent(client, w_mod, formatted_history + [{"role": "user", "content": optimized}], provider, enable_web=True)
            responses = [worker_response]
            log_activity(f"Travailleur 1 ({w_mod}) a terminé.")
        else:
            w_tasks = []
            for w in workers:
                w_client, w_prov = get_client_for_model(db, w, settings)
                w_tasks.append(ask_agent(w_client, w, formatted_history + [{"role": "user", "content": optimized}], w_prov, enable_web=True))
            responses = await asyncio.gather(*w_tasks, return_exceptions=True)
            log_activity("Tous les travailleurs ont terminé leur analyse.")

        c_mod = config.get("concatenator")
        if not c_mod: c_mod = "gemini-3.5-flash-lite"
        
        c_client, c_prov = get_client_for_model(db, c_mod, settings)
        
        log_activity(f"Synthèse et traduction finale via Concaténeur ({c_mod})...")
        concat_system = (
            "You are a master lead developer and technical synthesizer. "
            "Synthesize the provided expert responses into a single cohesive response. "
            "Translate all explanatory text, descriptions, and user-facing prose into natural French. "
            "CRITICAL: Do NOT translate code blocks, programming keywords, or source code contents. "
            "You may translate code comments into French if appropriate, but leave code syntax strictly intact."
        )
        
        synth = f"User Request: {original_user_text}\n\n" + "\n".join([f"--- EXPERT {i+1} ---\n{str(r)}" for i, r in enumerate(responses)])
        final_response = await ask_agent(c_client, c_mod, [{"role": "system", "content": concat_system}, {"role": "user", "content": synth}], c_prov, enable_web=False)
        
        log_activity("Orchestration terminée avec succès.")

    except Exception as e:
        tb_str = traceback.format_exc()
        system_logger.error(f"Traceback complet:\n{tb_str}")
        final_response = f"L'IA a rencontré une erreur critique: {str(e)}"
        log_activity(f"ERREUR CRITIQUE: {str(e)}")
    
    await sync_finances(db, settings)
    return final_response