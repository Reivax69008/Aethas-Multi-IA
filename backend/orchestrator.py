import asyncio
import httpx
import urllib.parse
import traceback
import base64
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
    system_logger.info(msg)
# --------------------------------------

ALLOWED_WORKER_PROVIDERS = {"openrouter", "cloudflare", "huggingface"}

def determine_domain(model_id: str, pipeline_tag: str = "", methods: list = None) -> str:
    if not model_id:
        return "Texte Polyvalent"
    mid = model_id.lower()
    ptag = (pipeline_tag or "").lower()
    m_list = [str(x).lower() for x in (methods or [])]

    if (
        ptag in ["text-to-video", "image-to-video"]
        or any(k in mid for k in ["t2v", "text-to-video", "wan2.1", "ltx-video", "hunyuanvideo", "cogvideo", "svd", "video", "veo"])
        or any("video" in m for m in m_list)
    ):
        return "Génération Vidéo"

    if (
        ptag in ["text-to-image", "image-to-image"]
        or any(k in mid for k in ["flux", "stable-diffusion", "sdxl", "dall-e", "dreamshaper", "midjourney", "imagen", "playground-v2", "-image", "image-generation"])
        or (any("image" in m or "predict" in m for m in m_list) and ("imagen" in mid or "image" in mid))
    ):
        return "Génération Image"

    if any(k in mid for k in ["vision", "vl", "omni", "pixtral", "gemini-1.5", "gemini-2", "gemini-3", "gpt-4o", "claude-3"]):
        return "Vision & Texte"
    if any(k in mid for k in ["coder", "code", "codestral", "deepseek-r1", "math", "qwen2.5-coder", "starcoder"]):
        return "Code & Logique"
    if "audio" in mid or "whisper" in mid or ptag.startswith("audio"):
        return "Audio"
    return "Texte Polyvalent"

def is_allowed_gemini_model(model_id: str, display_name: str = "", domain: str = "") -> bool:
    """Exclut lyria/tts/embedding et ne garde que Gemini 3.5 flash-lite, 3.8 flash, 3.1 pro, Argon et Image/Vidéo Gemini."""
    mid = (model_id or "").lower()
    hay = f"{mid} {display_name}".lower()
    if any(ex in hay for ex in ["lyria", "tts", "embedding", "aqa", "bison", "gecko", "learnlm", "gemma"]):
        return False
    if domain in ["Génération Image", "Génération Vidéo"] or any(k in mid for k in ["imagen", "veo", "-image", "-video"]):
        return True
    if "argon" in hay:
        return True
    if not mid.startswith("gemini-"):
        return False
    if "3.5" in hay and ("flash-lite" in hay or "lite" in hay):
        return True
    if "3.8" in hay and "flash" in hay:
        return True
    if "3.1" in hay and "pro" in hay:
        return True
    return False

def purge_unauthorized_models(db: Session):
    """Purge immédiate en BDD des anciens modèles non autorisés (Groq, DeepSeek, Mistral, Lyria, etc.)."""
    try:
        all_models = db.query(AIModel).all()
        removed = 0
        for m in all_models:
            prov = (m.provider or "").lower()
            if prov not in ["openrouter", "cloudflare", "huggingface", "gemini"]:
                db.delete(m)
                removed += 1
            elif prov == "gemini" and not is_allowed_gemini_model(m.model_id, m.name or "", m.domain or ""):
                db.delete(m)
                removed += 1
        if removed > 0:
            db.commit()
            log_activity(f"[Purge Auto BDD] {removed} modèle(s) non autorisés (ex: lyria/groq) supprimés.")
    except Exception:
        db.rollback()

def is_worker_eligible(model_obj: AIModel) -> bool:
    if not model_obj:
        return False
    prov = (model_obj.provider or "").lower()
    mid = (model_obj.model_id or "").lower()
    dom = model_obj.domain or ""
    if prov in ALLOWED_WORKER_PROVIDERS:
        return True
    if "argon" in mid or prov == "argon":
        return True
    if prov == "gemini" and dom in ["Génération Image", "Génération Vidéo"]:
        return True
    return False

def resolve_gemini_model_id(db: Session, requested_id: str) -> str:
    """Résout le vrai nom du modèle Gemini pour Prompteur/Concaténeur (jamais lyria ni un ancien modèle Groq/OpenRouter)."""
    req_low = (requested_id or "gemini-3.5-flash-lite").lower()

    gemini_models = [
        m for m in db.query(AIModel).filter(AIModel.provider == "gemini").all()
        if is_allowed_gemini_model(m.model_id, m.name or "", m.domain or "")
        and m.domain not in ["Génération Image", "Génération Vidéo"]
    ]

    if not gemini_models:
        if "3.8" in req_low:
            return "gemini-3.8-flash"
        if "3.1" in req_low:
            return "gemini-3.1-pro-preview"
        return "gemini-3.5-flash-lite"

    for m in gemini_models:
        if m.model_id.lower() == req_low or (m.name and m.name.lower() == req_low):
            return m.model_id

    if "argon" in req_low:
        for m in gemini_models:
            if "argon" in m.model_id.lower() or (m.name and "argon" in m.name.lower()):
                return m.model_id
    elif "3.8" in req_low and "flash" in req_low:
        for m in gemini_models:
            if "3.8" in m.model_id.lower() and "flash" in m.model_id.lower():
                return m.model_id
    elif "3.1" in req_low and "pro" in req_low:
        for m in gemini_models:
            if "3.1" in m.model_id.lower() and "pro" in m.model_id.lower():
                return m.model_id
    else:
        for m in gemini_models:
            if "3.5" in m.model_id.lower() and "lite" in m.model_id.lower():
                return m.model_id

    return gemini_models[0].model_id

