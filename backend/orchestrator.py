import asyncio
import httpx
import urllib.parse
import traceback
import base64
import os
import re
from typing import Dict, Any
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

# --- ÉTAT TEMPS RÉEL DES PROJETS & RAISONNEMENT EN DIRECT (POINT 1 & 7) ---
project_live_status: Dict[int, Dict[str, Any]] = {}

def set_project_live_status(project_id: int, active: bool, step: str = "", reasoning: str = None):
    if not project_id:
        return
    prev = project_live_status.get(project_id) or {}
    project_live_status[project_id] = {
        "active": active,
        "step": step or prev.get("step") or "Orchestration en cours...",
        "reasoning": reasoning if reasoning is not None else prev.get("reasoning", ""),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

def clear_project_live_status(project_id: int):
    if project_id:
        project_live_status.pop(project_id, None)

# --- CONFIGURATION HERMES & OLLAMA LOCAL (GTX 1650 - 4 Go GDDR6) ---
HERMES_API_URL = os.getenv("HERMES_API_URL", "http://192.168.1.20:8642")
HERMES_API_KEY = os.getenv("HERMES_API_KEY", "87186fe63b1e5d8b8d01bc769f5e894d24081a86d0d800d00b6358c26fded37e")

OLLAMA_CANDIDATE_URLS = [
    os.getenv("OLLAMA_API_URL", "").strip(),
    "http://192.168.1.20:11434",
    "http://host.docker.internal:11434",
    "http://172.17.0.1:11434",
    "http://127.0.0.1:11434"
]
# Modèles légers (< 2.6 Go VRAM en Q4) strictement adaptés à une GeForce GTX 1650 (4 Go GDDR6)
GTX1650_SAFE_MODELS_PRIORITY = [
    "qwen2.5-coder:1.5b",
    "qwen2.5:1.5b",
    "llama3.2:1b",
    "deepseek-r1:1.5b",
    "qwen2.5:3b",
    "llama3.2:3b",
    "gemma2:2b",
    "phi3:mini",
    "smollm2:1.7b",
    "tinyllama"
]

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

def detect_model_capabilities(
    model_id: str,
    provider: str = "",
    domain: str = "",
    arch: dict = None,
    supported_params: list = None,
    description: str = ""
) -> dict:
    """
    Détecte automatiquement les 4 capacités (style LM Studio) :
    - supports_reasoning (Cerveau vert : Raisonnement / Thinking / CoT)
    - supports_tools (Marteau bleu : Tools / Function Calling)
    - supports_vision (Œil ambre : Accepte les images en entrée)
    - supports_audio (Micro violet : Accepte les prompts audio en entrée)
    """
    mid = (model_id or "").lower()
    prov = (provider or "").lower()
    dom = (domain or "")
    desc = (description or "").lower()
    arch = arch or {}
    params = [str(p).lower() for p in (supported_params or [])]

    modality_str = str(arch.get("modality") or "").lower()
    input_mods = [str(x).lower() for x in (arch.get("input_modalities") or [])]

    if dom in ["Génération Image", "Génération Vidéo"]:
        return {
            "reasoning": False,
            "tools": False,
            "vision": any(k in mid for k in ["flux.1-dev", "flux-1-dev", "imagen", "gemini", "gpt-4o", "i2v", "image-to-"]) or "image" in input_mods,
            "audio": False
        }

    reasoning = (
        any(p in params for p in ["reasoning", "include_reasoning", "reasoning_effort", "thinking"])
        or any(k in mid for k in [
            "deepseek-r1", "-r1", "qwq", "o1", "o3", "o4", "thinking", "reason",
            "sonar-reasoning", "gemini-2.5", "gemini-3", "claude-3.7", "claude-4", "magistral", "kimi-k1", "qwen3"
        ])
        or "modèle de raisonnement" in desc
        or "reasoning model" in desc
    )

    tools = (
        any(p in params for p in ["tools", "tool_choice", "functions"])
        or (prov == "gemini" and dom not in ["Génération Image", "Génération Vidéo"])
        or any(k in mid for k in [
            "gpt-4", "gpt-3.5", "claude-3", "claude-4", "gemini-", "qwen2.5", "qwen-2.5", "qwen3",
            "llama-3.1", "llama-3.2", "llama-3.3", "llama-4", "mistral-large", "mistral-small",
            "ministral", "codestral", "pixtral", "deepseek-chat", "deepseek-v3", "command-r",
            "nova-", "hermes", "argon", "function"
        ])
    )
    if any(no_t in mid for no_t in ["deepseek-r1-distill", "whisper", "tts"]):
        if "tools" not in params:
            tools = False

    vision = (
        "image" in input_mods
        or "image+" in modality_str
        or "+image->" in modality_str
        or dom == "Vision & Texte"
        or (prov == "gemini" and dom not in ["Génération Image", "Génération Vidéo"])
        or any(k in mid for k in [
            "vision", "-vl", "vl-", "pixtral", "gpt-4o", "gpt-4-turbo", "claude-3", "claude-4",
            "gemini-", "omni", "llava", "molmo", "internvl", "qvq", "nova-lite", "nova-pro", "nova-2", "gemma-3"
        ])
    )

    audio = (
        "audio" in input_mods
        or "audio" in modality_str
        or dom == "Audio"
        or (prov == "gemini" and dom not in ["Génération Image", "Génération Vidéo"])
        or any(k in mid for k in [
            "audio", "whisper", "omni", "gpt-4o-audio", "gpt-4o-realtime", "gemini-", "ultravox", "voxtral", "qwen2-audio"
        ])
    )

    return {
        "reasoning": bool(reasoning),
        "tools": bool(tools),
        "vision": bool(vision),
        "audio": bool(audio)
    }

def is_allowed_gemini_model(model_id: str, display_name: str = "", domain: str = "") -> bool:
    """Exclut lyria/tts/embedding et ne garde que Gemini 3.5 flash-lite, 3.8 flash, 3.1 pro, Argon et Image/Vidéo Gemini."""
    mid = (model_id or "").lower()
    hay = f"{mid} {display_name}".lower()
    if any(ex in hay for ex in ["lyria", "tts", "embedding", "aqa", "bison", "gecko", "learnlm", "gemma", "flash-lite-image"]):
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
    """Purge immédiate en BDD des anciens modèles non autorisés et met à jour les capacités LM Studio si absentes."""
    try:
        all_models = db.query(AIModel).all()
        removed = 0
        updated_caps = 0
        for m in all_models:
            prov = (m.provider or "").lower()
            if prov not in ["openrouter", "cloudflare", "huggingface", "gemini"]:
                db.delete(m)
                removed += 1
            elif prov == "gemini" and not is_allowed_gemini_model(m.model_id, m.name or "", m.domain or ""):
                db.delete(m)
                removed += 1
            else:
                if not any([m.supports_reasoning, m.supports_tools, m.supports_vision, m.supports_audio]):
                    caps = detect_model_capabilities(m.model_id, m.provider, m.domain, description=m.description_fr or "")
                    m.supports_reasoning = caps["reasoning"]
                    m.supports_tools = caps["tools"]
                    m.supports_vision = caps["vision"]
                    m.supports_audio = caps["audio"]
                    updated_caps += 1
        if removed > 0 or updated_caps > 0:
            db.commit()
            if removed > 0:
                log_activity(f"[Purge Auto BDD] {removed} modèle(s) non autorisés supprimés.")
            if updated_caps > 0:
                log_activity(f"[Capacités IA] {updated_caps} modèle(s) enrichis (Vision, Tools, Raisonnement, Audio).")
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
    """Résout le modèle pour Prompteur/Concaténeur : accepte Gemini autorisé, Argon, ou un modèle gratuit OpenRouter sélectionné."""
    req_clean = (requested_id or "gemini-3.5-flash-lite").strip()
    req_low = req_clean.lower()

    existing_model = db.query(AIModel).filter(AIModel.model_id == req_clean).first()
    if existing_model:
        prov = (existing_model.provider or "").lower()
        if prov == "openrouter" and existing_model.is_free and existing_model.domain not in ["Génération Image", "Génération Vidéo"]:
            return existing_model.model_id
        if "argon" in req_low:
            return existing_model.model_id
        if prov == "gemini" and is_allowed_gemini_model(existing_model.model_id, existing_model.name or "", existing_model.domain or ""):
            return existing_model.model_id

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

def _score_openrouter_free_fallback(m: AIModel, target_domain: str, required_ctx: int = 8192, orig: AIModel = None) -> int:
    """Calcule un score de pertinence pour choisir le modèle gratuit OpenRouter le plus adapté."""
    score = 0
    mid = (m.model_id or "").lower()
    dom = m.domain or "Texte Polyvalent"
    ctx = m.context_length or 8192

    if dom == target_domain:
        score += 100
    elif target_domain == "Code & Logique" and dom == "Texte Polyvalent":
        score += 40
    elif target_domain == "Texte Polyvalent" and dom in ["Code & Logique", "Vision & Texte"]:
        score += 50

    if orig:
        if orig.supports_reasoning and m.supports_reasoning:
            score += 60
        if orig.supports_tools and m.supports_tools:
            score += 50
        if orig.supports_vision and m.supports_vision:
            score += 70
        if orig.supports_audio and m.supports_audio:
            score += 70

    if ctx >= required_ctx:
        score += 50
    score += min(int(ctx / 4000), 40)

    preferred_keywords = ["gemini", "qwen-2.5-coder", "qwen2.5", "deepseek", "llama-3.3", "llama-3.1", "mistral", "pixtral", "vl"]
    for idx, kw in enumerate(preferred_keywords):
        if kw in mid:
            score += (35 - idx * 3)
            break

    return score

def find_quota_fallback_model(
    db: Session,
    failed_model_id: str,
    excluded_ids: set,
    is_worker: bool = True,
    target_domain: str = None,
    strict_is_free: bool = None,
    min_required_context: int = None
) -> str:
    """
    Trouve un modèle de remplacement disponible :
    - Pour Prompteur/Concaténeur (is_worker=False) : bascule en priorité sur gemini-3.5-flash-lite
      ou sur le modèle GRATUIT OpenRouter le plus adapté au domaine et au contexte.
    - Pour Travailleur (is_worker=True) : respecte STRICTEMENT les mêmes pré-requis que la sélection
      initiale (Gratuit/Payant, Domaine fonctionnel, Capacités Vision/Tools/Raisonnement/Audio et contexte).
    """
    orig = db.query(AIModel).filter(AIModel.model_id == failed_model_id).first()
    domain_to_match = target_domain or (orig.domain if orig else determine_domain(failed_model_id))
    req_ctx = min_required_context or (orig.context_length if orig and orig.context_length else 8192)

    if not is_worker:
        gem_lite_id = resolve_gemini_model_id(db, "gemini-3.5-flash-lite")
        if gem_lite_id not in excluded_ids and "gemini-3.5-flash-lite" not in excluded_ids:
            return gem_lite_id

        gem_candidates = [
            g for g in db.query(AIModel).filter(AIModel.provider == "gemini", ~AIModel.model_id.in_(excluded_ids)).all()
            if is_allowed_gemini_model(g.model_id, g.name or "", g.domain or "")
            and g.domain not in ["Génération Image", "Génération Vidéo"]
        ]
        if gem_candidates:
            gem_candidates.sort(key=lambda x: (0 if "lite" in x.model_id.lower() else 1))
            return gem_candidates[0].model_id

        or_free_candidates = [
            m for m in db.query(AIModel).filter(
                AIModel.provider == "openrouter",
                AIModel.is_free == True,
                ~AIModel.model_id.in_(excluded_ids)
            ).all()
            if m.domain not in ["Génération Image", "Génération Vidéo", "Audio"]
        ]
        if domain_to_match == "Vision & Texte":
            vision_or = [m for m in or_free_candidates if m.domain == "Vision & Texte" or m.supports_vision]
            if vision_or:
                or_free_candidates = vision_or

        if or_free_candidates:
            or_free_candidates.sort(
                key=lambda m: _score_openrouter_free_fallback(m, domain_to_match, req_ctx, orig),
                reverse=True
            )
            return or_free_candidates[0].model_id

        return None

    # --- MODE TRAVAILLEUR : Respect strict des pré-requis de la sélection initiale ---
    must_be_free = strict_is_free if strict_is_free is not None else (bool(orig.is_free) if orig else True)

    all_candidates = db.query(AIModel).filter(
        AIModel.is_free == must_be_free,
        ~AIModel.model_id.in_(excluded_ids)
    ).all()

    eligible = [m for m in all_candidates if is_worker_eligible(m)]
    if not eligible:
        return None

    same_domain = [m for m in eligible if m.domain == domain_to_match]
    if domain_to_match in ["Génération Image", "Génération Vidéo"]:
        provider_priority = {"huggingface": 3, "cloudflare": 2, "openrouter": 1, "gemini": 0}
        same_domain.sort(key=lambda x: (provider_priority.get((x.provider or "").lower(), 0), x.context_length or 0), reverse=True)
        return same_domain[0].model_id if same_domain else None
    else:
        pool = same_domain if same_domain else [m for m in eligible if m.domain not in ["Génération Image", "Génération Vidéo"]]

    if not pool:
        return None

    if orig:
        strict_prereq_pool = [
            m for m in pool
            if (not orig.supports_vision or m.supports_vision)
            and (not orig.supports_audio or m.supports_audio)
            and (not orig.supports_tools or m.supports_tools)
            and (not orig.supports_reasoning or m.supports_reasoning)
        ]
        if strict_prereq_pool:
            pool = strict_prereq_pool

    compat_ctx_pool = [m for m in pool if (m.context_length or 0) >= req_ctx]
    final_pool = compat_ctx_pool if compat_ctx_pool else pool

    final_pool.sort(
        key=lambda x: (
            1 if (x.provider or "").lower() == "openrouter" else 0,
            _score_openrouter_free_fallback(x, domain_to_match, req_ctx, orig),
            x.context_length or 0
        ),
        reverse=True
    )
    return final_pool[0].model_id

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
    log_activity(f"Synchronisation stricte + Capacités LM Studio (Vision, Tools, Raisonnement, Audio) [{sync_type}]...")
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
                            arch_obj = item.get("architecture") or {}
                            arch = (arch_obj.get("modality") or "").lower()
                            sup_params = item.get("supported_parameters") or []
                            if "->video" in arch:
                                dom = "Génération Vidéo"
                            elif "->image" in arch:
                                dom = "Génération Image"
                            else:
                                dom = determine_domain(m_id)
                            caps = detect_model_capabilities(m_id, "openrouter", dom, arch_obj, sup_params, desc_en)
                            models_to_process[m_id] = {
                                "provider": "openrouter",
                                "name": item.get("name") or m_id,
                                "desc_en": desc_en,
                                "domain": dom,
                                "is_free": is_free,
                                "ctx": item.get("context_length") or 8192,
                                "pp": pp,
                                "pc": pc,
                                "caps": caps
                            }
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
                        desc_cf = item.get("description") or "Modèle Serverless Cloudflare Workers AI."
                        caps = detect_model_capabilities(m_id, "cloudflare", dom, description=desc_cf)
                        models_to_process[m_id] = {
                            "provider": "cloudflare",
                            "name": m_id.split("/")[-1],
                            "desc": desc_cf,
                            "domain": dom,
                            "is_free": True,
                            "ctx": 16384,
                            "pp": 0.0,
                            "pc": 0.0,
                            "caps": caps
                        }
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
            caps = detect_model_capabilities(m_id, "huggingface", dom)
            models_to_process[m_id] = {
                "provider": "huggingface",
                "name": name,
                "desc": f"Modèle Hugging Face Inference ({dom}).",
                "domain": dom,
                "is_free": is_free,
                "ctx": ctx,
                "pp": 0.0 if is_free else 0.5,
                "pc": 0.0 if is_free else 1.0,
                "caps": caps
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
                            caps = detect_model_capabilities(m_id, "huggingface", dom)
                            models_to_process[m_id] = {
                                "provider": "huggingface",
                                "name": m_id.split("/")[-1],
                                "desc": f"Modèle Hugging Face Hub ({dom}).",
                                "domain": dom,
                                "is_free": True,
                                "ctx": 16384,
                                "pp": 0.0,
                                "pc": 0.0,
                                "caps": caps
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
                            caps = detect_model_capabilities(m_id, "gemini", dom)
                            models_to_process[m_id] = {
                                "provider": "gemini",
                                "name": disp_name,
                                "desc": f"Modèle officiel Google Gemini ({role_desc} - {dom}).",
                                "domain": dom,
                                "is_free": True,
                                "ctx": item.get("inputTokenLimit") or 1000000,
                                "pp": 0.0,
                                "pc": 0.0,
                                "caps": caps
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
                "pc": 0.0,
                "caps": {"reasoning": True, "tools": True, "vision": True, "audio": False}
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
            caps = data.get("caps") or detect_model_capabilities(m_id, data["provider"], data["domain"], description=data.get("desc", ""))
            existing = db.query(AIModel).filter(AIModel.model_id == m_id).first()
            if existing:
                existing.provider = data["provider"]
                existing.name = data["name"]
                existing.pricing_prompt = data["pp"]
                existing.pricing_completion = data["pc"]
                existing.is_free = data["is_free"]
                existing.description_fr = data["desc"]
                existing.domain = data["domain"]
                existing.context_length = data["ctx"]
                existing.supports_reasoning = caps["reasoning"]
                existing.supports_tools = caps["tools"]
                existing.supports_vision = caps["vision"]
                existing.supports_audio = caps["audio"]
                existing.last_updated = datetime.now(timezone.utc)
            else:
                db.add(AIModel(
                    provider=data["provider"],
                    model_id=m_id,
                    name=data["name"],
                    description_fr=data["desc"],
                    domain=data["domain"],
                    is_free=data["is_free"],
                    context_length=data["ctx"],
                    pricing_prompt=data["pp"],
                    pricing_completion=data["pc"],
                    supports_reasoning=caps["reasoning"],
                    supports_tools=caps["tools"],
                    supports_vision=caps["vision"],
                    supports_audio=caps["audio"]
                ))
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
    log_activity(f"Synchronisation terminée : {added} modèles autorisés actifs avec badges LM Studio.")
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

# --- CALCUL DU CONTEXTE MAXIMAL AVEC 10% DE MARGE STRICTE (POINT 4) ---
def compute_dynamic_chunk_size(db: Session, active_model_ids: list) -> int:
    """
    Extrait le contexte maximal autorisé (context_length) de tous les modèles sélectionnés
    et fixe la limite au plus près du modèle le plus restrictif en gardant 10% de marge (90% utiles).
    """
    valid_ids = []
    for m in active_model_ids:
        if m and m.strip() and m.strip() not in valid_ids:
            valid_ids.append(m.strip())
    if not valid_ids:
        return 24000

    models_db = db.query(AIModel).filter(AIModel.model_id.in_(valid_ids)).all()
    db_map = {m.model_id: m.context_length for m in models_db if m.context_length and m.context_length > 0}

    contexts = []
    for mid in valid_ids:
        if mid in db_map:
            contexts.append(db_map[mid])
        elif mid.lower().startswith("gemini-") or "argon" in mid.lower():
            contexts.append(128000)
        elif mid.startswith("@cf/"):
            contexts.append(16384)
        else:
            contexts.append(8192)

    min_ctx = min(contexts) if contexts else 8192
    # 90% du contexte maximal autorisé (10% de marge de sécurité) * ~3.8 caractères par token
    safe_tokens = int(min_ctx * 0.90)
    calculated_chars = int(safe_tokens * 3.8)
    chunk_size = max(4000, min(calculated_chars, 360000))
    log_activity(f"[Contexte IA] Max autorisé: {min_ctx} tokens -> Marge 10% appliquée ({safe_tokens} tokens / {chunk_size} car. max par chunk).")
    return chunk_size

def split_text_smart_with_margin(text: str, max_chars_per_chunk: int) -> list:
    """
    Découpe intelligemment un texte ou code dépassant la limite (90% du contexte)
    au plus près de max_chars_per_chunk le long des sauts de ligne sans couper de ligne au milieu.
    """
    if not text:
        return [""]
    if len(text) <= max_chars_per_chunk:
        return [text]

    chunks = []
    start = 0
    total_len = len(text)
    while start < total_len:
        end = min(start + max_chars_per_chunk, total_len)
        if end < total_len:
            # Cherche un double saut de ligne ou un saut de ligne simple dans les derniers 15% du chunk
            search_zone_start = start + int(max_chars_per_chunk * 0.85)
            split_pos = text.rfind("\n\n", search_zone_start, end)
            if split_pos == -1:
                split_pos = text.rfind("\n", search_zone_start, end)
            if split_pos != -1 and split_pos > start:
                end = split_pos + 1
        chunks.append(text[start:end])
        start = end
    return chunks

# --- CASCADE DE CHUNKING HYBRIDE : HERMES (POINT 2) -> OLLAMA GTX 1650 4Go (POINT 9) -> CLOUD (POINT 3) ---
async def detect_local_ollama_gtx1650() -> tuple[str, str]:
    """
    Vérifie si Ollama est installé et accessible sur le réseau local, et sélectionne un modèle
    compatible avec une GeForce GTX 1650 (4 Go de GDDR6, < 3.2 Go de poids).
    """
    async with httpx.AsyncClient(timeout=2.5) as client:
        for base_url in OLLAMA_CANDIDATE_URLS:
            if not base_url:
                continue
            clean_url = base_url.rstrip("/")
            try:
                resp = await client.get(f"{clean_url}/api/tags")
                if resp.status_code == 200:
                    models_list = resp.json().get("models") or []
                    if not models_list:
                        continue
                    # Filtrer les modèles qui tiennent dans les 4 Go de GDDR6 de la GTX 1650 (< 3.3 Go)
                    safe_installed = []
                    for m in models_list:
                        m_name = (m.get("name") or "").lower()
                        m_size = int(m.get("size") or 0)
                        if m_size == 0 or m_size <= 3300000000:
                            safe_installed.append(m.get("name"))
                    if not safe_installed:
                        continue
                    for pref in GTX1650_SAFE_MODELS_PRIORITY:
                        for inst in safe_installed:
                            if pref in inst.lower():
                                return clean_url, inst
                    return clean_url, safe_installed[0]
            except Exception:
                continue
    return None, None

async def try_hermes_chunk_processing(chunk_text: str, user_goal: str, chunk_idx: int, total_chunks: int, is_ocr_ce2: bool = False) -> str:
    """Utilise la compétence de chunking / synthèse de l'instance Hermes si elle est en ligne (Point 2)."""
    headers = {
        "Authorization": f"Bearer {HERMES_API_KEY}",
        "X-API-Key": HERMES_API_KEY,
        "Content-Type": "application/json"
    }
    sys_instruction = (
        "Tu es le module de Chunking de Hermes Agent. "
        + (
            "Transcris et restitue INTÉGRALEMENT et À L'IDENTIQUE ce segment (sans jamais corriger les fautes d'élèves)."
            if is_ocr_ce2 else
            "Analyse ce segment de contexte (chunk), conserve l'intégralité du code, des structures techniques et des informations clés utiles à la demande, en le structurant proprement."
        )
    )
    user_msg = f"Objectif global : {user_goal}\n[Chunk {chunk_idx}/{total_chunks} - Marge 10% respectée] :\n{chunk_text}"

    async with httpx.AsyncClient(timeout=90.0) as client:
        try:
            resp = await client.post(
                f"{HERMES_API_URL}/v1/chat/completions",
                headers=headers,
                json={
                    "model": "hermes-agent",
                    "messages": [
                        {"role": "system", "content": sys_instruction},
                        {"role": "user", "content": user_msg}
                    ]
                }
            )
            if resp.status_code == 200:
                choices = resp.json().get("choices") or []
                if choices and choices[0].get("message", {}).get("content"):
                    log_activity(f"[Chunking Hermes] Chunk {chunk_idx}/{total_chunks} traité par la compétence Hermes.")
                    return choices[0]["message"]["content"]
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
    return None

async def try_ollama_chunk_processing(ollama_url: str, ollama_model: str, chunk_text: str, user_goal: str, chunk_idx: int, total_chunks: int, is_ocr_ce2: bool = False) -> str:
    """Exécute le chunking sur l'IA locale Ollama en limitant la VRAM pour la GTX 1650 4 Go GDDR6 (Point 9)."""
    if not ollama_url or not ollama_model:
        return None
    # Sur une GTX 1650 4 Go, on limite num_ctx à 4096 tokens max pour éviter tout débordement VRAM
    safe_local_chunk = chunk_text[:12000]
    sys_instruction = (
        "Tu es un extracteur de contexte local rapide. "
        + (
            "Recopie exactement à l'identique sans corriger aucune faute."
            if is_ocr_ce2 else
            "Extrais et conserve tous les éléments techniques, extraits de code, variables et données importantes de ce bloc pour répondre à la demande."
        )
    )
    async with httpx.AsyncClient(timeout=90.0) as client:
        try:
            resp = await client.post(
                f"{ollama_url}/api/chat",
                json={
                    "model": ollama_model,
                    "stream": False,
                    "options": {
                        "num_ctx": 4096,
                        "temperature": 0.1
                    },
                    "messages": [
                        {"role": "system", "content": sys_instruction},
                        {"role": "user", "content": f"Demande : {user_goal}\n\nSegment ({chunk_idx}/{total_chunks}) :\n{safe_local_chunk}"}
                    ]
                }
            )
            if resp.status_code == 200:
                content = (resp.json().get("message") or {}).get("content")
                if content:
                    log_activity(f"[Chunking Ollama GTX 1650] Chunk {chunk_idx}/{total_chunks} traité localement via {ollama_model}.")
                    return content
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
    return None

async def smart_chunk_text_pipeline(
    db: Session,
    settings: SystemSettings,
    full_text: str,
    user_goal: str,
    max_chunk_chars: int,
    fallback_prompter_id: str,
    is_ocr_ce2: bool = False,
    project_id: int = None,
    label: str = "Contexte"
) -> str:
    """
    Pipeline complet de Chunking (Points 2, 3, 4, 9) :
    Si le texte dépasse max_chunk_chars (90% du contexte max autorisé) :
    1. Découpe au plus près avec 10% de marge.
    2. Tente la compétence de chunking d'Hermes.
    3. Sinon vérifie si Ollama est installé (optimisé GTX 1650 4 Go GDDR6) et l'utilise.
    4. Sinon utilise l'IA serveur/cloud (Prompteur) pour condenser les chunks.
    """
    if len(full_text) <= max_chunk_chars:
        return full_text

    chunks = split_text_smart_with_margin(full_text, max_chunk_chars)
    total_c = len(chunks)
    log_activity(f"[Chunking Auto 90%] {label} ({len(full_text)} car.) dépasse la limite ({max_chunk_chars} car.) -> Découpé en {total_c} chunks.")
    if project_id:
        set_project_live_status(
            project_id, True,
            f"Découpage intelligent ({total_c} chunks avec 10% de marge)...",
            f"Le volume ({len(full_text)} caractères) dépasse 90% du contexte autorisé ({max_chunk_chars} car.). Découpage en {total_c} parties."
        )

    ollama_url, ollama_model = await detect_local_ollama_gtx1650()
    if ollama_url and ollama_model:
        log_activity(f"[Ollama Détecté] Modèle compatible GTX 1650 (4 Go GDDR6) prêt : {ollama_model} sur {ollama_url}")

    processed_parts = []
    for idx, ch in enumerate(chunks, start=1):
        if project_id:
            set_project_live_status(
                project_id, True,
                f"Chunking {label} : traitement de la partie {idx}/{total_c}...",
                f"Analyse du chunk {idx}/{total_c} ({len(ch)} car.) via cascade Hermes -> Ollama GTX 1650 -> Cloud IA..."
            )

        # 1. Compétence de chunking Hermes
        res_chunk = await try_hermes_chunk_processing(ch, user_goal, idx, total_c, is_ocr_ce2=is_ocr_ce2)

        # 2. IA locale Ollama (GTX 1650 4 Go) si chunk adapté
        if not res_chunk and ollama_url and ollama_model and len(ch) <= 14000:
            res_chunk = await try_ollama_chunk_processing(ollama_url, ollama_model, ch, user_goal, idx, total_c, is_ocr_ce2=is_ocr_ce2)

        # 3. IA Serveur / Cloud (Prompteur)
        if not res_chunk:
            sys_c = (
                "Tu es un module d'extraction fidèle. Restitue à l'identique sans corriger les fautes."
                if is_ocr_ce2 else
                "Tu es un ingénieur de contexte. Résume et extrait tout le code, la structure et les données techniques essentielles de ce chunk pour répondre à la demande de l'utilisateur."
            )
            prompt_c = f"Demande : {user_goal}\n\nChunk {idx}/{total_c} :\n```\n{ch}\n```"
            try:
                res_chunk = await ask_agent_with_fallback(
                    db, settings, fallback_prompter_id,
                    [{"role": "system", "content": sys_c}, {"role": "user", "content": prompt_c}],
                    is_worker=False, enable_web=False, project_id=project_id
                )
                log_activity(f"[Chunking IA Serveur] Chunk {idx}/{total_c} traité via {fallback_prompter_id}.")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                res_chunk = ch[: max(2000, int(max_chunk_chars / total_c))]
                log_activity(f"[Chunking Secours] Découpage direct sur chunk {idx}/{total_c} ({str(e)[:50]}).")

        processed_parts.append(f"### [Segment {idx}/{total_c}]\n{res_chunk}")
        await asyncio.sleep(0.4)

    combined = "\n\n".join(processed_parts)
    if len(combined) > max_chunk_chars:
        combined = combined[:max_chunk_chars]
    return combined

def extract_safe_content(resp, project_id: int = None, model_label: str = "") -> str:
    """Extrait le contenu ET capture le raisonnement du modèle (Point 1) s'il est présent."""
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

    # Extraction du raisonnement natif (DeepSeek-R1, OpenRouter reasoning, QwQ, etc.)
    reasoning = (
        getattr(msg, "reasoning_content", None)
        or getattr(msg, "reasoning", None)
        or (msg.get("reasoning_content") if isinstance(msg, dict) else None)
        or (msg.get("reasoning") if isinstance(msg, dict) else None)
    )

    content_str = str(content) if content is not None else ""

    # Détection des balises <think>...</think> dans le flux texte
    think_match = re.search(r"<think>([\s\S]*?)</think>", content_str, re.IGNORECASE)
    if think_match and not reasoning:
        reasoning = think_match.group(1).strip()

    if reasoning:
        clean_r = str(reasoning).strip()
        if project_id and clean_r:
            set_project_live_status(
                project_id,
                True,
                f"Raisonnement de {model_label or 'l’IA'} acquis...",
                f"🧠 [{model_label or 'Modèle'}]\n{clean_r[:1500]}"
            )
        if "<think>" not in content_str and clean_r:
            content_str = f"<think>\n{clean_r}\n</think>\n\n{content_str}"

    if not content_str.strip():
        raise ValueError("Le modèle a renvoyé un contenu vide.")
    return content_str

async def ask_agent(client, model_id, messages, provider="openrouter", enable_web=True, project_id: int = None) -> str:
    kwargs = {"model": model_id, "messages": messages}
    if provider == "openrouter": 
        kwargs["extra_headers"] = {"HTTP-Referer": "https://aethas38.duckdns.org", "X-Title": "AETHAS38 Orchestrator"}
        plugins = [{"id": "context-compression"}]
        if enable_web:
            plugins.append({"id": "web"})
        kwargs["extra_body"] = {"plugins": plugins, "include_reasoning": True}
        
        try:
            resp = await client.chat.completions.create(**kwargs)
            return extract_safe_content(resp, project_id=project_id, model_label=model_id)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if enable_web:
                log_activity(f"Repli sans plugin web pour {model_id} : {str(e)[:80]}")
                kwargs["extra_body"] = {"plugins": [{"id": "context-compression"}], "include_reasoning": True}
                resp = await client.chat.completions.create(**kwargs)
                return extract_safe_content(resp, project_id=project_id, model_label=model_id)
            raise e
    else:
        resp = await client.chat.completions.create(**kwargs)
        return extract_safe_content(resp, project_id=project_id, model_label=model_id)

async def ask_agent_with_fallback(
    db: Session,
    settings: SystemSettings,
    model_id: str,
    messages: list,
    is_worker: bool = True,
    enable_web: bool = False,
    target_domain: str = None,
    min_required_context: int = None,
    project_id: int = None
) -> str:
    tried_models = set()
    current_model = model_id
    strict_free = True if not is_worker else get_model_is_free(db, model_id)
    tier_label = "GRATUIT" if strict_free else "PAYANT"
    role_label = "Travailleur" if is_worker else "Prompteur/Concaténeur"

    for attempt in range(5):
        tried_models.add(current_model)
        client, provider = get_client_for_model(db, current_model, settings, is_worker=is_worker)
        if project_id:
            m_obj = db.query(AIModel).filter(AIModel.model_id == current_model).first()
            has_reason = bool(m_obj and m_obj.supports_reasoning) or any(k in current_model.lower() for k in ["r1", "qwq", "thinking", "reason", "gemini-2.5", "gemini-3", "qwen3"])
            set_project_live_status(
                project_id,
                True,
                f"{role_label} ({current_model}) en cours de réflexion..." if has_reason else f"{role_label} ({current_model}) traite la requête...",
                f"🧠 Modèle de raisonnement actif : {current_model}\nAnalyse logique et génération des chaînes de pensée en cours..." if has_reason else None
            )
        try:
            return await ask_agent(client, current_model, messages, provider, enable_web=enable_web, project_id=project_id)
        except asyncio.CancelledError:
            log_activity(f"🛑 Requête interrompue par l'utilisateur sur {current_model}.")
            raise
        except Exception as e:
            err_str = str(e)
            log_activity(f"⚠️ Quota/Erreur {role_label} sur {current_model} ({tier_label}) : {err_str[:90]}")
            next_model = find_quota_fallback_model(
                db=db,
                failed_model_id=current_model,
                excluded_ids=tried_models,
                is_worker=is_worker,
                target_domain=target_domain,
                strict_is_free=strict_free,
                min_required_context=min_required_context
            )
            if not next_model:
                raise e
            log_activity(f"🔄 Bascule auto {role_label} ({tier_label} / mêmes pré-requis) : {current_model} -> {next_model}")
            current_model = next_model

    raise ValueError(f"Tous les modèles {role_label} ({tier_label}) sollicités ont dépassé leur quota.")

async def _try_single_media_model(
    client: httpx.AsyncClient,
    settings: SystemSettings,
    provider: str,
    model_id: str,
    final_prompt: str,
    media_type: str,
    input_images: list = None
) -> str:
    # 1. GEMINI IMAGE / VIDEO (Supporte aussi les images de référence en entrée via generateContent)
    if provider == "gemini":
        if not settings.gemini_api_key:
            raise ValueError("Clé API Gemini manquante.")

        errors_collected = []
        if model_id.lower().startswith("gemini-") or (input_images and media_type == "image"):
            gen_model = model_id if model_id.lower().startswith("gemini-") else "gemini-2.0-flash-exp-image-generation"
            gen_url = f"https://generativelanguage.googleapis.com/v1beta/models/{gen_model}:generateContent?key={settings.gemini_api_key}"
            parts = [{"text": final_prompt}]
            for img in (input_images or []):
                content_str = img.get("content", "") if isinstance(img, dict) else getattr(img, "content", "")
                if content_str.startswith("data:"):
                    try:
                        header, b64_img = content_str.split(",", 1)
                        mime_img = header.split(";")[0].replace("data:", "") or "image/png"
                        parts.append({"inlineData": {"mimeType": mime_img, "data": b64_img}})
                    except Exception:
                        pass

            resp2 = await client.post(gen_url, json={
                "contents": [{"parts": parts}],
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
            errors_collected.append(f"generateContent({resp2.status_code})")

        predict_models = [model_id]
        if media_type == "image" and "imagen-3.0-generate-002" not in predict_models:
            predict_models.append("imagen-3.0-generate-002")

        for p_mod in predict_models:
            predict_url = f"https://generativelanguage.googleapis.com/v1beta/models/{p_mod}:predict?key={settings.gemini_api_key}"
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
            errors_collected.append(f"{p_mod}({resp.status_code}): {resp.text[:100]}")

        raise ValueError(f"Gemini Media indisponible: {' | '.join(errors_collected)}")

    # 2. HUGGING FACE INFERENCE API
    elif provider == "huggingface":
        if not settings.huggingface_api_key:
            raise ValueError("Clé API HuggingFace manquante.")
        headers = {"Authorization": f"Bearer {settings.huggingface_api_key.strip()}"}
        endpoints_to_try = [
            (f"https://router.huggingface.co/hf-inference/models/{model_id}", {"inputs": final_prompt}),
            (f"https://router.huggingface.co/fal-ai/{model_id}", {"prompt": final_prompt})
        ]
        last_hf_err = ""
        for hf_url, payload_json in endpoints_to_try:
            resp = await client.post(hf_url, headers=headers, json=payload_json)
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

    # 4. OPENROUTER (Supporte l'envoi d'images de référence dans messages)
    else:
        if not settings.openrouter_api_key:
            raise ValueError("Clé API OpenRouter manquante.")
        headers = {"Authorization": f"Bearer {settings.openrouter_api_key.strip()}", "HTTP-Referer": "https://aethas38.duckdns.org"}
        user_content = final_prompt
        if input_images:
            user_content = [{"type": "text", "text": final_prompt}]
            for img in input_images:
                c_str = img.get("content", "") if isinstance(img, dict) else getattr(img, "content", "")
                if c_str.startswith("data:"):
                    user_content.append({"type": "image_url", "image_url": {"url": c_str}})

        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json={"model": model_id, "messages": [{"role": "user", "content": user_content}], "modalities": ["image", "text"]}
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

async def generate_media(
    db: Session,
    settings: SystemSettings,
    prompt: str,
    media_type: str,
    model_id: str,
    prompter_id: str = "gemini-3.5-flash-lite",
    optimize_prompt: bool = True,
    input_images: list = None
) -> dict:
    try:
        log_activity(f"[Studio {media_type.upper()}] Démarrage avec {model_id} ({len(input_images or [])} image(s) jointe(s))...")
        final_prompt = prompt

        if (optimize_prompt or input_images) and (settings.gemini_api_key or settings.openrouter_api_key):
            try:
                real_prompter = resolve_gemini_model_id(db, prompter_id)
                if input_images:
                    log_activity(f"[Studio {media_type.upper()}] Analyse visuelle de {len(input_images)} image(s) de référence via {real_prompter}...")
                    sys_msg = (
                        f"You are an expert visual prompt engineer for AI {media_type} generation and image-to-image synthesis. "
                        "Analyze the attached reference image(s) in detail (subject, composition, lighting, colors, style) and combine them "
                        "with the user's French instruction into a single rich, detailed, cinematic English generation prompt. "
                        "Output ONLY the final English prompt without quotes or explanations."
                    )
                    user_parts = [{"type": "text", "text": f"User instruction: {prompt or 'Reproduce and enhance this visual scene with high fidelity.'}"}]
                    for img in input_images:
                        c_str = img.get("content", "") if isinstance(img, dict) else getattr(img, "content", "")
                        if c_str.startswith("data:"):
                            user_parts.append({"type": "image_url", "image_url": {"url": c_str}})
                    final_prompt = await ask_agent_with_fallback(
                        db, settings, real_prompter,
                        [{"role": "system", "content": sys_msg}, {"role": "user", "content": user_parts}],
                        is_worker=False, enable_web=False, target_domain="Vision & Texte"
                    )
                else:
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
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log_activity(f"[Studio] Optimisation ignorée ({str(e)[:50]}), utilisation du prompt original.")

        strict_free = get_model_is_free(db, model_id)
        tier_label = "GRATUIT" if strict_free else "PAYANT"
        target_domain = "Génération Vidéo" if media_type == "video" else "Génération Image"

        tried_models = set()
        current_model = model_id
        last_error = ""

        async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
            for attempt in range(5):
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
                    media_url = await _try_single_media_model(client, settings, provider, current_model, final_prompt, media_type, input_images=input_images)
                    log_activity(f"✅ [Studio {media_type.upper()}] Généré avec succès via {current_model} ({tier_label}).")
                    return {
                        "media_url": media_url,
                        "media_type": media_type,
                        "optimized_prompt": final_prompt,
                        "model_used": current_model
                    }
                except asyncio.CancelledError:
                    raise
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
    except asyncio.CancelledError:
        log_activity("🛑 Génération média interrompue par l'utilisateur.")
        raise HTTPException(status_code=499, detail="Génération média interrompue par l'utilisateur.")
    except HTTPException:
        raise
    except Exception as e:
        tb_str = traceback.format_exc()
        system_logger.error(f"Erreur Studio Média:\n{tb_str}")
        raise HTTPException(status_code=500, detail=f"Erreur interne Studio Média : {str(e)}")

async def run_orchestrator(db: Session, history: list, settings: SystemSettings, config: dict, extracted_files: list = None, project_id: int = None) -> str:
    if not config: config = {}
    mode = config.get("mode", "multi")
    theme = config.get("theme", "general")
    enable_web = config.get("enable_web", True)
    custom_instructions = (config.get("custom_instructions") or "").strip()

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

    # Injection des consignes spécifiques persistantes en début de prompt (si définies sur la discussion)
    if custom_instructions:
        log_activity(f"[Consignes Discussion] Application des consignes persistantes ({len(custom_instructions)} car.).")
        user_prompt = f"[CONSIGNES SPÉCIFIQUES IMPÉRATIVES DE CETTE DISCUSSION À APPLIQUER SYSTÉMATIQUEMENT] :\n{custom_instructions}\n\n[DEMANDE DE L'UTILISATEUR] :\n{user_prompt}"

    all_involved_models = [p_mod] + workers + ([c_mod] if mode == "multi" else [])
    chunk_size = compute_dynamic_chunk_size(db, all_involved_models)

    is_ocr_ce2 = (theme == "ocr_ce2")
    final_response = ""

    try:
        set_project_live_status(project_id, True, f"Initialisation ({mode.upper()}) avec {p_mod}...", "")
        log_activity(f"Orchestration [{mode.upper()} | Thème: {theme} | Web: {'ON' if enable_web else 'OFF'}]. Prompteur: {p_mod}")

        files_context = ""
        if extracted_files:
            log_activity(f"Traitement Map-Reduce de {len(extracted_files)} fichier(s) joint(s) (Chunk max 90%: {chunk_size} car.).")
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
                    set_project_live_status(project_id, True, f"Analyse Vision / OCR de l'image {fname}...")
                    log_activity(f"Analyse Vision / OCR de l'image {fname}...")
                    user_msg_content = [
                        {"type": "text", "text": f"Demande : '{original_user_text}'.\nFichier image : '{fname}'. Transcris intégralement et littéralement le contenu visible (sans corriger aucune faute si c'est une copie d'élève)."},
                        {"type": "image_url", "image_url": {"url": content}}
                    ]
                    try:
                        analysis = await ask_agent_with_fallback(
                            db, settings, p_mod,
                            [{"role": "system", "content": file_sys}, {"role": "user", "content": user_msg_content}],
                            is_worker=False, enable_web=False, target_domain="Vision & Texte", project_id=project_id
                        )
                        log_activity(f"OCR Vision de {fname} réussi.")
                        return f"\n\n--- Transcription exacte du fichier {fname} ---\n{analysis}"
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        log_activity(f"Erreur OCR Vision sur {fname}: {str(e)}")
                        return f"\n\n--- Erreur de lecture image sur {fname} ---\n{str(e)}"

                if len(content) > chunk_size:
                    processed_file = await smart_chunk_text_pipeline(
                        db=db,
                        settings=settings,
                        full_text=content,
                        user_goal=original_user_text,
                        max_chunk_chars=chunk_size,
                        fallback_prompter_id=p_mod,
                        is_ocr_ce2=is_ocr_ce2,
                        project_id=project_id,
                        label=f"Fichier {fname}"
                    )
                    return f"\n\n--- Extraction chunkée (marge 10%) du fichier {fname} ---\n{processed_file}"
                else:
                    if is_ocr_ce2:
                        file_prompt = f"Demande : '{original_user_text}'.\nFichier : '{fname}'. Restitue intégralement et À L'IDENTIQUE (sans corriger les erreurs des élèves) le contenu ci-dessous :\n```\n{content}\n```"
                    else:
                        file_prompt = f"Demande de l'utilisateur : '{original_user_text}'.\n\nAnalysez le fichier ci-dessous. Extrayez, résumez et conservez méticuleusement tout le code, les macros VBA, les requêtes SQL, ou les données métier pertinentes.\n\nFichier : {fname}\nContenu :\n```\n{content}\n```"
                    try:
                        analysis = await ask_agent_with_fallback(
                            db, settings, p_mod,
                            [{"role": "system", "content": file_sys}, {"role": "user", "content": file_prompt}],
                            is_worker=False, enable_web=False, project_id=project_id
                        )
                        log_activity(f"Analyse intégrale de {fname} réussie.")
                        return f"\n\n--- Extraction du fichier {fname} ---\n{analysis}"
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        log_activity(f"Erreur d'analyse sur {fname}: {str(e)}")
                        return f"\n\n--- Erreur sur {fname} ---\n{str(e)}"

            file_analyses = []
            for f in extracted_files:
                analysis = await process_single_file(f)
                file_analyses.append(analysis or "")
                await asyncio.sleep(0.5)
            
            files_context = "".join(file_analyses)
            user_prompt = f"{user_prompt}\n\nVoici les données extraites des fichiers joints :\n{files_context}"

        # Si le prompt complet dépasse 90% du contexte maximal autorisé -> Chunking intelligent (Hermes -> Ollama GTX 1650 -> Cloud)
        if len(user_prompt) > chunk_size:
            user_prompt = await smart_chunk_text_pipeline(
                db=db,
                settings=settings,
                full_text=user_prompt,
                user_goal=original_user_text,
                max_chunk_chars=chunk_size,
                fallback_prompter_id=p_mod,
                is_ocr_ce2=is_ocr_ce2,
                project_id=project_id,
                label="Prompt global"
            )

        set_project_live_status(project_id, True, f"Optimisation du prompt via {p_mod}...")
        if is_ocr_ce2:
            log_activity("Structuration de la tâche de correction CE2 (Français strict conservé)...")
            prompt_system = (
                "Tu es un ingénieur pédagogique assistant Céline, professeure des écoles en CE2. "
                "Ne traduis RIEN en anglais. Prépare la consigne complète en français pour le correcteur IA en conservant "
                "STRICTEMENT à l'identique les transcriptions brutes des copies d'élèves (avec toutes leurs fautes d'origine) ainsi que le corrigé de référence."
            )
            if custom_instructions:
                prompt_system = f"[CONSIGNES SPÉCIFIQUES DE LA DISCUSSION] :\n{custom_instructions}\n\n{prompt_system}"
            optimized = await ask_agent_with_fallback(
                db, settings, p_mod,
                [{"role": "system", "content": prompt_system}, {"role": "user", "content": user_prompt}],
                is_worker=False, enable_web=False, project_id=project_id
            )
        else:
            log_activity(f"Optimisation de la requête via le Prompteur ({p_mod})...")
            prompt_system = (
                "You are an expert prompt engineer. Translate and optimize the user request and any file context into clear, precise English tailored for AI execution. "
                "Keep all code blocks, persistent custom instructions, and exact data intact."
            )
            if custom_instructions:
                prompt_system += f"\n\nMANDATORY PERSISTENT DISCUSSION INSTRUCTIONS (Always enforce at the top of the prompt):\n{custom_instructions}"
            optimized = await ask_agent_with_fallback(
                db, settings, p_mod,
                [{"role": "system", "content": prompt_system}, {"role": "user", "content": user_prompt}],
                is_worker=False, enable_web=False, project_id=project_id
            )

        if custom_instructions:
            optimized = f"[CONSIGNES SPÉCIFIQUES IMPÉRATIVES DE CETTE DISCUSSION] :\n{custom_instructions}\n\n{optimized}"

        if len(optimized) > chunk_size:
            optimized = await smart_chunk_text_pipeline(
                db=db,
                settings=settings,
                full_text=optimized,
                user_goal=original_user_text,
                max_chunk_chars=chunk_size,
                fallback_prompter_id=p_mod,
                is_ocr_ce2=is_ocr_ce2,
                project_id=project_id,
                label="Prompt optimisé"
            )

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

        if custom_instructions:
            worker_sys_prompt = (
                f"[CONSIGNES SPÉCIFIQUES IMPÉRATIVES DE CETTE DISCUSSION] :\n{custom_instructions}\n\n"
                + (worker_sys_prompt or "Respecte scrupuleusement les consignes spécifiques de cette discussion.")
            )

        safe_history = []
        running_chars = len(optimized) + (len(worker_sys_prompt) if worker_sys_prompt else 0)
        for h_msg in reversed(formatted_history):
            c_len = len(h_msg.get("content") or "")
            if running_chars + c_len <= chunk_size:
                safe_history.insert(0, h_msg)
                running_chars += c_len
            else:
                break

        async def execute_single_worker(w_mod: str) -> str:
            m_db = db.query(AIModel).filter(AIModel.model_id == w_mod).first()
            dom = m_db.domain if m_db else determine_domain(w_mod)
            # Vérification individuelle du contexte autorisé du travailleur (avec 10% de marge)
            w_max_chars = compute_dynamic_chunk_size(db, [w_mod])
            w_prompt = optimized
            if len(w_prompt) > w_max_chars:
                w_prompt = await smart_chunk_text_pipeline(
                    db=db,
                    settings=settings,
                    full_text=w_prompt,
                    user_goal=original_user_text,
                    max_chunk_chars=w_max_chars,
                    fallback_prompter_id=p_mod,
                    is_ocr_ce2=is_ocr_ce2,
                    project_id=project_id,
                    label=f"Contexte {w_mod}"
                )

            if dom in ["Génération Image", "Génération Vidéo"]:
                m_type = "video" if dom == "Génération Vidéo" else "image"
                img_files = [f for f in (extracted_files or []) if f.get("is_image")]
                media_res = await generate_media(db, settings, w_prompt, m_type, w_mod, p_mod, optimize_prompt=False, input_images=img_files)
                return f"[MEDIA_{m_type.upper()}:{media_res['model_used']}]\n{media_res['media_url']}\nPrompt utilisé : {media_res['optimized_prompt']}"
            msgs = safe_history.copy()
            if worker_sys_prompt:
                msgs.insert(0, {"role": "system", "content": worker_sys_prompt})
            msgs.append({"role": "user", "content": w_prompt})
            return await ask_agent_with_fallback(
                db, settings, w_mod, msgs,
                is_worker=True, enable_web=enable_web,
                target_domain=dom,
                project_id=project_id
            )

        set_project_live_status(project_id, True, f"Exécution sur {len(workers)} travailleur(s) IA...")
        log_activity(f"Exécution sur {len(workers)} travailleur(s) (avec bascule anti-quota équivalente active)...")
        if len(workers) == 1:
            worker_response = await execute_single_worker(workers[0])
            responses = [worker_response]
            log_activity(f"Travailleur ({workers[0]}) a terminé.")
        else:
            w_tasks = [execute_single_worker(w) for w in workers]
            responses = await asyncio.gather(*w_tasks, return_exceptions=True)
            for r in responses:
                if isinstance(r, asyncio.CancelledError):
                    raise r
            log_activity("Tous les travailleurs ont terminé leur analyse.")

        if mode == "mono" or any(str(r).startswith("[MEDIA_") for r in responses):
            log_activity("Restitution directe (Mono-IA / Média généré).")
            final_response = "\n\n".join([str(r) for r in responses])
        else:
            set_project_live_status(project_id, True, f"Synthèse finale par le Concaténeur ({c_mod})...")
            log_activity(f"Synthèse finale via Concaténeur ({c_mod})...")
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
            if custom_instructions:
                concat_system = f"[CONSIGNES SPÉCIFIQUES IMPÉRATIVES DE LA DISCUSSION] :\n{custom_instructions}\n\n{concat_system}"

            synth = f"User Request: {original_user_text}\n"
            if custom_instructions:
                synth += f"Persistent Instructions: {custom_instructions}\n"
            synth += "\n" + "\n".join([f"--- EXPERT {i+1} ---\n{str(r)}" for i, r in enumerate(responses)])

            c_max_chars = compute_dynamic_chunk_size(db, [c_mod])
            if len(synth) > c_max_chars:
                synth = await smart_chunk_text_pipeline(
                    db=db,
                    settings=settings,
                    full_text=synth,
                    user_goal=original_user_text,
                    max_chunk_chars=c_max_chars,
                    fallback_prompter_id=p_mod,
                    is_ocr_ce2=is_ocr_ce2,
                    project_id=project_id,
                    label="Synthèse Concaténeur"
                )
            final_response = await ask_agent_with_fallback(
                db, settings, c_mod,
                [{"role": "system", "content": concat_system}, {"role": "user", "content": synth}],
                is_worker=False, enable_web=False,
                target_domain="Code & Logique" if theme == "code" else "Texte Polyvalent",
                project_id=project_id
            )

        log_activity("Orchestration terminée avec succès.")

    except asyncio.CancelledError:
        log_activity("🛑 Orchestration interrompue à la demande de l'utilisateur.")
        raise
    except Exception as e:
        tb_str = traceback.format_exc()
        system_logger.error(f"Traceback complet:\n{tb_str}")
        final_response = f"L'IA a rencontré une erreur critique: {str(e)}"
        log_activity(f"ERREUR CRITIQUE: {str(e)}")
    finally:
        clear_project_live_status(project_id)
    
    await sync_finances(db, settings)
    return final_response