def get_model_is_free(db: Session, model_id: str) -> bool:
    m = db.query(AIModel).filter(AIModel.model_id == model_id).first()
    if m is not None:
        return bool(m.is_free)
    if ":free" in (model_id or "").lower() or (model_id or "").startswith("@cf/"):
        return True
    return True

def find_quota_fallback_model(db: Session, failed_model_id: str, excluded_ids: set, is_worker: bool = True, target_domain: str = None, strict_is_free: bool = None) -> str:
    """Trouve un modèle de remplacement en respectant STRICTEMENT le caractère Gratuit ou Payant."""
    orig = db.query(AIModel).filter(AIModel.model_id == failed_model_id).first()
    must_be_free = strict_is_free if strict_is_free is not None else (bool(orig.is_free) if orig else True)
    domain_to_match = target_domain or (orig.domain if orig else determine_domain(failed_model_id))

    if not is_worker:
        gem_candidates = [
            g for g in db.query(AIModel).filter(AIModel.provider == "gemini", ~AIModel.model_id.in_(excluded_ids)).all()
            if is_allowed_gemini_model(g.model_id, g.name or "", g.domain or "")
            and g.domain not in ["Génération Image", "Génération Vidéo"]
        ]
        if gem_candidates:
            return gem_candidates[0].model_id
        for fallback_gem in ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.1-pro-preview"]:
            if fallback_gem not in excluded_ids:
                return fallback_gem
        return None

    all_candidates = db.query(AIModel).filter(
        AIModel.is_free == must_be_free,
        ~AIModel.model_id.in_(excluded_ids)
    ).all()

    eligible = [m for m in all_candidates if is_worker_eligible(m)]
    if not eligible:
        return None

    same_domain = [m for m in eligible if m.domain == domain_to_match]
    if domain_to_match in ["Génération Image", "Génération Vidéo"]:
        # Pour l'image et la vidéo, on ne bascule que sur un modèle du même type média
        pool = same_domain
    else:
        pool = same_domain if same_domain else [m for m in eligible if m.domain not in ["Génération Image", "Génération Vidéo"]]

    if not pool:
        return None
    pool.sort(key=lambda x: (x.context_length or 0), reverse=True)
    return pool[0].model_id

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
    try:
        db.query(FinancialLog).filter(~FinancialLog.provider.in_(["OpenRouter", "Cloudflare", "HuggingFace", "Gemini"])).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()

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
            except Exception as e:
                print(f"Erreur Finance OR: {e}")
            
        if settings.cloudflare_api_token: update_finance_db(db, "Cloudflare", 0.0, 0.0)
        if settings.huggingface_api_key: update_finance_db(db, "HuggingFace", 0.0, 0.0)
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
    except Exception as e:
        print(f"Finance DB Error: {e}")

async def sync_providers_models(db: Session, settings: SystemSettings, sync_type: str = "Automatique"):
    if not settings: return {"status": "error", "models_processed": 0}
    log_activity(f"Synchronisation stricte (OpenRouter, Cloudflare, HuggingFace, Gemini ciblé & Argon) [{sync_type}]...")
    added = 0
    models_to_process = {}

    async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
        # 1. OPENROUTER
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
                            arch = ((item.get("architecture") or {}).get("modality") or "").lower()
                            if "->video" in arch:
                                dom = "Génération Vidéo"
                            elif "->image" in arch:
                                dom = "Génération Image"
                            else:
                                dom = determine_domain(m_id)
                            models_to_process[m_id] = {"provider": "openrouter", "name": item.get("name") or m_id, "desc_en": desc_en, "domain": dom, "is_free": is_free, "ctx": item.get("context_length") or 8192, "pp": pp, "pc": pc}
                        except: pass
            except Exception as e: print(f"Erreur OR Models: {e}")

        # 2. CLOUDFLARE WORKERS AI
        if settings.cloudflare_account_id and settings.cloudflare_api_token:
            try:
                url = f"https://api.cloudflare.com/client/v4/accounts/{settings.cloudflare_account_id}/ai/models/search"
                resp = await client.get(url, headers={"Authorization": f"Bearer {settings.cloudflare_api_token}"})
                if resp.status_code == 200 and resp.json():
                    for item in (resp.json().get("result") or []):
                        if not item or not item.get("name"): continue
                        m_id = item.get("name")
                        task_name = ((item.get("task") or {}).get("name") or "").lower()
                        dom = determine_domain(m_id, task_name)
                        models_to_process[m_id] = {"provider": "cloudflare", "name": m_id.split("/")[-1], "desc": item.get("description") or "Modèle Serverless Cloudflare Workers AI.", "domain": dom, "is_free": True, "ctx": 16384, "pp": 0.0, "pc": 0.0}
            except Exception: pass

        # 3. HUGGING FACE
        hf_curated = [
            ("Qwen/Qwen2.5-Coder-32B-Instruct", "Qwen 2.5 Coder 32B (HF)", "Code & Logique", True, 32768),
            ("Qwen/Qwen2.5-72B-Instruct", "Qwen 2.5 72B Instruct (HF)", "Texte Polyvalent", True, 32768),
            ("meta-llama/Llama-3.3-70B-Instruct", "Llama 3.3 70B Instruct (HF)", "Texte Polyvalent", True, 32768),
            ("deepseek-ai/DeepSeek-R1-Distill-Qwen-32B", "DeepSeek R1 Distill 32B (HF)", "Code & Logique", True, 32768),
            ("meta-llama/Llama-3.2-11B-Vision-Instruct", "Llama 3.2 11B Vision (HF)", "Vision & Texte", True, 16384),
            ("black-forest-labs/FLUX.1-schnell", "FLUX.1 Schnell (Image HF)", "Génération Image", True, 4096),
            ("black-forest-labs/FLUX.1-dev", "FLUX.1 Dev (Image HF Pro)", "Génération Image", False, 4096),
            ("stabilityai/stable-diffusion-xl-base-1.0", "Stable Diffusion XL 1.0 (Image HF)", "Génération Image", True, 4096),
            ("ByteDance/SDXL-Lightning", "SDXL Lightning (Image Rapide HF)", "Génération Image", True, 4096),
            ("Lightricks/LTX-Video", "LTX-Video Temps Réel (Vidéo HF)", "Génération Vidéo", True, 4096),
            ("Wan-AI/Wan2.1-T2V-14B", "Wan 2.1 Text-to-Video 14B (Vidéo HF)", "Génération Vidéo", False, 4096),
            ("tencent/HunyuanVideo", "HunyuanVideo HD (Vidéo HF)", "Génération Vidéo", False, 4096),
        ]
        for m_id, name, dom, is_free, ctx in hf_curated:
            models_to_process[m_id] = {
                "provider": "huggingface",
                "name": name,
                "desc": f"Modèle Hugging Face Inference ({dom}).",
                "domain": dom,
                "is_free": is_free,
                "ctx": ctx,
                "pp": 0.0 if is_free else 0.5,
                "pc": 0.0 if is_free else 1.0
            }

        if settings.huggingface_api_key:
            try:
                hf_headers = {"Authorization": f"Bearer {settings.huggingface_api_key}"}
                for ptag in ["text-generation", "text-to-image", "text-to-video"]:
                    hf_resp = await client.get(f"https://huggingface.co/api/models?pipeline_tag={ptag}&inference=warm&sort=downloads&direction=-1&limit=12", headers=hf_headers, timeout=15.0)
                    if hf_resp.status_code == 200 and isinstance(hf_resp.json(), list):
                        for item in hf_resp.json():
                            m_id = item.get("id")
                            if not m_id or m_id in models_to_process: continue
                            dom = determine_domain(m_id, ptag)
                            models_to_process[m_id] = {
                                "provider": "huggingface",
                                "name": m_id.split("/")[-1],
                                "desc": f"Modèle Hugging Face Hub ({dom}).",
                                "domain": dom,
                                "is_free": True,
                                "ctx": 16384,
                                "pp": 0.0,
                                "pc": 0.0
                            }
            except Exception as e:
                print(f"Erreur HF Models: {e}")

        # 4. COMPTE GEMINI (Uniquement les 3 versions + Argon + Image/Vidéo Gemini, sans Lyria)
        if settings.gemini_api_key:
            try:
                resp = await client.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={settings.gemini_api_key}")
                if resp.status_code == 200 and resp.json():
                    for item in (resp.json().get("models") or []):
                        if not item or "name" not in item: continue
                        m_id = item["name"].replace("models/", "")
                        disp_name = item.get("displayName") or m_id
                        methods = item.get("supportedGenerationMethods") or []
                        dom = determine_domain(m_id, "", methods)

                        if is_allowed_gemini_model(m_id, disp_name, dom):
                            role_desc = "Travailleur & Studio Média Gemini" if dom in ["Génération Image", "Génération Vidéo"] or "argon" in m_id.lower() else "Prompteur / Concaténeur Gemini"
                            models_to_process[m_id] = {
                                "provider": "gemini",
                                "name": disp_name,
                                "desc": f"Modèle officiel Google Gemini ({role_desc} - {dom}).",
                                "domain": dom,
                                "is_free": True,
                                "ctx": item.get("inputTokenLimit") or 1000000,
                                "pp": 0.0,
                                "pc": 0.0
                            }
            except Exception as e:
                print(f"Erreur Gemini Models: {e}")

        if not any("argon" in k.lower() for k in models_to_process.keys()):
            models_to_process["argon"] = {
                "provider": "openrouter" if settings.openrouter_api_key else "gemini",
                "name": "Argon (Modèle Spécial)",
                "desc": "Modèle Argon polyvalent activé pour les travailleurs et l'orchestration.",
                "domain": "Code & Logique",
                "is_free": True,
                "ctx": 128000,
                "pp": 0.0,
                "pc": 0.0
            }

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
                existing.provider = data["provider"]; existing.name = data["name"]; existing.pricing_prompt = data["pp"]; existing.pricing_completion = data["pc"]; existing.is_free = data["is_free"]; existing.description_fr = data["desc"]; existing.domain = data["domain"]; existing.context_length = data["ctx"]; existing.last_updated = datetime.now(timezone.utc)
            else:
                db.add(AIModel(provider=data["provider"], model_id=m_id, name=data["name"], description_fr=data["desc"], domain=data["domain"], is_free=data["is_free"], context_length=data["ctx"], pricing_prompt=data["pp"], pricing_completion=data["pc"]))
            added += 1
            if added % 50 == 0: db.commit()
        except IntegrityError: db.rollback()
        except Exception: db.rollback()

    purge_unauthorized_models(db)
    try:
        settings.last_sync_date = datetime.now(timezone.utc)
        settings.last_sync_type = sync_type
        db.commit()
    except Exception:
        db.rollback()
        
    await sync_finances(db, settings)
    log_activity(f"Synchronisation terminée : {added} modèles autorisés actifs.")
    return {"status": "success", "models_processed": added}

def get_client_for_model(db: Session, model_id: str, settings: SystemSettings, is_worker: bool = False):
    model_db = db.query(AIModel).filter(AIModel.model_id == model_id).first()
    provider = (model_db.provider or "openrouter").lower() if model_db else ("gemini" if model_id.lower().startswith("gemini-") else "openrouter")

    if is_worker and provider not in ALLOWED_WORKER_PROVIDERS:
        if provider == "gemini" and ("argon" in model_id.lower() or (model_db and model_db.domain in ["Génération Image", "Génération Vidéo"])):
            provider = "gemini"
        elif model_id.startswith("@cf/"):
            provider = "cloudflare"
        else:
            provider = "openrouter"

    if provider == "gemini" and settings.gemini_api_key:
        return AsyncOpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=settings.gemini_api_key), "gemini"
    elif provider == "cloudflare" and settings.cloudflare_account_id and settings.cloudflare_api_token:
        return AsyncOpenAI(base_url=f"https://api.cloudflare.com/client/v4/accounts/{settings.cloudflare_account_id}/ai/v1", api_key=settings.cloudflare_api_token), "cloudflare"
    elif provider == "huggingface" and settings.huggingface_api_key:
        return AsyncOpenAI(base_url="https://router.huggingface.co/hf-inference/v1", api_key=settings.huggingface_api_key), "huggingface"
    
    return AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=settings.openrouter_api_key), "openrouter"

def compute_dynamic_chunk_size(db: Session, active_model_ids: list) -> int:
    valid_ids = [m for m in active_model_ids if m and m.strip()]
    if not valid_ids:
        return 60000
    models_db = db.query(AIModel).filter(AIModel.model_id.in_(valid_ids)).all()
    contexts = [m.context_length for m in models_db if m.context_length and m.context_length > 0]
    min_ctx = min(contexts) if contexts else 8192

    calculated_chars = int(min_ctx * 0.5 * 3.5)
    chunk_size = max(6000, min(calculated_chars, 150000))
    log_activity(f"Contexte le plus restrictif : {min_ctx} tokens -> Chunk dynamique fixé à {chunk_size} caractères.")
    return chunk_size

def extract_safe_content(resp) -> str:
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

async def ask_agent_with_fallback(db: Session, settings: SystemSettings, model_id: str, messages: list, is_worker: bool = True, enable_web: bool = False) -> str:
    tried_models = set()
    current_model = model_id
    strict_free = get_model_is_free(db, model_id)
    tier_label = "GRATUIT" if strict_free else "PAYANT"

    for attempt in range(4):
        tried_models.add(current_model)
        client, provider = get_client_for_model(db, current_model, settings, is_worker=is_worker)
        try:
            return await ask_agent(client, current_model, messages, provider, enable_web=enable_web)
        except Exception as e:
            err_str = str(e)
            log_activity(f"⚠️ Quota/Erreur sur {current_model} ({tier_label}) : {err_str[:90]}")
            next_model = find_quota_fallback_model(
                db=db,
                failed_model_id=current_model,
                excluded_ids=tried_models,
                is_worker=is_worker,
                strict_is_free=strict_free
            )
            if not next_model:
                raise e
            log_activity(f"🔄 Bascule automatique ({tier_label} respecté) : {current_model} -> {next_model}")
            current_model = next_model

    raise ValueError(f"Tous les modèles ({tier_label}) sollicités ont dépassé leur quota.")

async def _try_single_media_model(client: httpx.AsyncClient, settings: SystemSettings, provider: str, model_id: str, final_prompt: str, media_type: str) -> str:
    # 1. GEMINI IMAGE / VIDEO
    if provider == "gemini":
        if not settings.gemini_api_key:
            raise ValueError("Clé API Gemini manquante.")
        predict_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:predict?key={settings.gemini_api_key}"
        resp = await client.post(predict_url, json={"instances": [{"prompt": final_prompt}], "parameters": {"sampleCount": 1}})
        if resp.status_code == 200:
            try:
                j_data = resp.json()
                preds = j_data.get("predictions") or []
                if preds:
                    pred = preds[0]
                    b64 = pred.get("bytesBase64Encoded") or pred.get("image") or pred.get("video")
                    mime = pred.get("mimeType") or ("video/mp4" if media_type == "video" else "image/png")
                    if b64:
                        return f"data:{mime};base64,{b64}"
            except Exception:
                pass

        gen_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={settings.gemini_api_key}"
        resp2 = await client.post(gen_url, json={
            "contents": [{"parts": [{"text": final_prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}
        })
        if resp2.status_code == 200:
            try:
                candidates = resp2.json().get("candidates") or []
                for c in candidates:
                    for part in ((c.get("content") or {}).get("parts") or []):
                        inline = part.get("inlineData")
                        if inline and inline.get("data"):
                            mime = inline.get("mimeType") or "image/png"
                            return f"data:{mime};base64,{inline['data']}"
            except Exception:
                pass
        raise ValueError(f"Gemini Media ({resp.status_code}): {resp.text[:140]}")

    # 2. HUGGING FACE INFERENCE API (Support hf-inference + fal-ai pour Vidéo/Image)
    elif provider == "huggingface":
        if not settings.huggingface_api_key:
            raise ValueError("Clé API HuggingFace manquante.")
        headers = {"Authorization": f"Bearer {settings.huggingface_api_key.strip()}"}
        urls_to_try = [
            f"https://router.huggingface.co/hf-inference/models/{model_id}",
            f"https://router.huggingface.co/fal-ai/{model_id}"
        ]
        last_hf_err = ""
        for hf_url in urls_to_try:
            resp = await client.post(hf_url, headers=headers, json={"inputs": final_prompt, "prompt": final_prompt})
            if resp.status_code == 200:
                ctype = (resp.headers.get("content-type") or "").lower()
                if "application/json" in ctype:
                    j_resp = resp.json()
                    if isinstance(j_resp, dict):
                        ext_url = (j_resp.get("video") or {}).get("url") or (j_resp.get("images") or [{}])[0].get("url") or j_resp.get("url")
                        if ext_url:
                            return ext_url
                    last_hf_err = f"Réponse JSON HF: {resp.text[:120]}"
                    continue
                mime = "video/mp4" if media_type == "video" else (ctype or "image/png")
                b64 = base64.b64encode(resp.content).decode("utf-8")
                return f"data:{mime};base64,{b64}"
            else:
                last_hf_err = f"HTTP {resp.status_code} ({resp.text[:120]})"
        raise ValueError(f"HuggingFace ({model_id}) indisponible ou quota atteint : {last_hf_err}")

    # 3. CLOUDFLARE WORKERS AI
    elif provider == "cloudflare":
        if not settings.cloudflare_account_id or not settings.cloudflare_api_token:
            raise ValueError("Identifiants Cloudflare manquants.")
        cf_url = f"https://api.cloudflare.com/client/v4/accounts/{settings.cloudflare_account_id.strip()}/ai/run/{model_id}"
        headers = {"Authorization": f"Bearer {settings.cloudflare_api_token.strip()}"}
        resp = await client.post(cf_url, headers=headers, json={"prompt": final_prompt})
        if resp.status_code != 200:
            raise ValueError(f"Cloudflare ({resp.status_code}): {resp.text[:140]}")
        ctype = (resp.headers.get("content-type") or "").lower()
        if "application/json" in ctype:
            j = resp.json()
            b64 = (j.get("result") or {}).get("image")
            if not b64:
                raise ValueError(f"Réponse Cloudflare sans image: {resp.text[:140]}")
        else:
            b64 = base64.b64encode(resp.content).decode("utf-8")
        return f"data:image/png;base64,{b64}"

    # 4. OPENROUTER
    else:
        if not settings.openrouter_api_key:
            raise ValueError("Clé API OpenRouter manquante.")
        headers = {"Authorization": f"Bearer {settings.openrouter_api_key.strip()}", "HTTP-Referer": "https://aethas38.duckdns.org"}
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json={"model": model_id, "messages": [{"role": "user", "content": final_prompt}], "modalities": ["image", "text"]}
        )
        if resp.status_code != 200:
            raise ValueError(f"OpenRouter ({resp.status_code}): {resp.text[:140]}")
        data = resp.json()
        if data.get("error"):
            raise ValueError(f"Erreur OpenRouter: {data['error']}")
        msg = ((data.get("choices") or [{}])[0]).get("message") or {}
        images = msg.get("images") or []
        if images and isinstance(images[0], dict):
            img_url = (images[0].get("image_url") or {}).get("url") or images[0].get("url")
            if img_url:
                return img_url
        content = msg.get("content") or ""
        if "data:image" in content or content.startswith("http"):
            return content.strip()
        raise ValueError("Ce modèle OpenRouter n'a pas renvoyé de média.")

async def generate_media(db: Session, settings: SystemSettings, prompt: str, media_type: str, model_id: str, prompter_id: str = "gemini-3.5-flash-lite", optimize_prompt: bool = True) -> dict:
    try:
        log_activity(f"[Studio {media_type.upper()}] Démarrage avec {model_id}...")
        final_prompt = prompt

        if optimize_prompt and settings.gemini_api_key:
            try:
                real_prompter = resolve_gemini_model_id(db, prompter_id)
                sys_msg = (
                    f"You are an expert visual prompt engineer for AI {media_type} generation. "
                    "Translate the user's French description into a rich, detailed, cinematic English prompt. "
                    "Output ONLY the final English prompt without quotes or explanations."
                )
                final_prompt = await ask_agent_with_fallback(
                    db, settings, real_prompter,
                    [{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}],
                    is_worker=False, enable_web=False
                )
                log_activity(f"[Studio {media_type.upper()}] Prompt optimisé par {real_prompter}.")
            except Exception as e:
                log_activity(f"[Studio] Optimisation ignorée ({str(e)[:50]}), utilisation du prompt original.")

        strict_free = get_model_is_free(db, model_id)
        tier_label = "GRATUIT" if strict_free else "PAYANT"
        target_domain = "Génération Vidéo" if media_type == "video" else "Génération Image"

        tried_models = set()
        current_model = model_id
        last_error = ""

        async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
            for attempt in range(4):
                tried_models.add(current_model)
                model_db = db.query(AIModel).filter(AIModel.model_id == current_model).first()
                if model_db and model_db.provider:
                    provider = model_db.provider.lower()
                elif current_model.startswith("@cf/"):
                    provider = "cloudflare"
                elif any(k in current_model.lower() for k in ["imagen", "veo", "gemini"]):
                    provider = "gemini"
                else:
                    provider = "huggingface"

                try:
                    media_url = await _try_single_media_model(client, settings, provider, current_model, final_prompt, media_type)
                    log_activity(f"✅ [Studio {media_type.upper()}] Généré avec succès via {current_model} ({tier_label}).")
                    return {
                        "media_url": media_url,
                        "media_type": media_type,
                        "optimized_prompt": final_prompt,
                        "model_used": current_model
                    }
                except Exception as e:
                    last_error = str(e)
                    log_activity(f"⚠️ Échec/Quota sur {current_model} ({tier_label}) : {last_error[:90]}")
                    next_mod = find_quota_fallback_model(
                        db=db,
                        failed_model_id=current_model,
                        excluded_ids=tried_models,
                        is_worker=True,
                        target_domain=target_domain,
                        strict_is_free=strict_free
                    )
                    if not next_mod:
                        break
                    log_activity(f"🔄 Bascule automatique Média ({tier_label} strict) : {current_model} -> {next_mod}")
                    current_model = next_mod

        raise HTTPException(
            status_code=400,
            detail=f"Aucun modèle {media_type} ({tier_label}) n'a pu aboutir après bascule automatique. Détail fournisseur : {last_error}"
        )
    except HTTPException:
        raise
    except Exception as e:
        tb_str = traceback.format_exc()
        system_logger.error(f"Erreur Studio Média:\n{tb_str}")
        raise HTTPException(status_code=500, detail=f"Erreur interne Studio Média : {str(e)}")

async def run_orchestrator(db: Session, history: list, settings: SystemSettings, config: dict, extracted_files: list = None) -> str:
    if not config: config = {}
    mode = config.get("mode", "multi")
    theme = config.get("theme", "general")
    enable_web = config.get("enable_web", True)
    workers = [w for w in (config.get("workers") or []) if w and w.strip()]
    if not workers:
        workers = ["Qwen/Qwen2.5-Coder-32B-Instruct"]
    if mode == "mono":
        workers = [workers[0]]

    p_mod = resolve_gemini_model_id(db, config.get("prompter") or "gemini-3.5-flash-lite")
    c_mod = resolve_gemini_model_id(db, config.get("concatenator") or "gemini-3.8-flash")

    user_prompt = (history[-1].content or "") if history else ""
    original_user_text = user_prompt.split("\n\n[Fichiers joints")[0] if "[Fichiers joints" in user_prompt else user_prompt
    formatted_history = [{"role": msg.role, "content": msg.content or ""} for msg in history[:-1]] if len(history) > 1 else []

    all_involved_models = [p_mod] + workers + ([c_mod] if mode == "multi" and len(workers) > 1 else [])
    chunk_size = compute_dynamic_chunk_size(db, all_involved_models)

    is_ocr_ce2 = (theme == "ocr_ce2")
    final_response = ""

    try:
        log_activity(f"Orchestration [{mode.upper()} | Thème: {theme} | Web: {'ON' if enable_web else 'OFF'}]. Prompteur Gemini: {p_mod}")

        files_context = ""
        if extracted_files:
            log_activity(f"Traitement Map-Reduce de {len(extracted_files)} fichier(s) joint(s).")
            async def process_single_file(f):
                if not f or not isinstance(f, dict): return ""
                fname = f.get('name') or 'Fichier_inconnu'
                content = f.get('content') or ''
                is_image = f.get('is_image', False)

                if is_ocr_ce2:
                    file_sys = (
                        "Tu es un système d'OCR scolaire ultra-précis pour une classe de CE2 (enseignante : Céline). "
                        "RÈGLE ABSOLUE ET CRITIQUE : Tu dois transcrire les copies d'élèves À L'IDENTIQUE, mot pour mot, lettre par lettre, chiffre par chiffre. "
                        "NE CORRIGE JAMAIS les fautes d'orthographe, de grammaire, de conjugaison ou les erreurs de calcul mathématique de l'élève lors de la transcription ! "
                        "Si un élève a écrit une erreur, reproduis exactement son erreur. "
                        "Si le fichier est le corrigé de l'enseignante, indique clairement [DOCUMENT CORRIGÉ DE RÉFÉRENCE] et retranscris-le fidèlement."
                    )
                else:
                    file_sys = "You are an expert data analyst and senior developer. Extract the most important technical information from the file without losing critical code syntax."

                if is_image:
                    log_activity(f"Analyse Vision / OCR de l'image {fname}...")
                    user_msg_content = [
                        {"type": "text", "text": f"Demande : '{original_user_text}'.\nFichier image : '{fname}'. Transcris intégralement et littéralement le contenu visible (sans corriger aucune faute si c'est une copie d'élève)."},
                        {"type": "image_url", "image_url": {"url": content}}
                    ]
                    try:
                        analysis = await ask_agent_with_fallback(db, settings, p_mod, [{"role": "system", "content": file_sys}, {"role": "user", "content": user_msg_content}], is_worker=False, enable_web=False)
                        log_activity(f"OCR Vision de {fname} réussi.")
                        return f"\n\n--- Transcription exacte du fichier {fname} ---\n{analysis}"
                    except Exception as e:
                        log_activity(f"Erreur OCR Vision sur {fname}: {str(e)}")
                        return f"\n\n--- Erreur de lecture image sur {fname} ---\n{str(e)}"

                if len(content) > chunk_size:
                    chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]
                    chunk_analyses = []
                    log_activity(f"Fichier lourd ({fname}): Découpage en {len(chunks)} chunks de {chunk_size} car.")
                    for idx, chunk in enumerate(chunks):
                        if is_ocr_ce2:
                            file_prompt = f"Demande : '{original_user_text}'.\nPartie {idx+1}/{len(chunks)} du fichier '{fname}'. Restitue le contenu EXACTEMENT à l'identique sans corriger aucune erreur d'élève :\n```\n{chunk}\n```"
                        else:
                            file_prompt = f"Demande de l'utilisateur : '{original_user_text}'.\n\nPartie {idx+1}/{len(chunks)} du fichier '{fname}'. Analysez, extrayez et résumez le code, VBA, SQL ou les données pertinentes.\n\nContenu :\n```\n{chunk}\n```"
                        try:
                            analysis = await ask_agent_with_fallback(db, settings, p_mod, [{"role": "system", "content": file_sys}, {"role": "user", "content": file_prompt}], is_worker=False, enable_web=False)
                            chunk_analyses.append(analysis or "[ Analyse vide ]")
                            log_activity(f"Chunk {idx+1}/{len(chunks)} de {fname} traité.")
                        except Exception as e:
                            chunk_analyses.append(f"[Erreur sur la partie {idx+1}: {str(e)}]")
                            log_activity(f"Erreur chunk {idx+1}/{len(chunks)} pour {fname}: {str(e)}")
                        await asyncio.sleep(1.5)
                    return f"\n\n--- Extraction du fichier {fname} (en {len(chunks)} parties) ---\n" + "\n".join(chunk_analyses)
                else:
                    if is_ocr_ce2:
                        file_prompt = f"Demande : '{original_user_text}'.\nFichier : '{fname}'. Restitue intégralement et À L'IDENTIQUE (sans corriger les erreurs des élèves) le contenu ci-dessous :\n```\n{content}\n```"
                    else:
                        file_prompt = f"Demande de l'utilisateur : '{original_user_text}'.\n\nAnalysez le fichier ci-dessous. Extrayez, résumez et conservez méticuleusement tout le code, les macros VBA, les requêtes SQL, ou les données métier pertinentes.\n\nFichier : {fname}\nContenu :\n```\n{content}\n```"
                    try:
                        analysis = await ask_agent_with_fallback(db, settings, p_mod, [{"role": "system", "content": file_sys}, {"role": "user", "content": file_prompt}], is_worker=False, enable_web=False)
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
            user_prompt = f"{original_user_text}\n\nVoici les données extraites des fichiers joints :\n{files_context}"

        if is_ocr_ce2:
            log_activity("Structuration de la tâche de correction CE2 (Français strict conservé)...")
            prompt_system = (
                "Tu es un ingénieur pédagogique assistant Céline, professeure des écoles en CE2. "
                "Ne traduis RIEN en anglais. Prépare la consigne complète en français pour le correcteur IA en conservant "
                "STRICTEMENT à l'identique les transcriptions brutes des copies d'élèves (avec toutes leurs fautes d'origine) ainsi que le corrigé de référence."
            )
            optimized = await ask_agent_with_fallback(db, settings, p_mod, [{"role": "system", "content": prompt_system}, {"role": "user", "content": user_prompt}], is_worker=False, enable_web=False)
        else:
            log_activity("Optimisation de la requête via le Prompteur Gemini...")
            prompt_system = "You are an expert prompt engineer. Translate and optimize the user request and any file context into clear, precise English tailored for AI execution. Keep all code blocks and exact data intact."
            optimized = await ask_agent_with_fallback(db, settings, p_mod, [{"role": "system", "content": prompt_system}, {"role": "user", "content": user_prompt}], is_worker=False, enable_web=False)

        worker_sys_prompt = None
        if is_ocr_ce2:
            worker_sys_prompt = (
                "Tu es l'assistant de correction de Céline pour ses élèves de CE2. "
                "RÈGLES IMPÉRATIVES :\n"
                "1. Ne corrige JAMAIS les erreurs (français, mathématiques, autres) dans la version initiale de l'élève : elle doit refléter exactement ce que l'élève a écrit.\n"
                "2. Appuie-toi strictement sur le corrigé fourni pour établir la version corrigée.\n"
                "3. Pour CHAQUE élève, génère un retour structuré contenant :\n"
                "   - **1. Version initiale de l'élève (Transcription exacte non corrigée)**\n"
                "   - **2. Version corrigée (Selon le corrigé officiel)**\n"
                "   - **3. Analyse des erreurs et appréciation bienveillante adaptée au niveau CE2**\n"
                "4. Enveloppe également le bilan complet de chaque élève dans un bloc de code markdown (ex: ```eleve_prenom.md ... ```) pour permettre à Céline de télécharger un fichier par élève en un clic."
            )
        elif mode == "mono":
            worker_sys_prompt = (
                "Tu es un expert technique principal. Réponds directement et de manière complète en FRANÇAIS naturel. "
                "Ne traduis jamais la syntaxe du code source à l'intérieur des blocs de code."
            )

        async def execute_single_worker(w_mod: str) -> str:
            m_db = db.query(AIModel).filter(AIModel.model_id == w_mod).first()
            dom = m_db.domain if m_db else determine_domain(w_mod)
            if dom in ["Génération Image", "Génération Vidéo"]:
                m_type = "video" if dom == "Génération Vidéo" else "image"
                media_res = await generate_media(db, settings, optimized, m_type, w_mod, p_mod, optimize_prompt=False)
                return f"[MEDIA_{m_type.upper()}:{media_res['model_used']}]\n{media_res['media_url']}\nPrompt utilisé : {media_res['optimized_prompt']}"
            msgs = formatted_history.copy()
            if worker_sys_prompt:
                msgs.insert(0, {"role": "system", "content": worker_sys_prompt})
            msgs.append({"role": "user", "content": optimized})
            return await ask_agent_with_fallback(db, settings, w_mod, msgs, is_worker=True, enable_web=enable_web)

        log_activity(f"Exécution sur {len(workers)} travailleur(s) (avec bascule anti-quota active)...")
        if len(workers) == 1:
            worker_response = await execute_single_worker(workers[0])
            responses = [worker_response]
            log_activity(f"Travailleur ({workers[0]}) a terminé.")
        else:
            w_tasks = [execute_single_worker(w) for w in workers]
            responses = await asyncio.gather(*w_tasks, return_exceptions=True)
            log_activity("Tous les travailleurs ont terminé leur analyse.")

        if mode == "mono" or any(str(r).startswith("[MEDIA_") for r in responses):
            log_activity("Restitution directe (Mono-IA / Média généré).")
            final_response = "\n\n".join([str(r) for r in responses])
        else:
            log_activity(f"Synthèse finale via Concaténeur Gemini ({c_mod})...")
            if is_ocr_ce2:
                concat_system = (
                    "Tu es le coordinateur pédagogique de Céline (classe de CE2). "
                    "Fusionne les analyses des experts pour produire le dossier final de correction en français. "
                    "Vérifie que pour CHAQUE élève figurent bien : 1) La version initiale brute (AVEC toutes les fautes d'origine de l'élève intactes), "
                    "2) La version corrigée basée sur le corrigé, et 3) Le retour pédagogique CE2, ainsi qu'un bloc téléchargeable par élève."
                )
            else:
                concat_system = (
                    "You are a master lead developer and technical synthesizer. "
                    "Synthesize the provided expert responses into a single cohesive response. "
                    "Translate all explanatory text, descriptions, and user-facing prose into natural French. "
                    "CRITICAL: Do NOT translate code blocks, programming keywords, or source code contents."
                )
            synth = f"User Request: {original_user_text}\n\n" + "\n".join([f"--- EXPERT {i+1} ---\n{str(r)}" for i, r in enumerate(responses)])
            final_response = await ask_agent_with_fallback(db, settings, c_mod, [{"role": "system", "content": concat_system}, {"role": "user", "content": synth}], is_worker=False, enable_web=False)

        log_activity("Orchestration terminée avec succès.")

    except Exception as e:
        tb_str = traceback.format_exc()
        system_logger.error(f"Traceback complet:\n{tb_str}")
        final_response = f"L'IA a rencontré une erreur critique: {str(e)}"
        log_activity(f"ERREUR CRITIQUE: {str(e)}")
    
    await sync_finances(db, settings)
    return final_response