import asyncio
import httpx
from openai import AsyncOpenAI
from fastapi import HTTPException
from sqlalchemy.orm import Session
from .models import SystemSettings, AIModel
from .logger import system_logger
from datetime import datetime, timezone

# --- PARTIE 1 : EXTRACTION DES MODÈLES ---
async def sync_providers_models(db: Session, settings: SystemSettings):
    """Extrait et met à jour les modèles depuis les fournisseurs configurés."""
    added_or_updated = 0
    
    # httpx.AsyncClient permet des requêtes non-bloquantes (ultra rapide)
    async with httpx.AsyncClient() as client:
        # 1. OpenRouter (Exemple principal pour l'extraction massive)
        if settings.openrouter_api_key:
            try:
                response = await client.get("https://openrouter.ai/api/v1/models")
                if response.status_code == 200:
                    for item in response.json().get("data", []):
                        model_id = item["id"]
                        existing = db.query(AIModel).filter(AIModel.model_id == model_id).first()
                        
                        pricing = item.get("pricing", {})
                        # Conversion en coût pour 1 Million de tokens
                        p_prompt = float(pricing.get("prompt", 0)) * 1000000 if pricing.get("prompt") else 0.0
                        p_comp = float(pricing.get("completion", 0)) * 1000000 if pricing.get("completion") else 0.0

                        if existing:
                            existing.pricing_prompt = p_prompt
                            existing.pricing_completion = p_comp
                            existing.last_updated = datetime.now(timezone.utc)
                        else:
                            new_model = AIModel(
                                provider="openrouter",
                                model_id=model_id,
                                name=item["name"],
                                context_length=item.get("context_length", 0),
                                pricing_prompt=p_prompt,
                                pricing_completion=p_comp
                            )
                            db.add(new_model)
                        added_or_updated += 1
            except Exception as e:
                system_logger.error(f"Erreur Sync OpenRouter: {e}")
    
    db.commit()
    return {"status": "success", "models_processed": added_or_updated}

# --- PARTIE 2 : MOTEUR MULTI-AGENTS ---
def get_client_for_model(model_id: str, settings: SystemSettings):
    """Retourne le client AsyncOpenAI approprié selon le modèle sélectionné."""
    if "gemini" in model_id.lower() and settings.gemini_api_key:
        return AsyncOpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=settings.gemini_api_key)
    elif settings.openrouter_api_key:
        return AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=settings.openrouter_api_key)
    raise ValueError(f"Aucun fournisseur configuré pour {model_id}")

async def ask_agent(client, model_id, messages, is_openrouter=False):
    """Appel asynchrone à un modèle IA."""
    kwargs = {"model": model_id, "messages": messages}
    if is_openrouter:
        kwargs["extra_headers"] = {"HTTP-Referer": "https://aethas38.duckdns.org", "X-Title": "AETHAS38 Orchestrator"}
    
    response = await client.chat.completions.create(**kwargs)
    return response.choices[0].message.content

async def run_orchestrator(history: list, settings: SystemSettings, config: dict) -> str:
    """
    Gère la logique : 1 Prompteur -> N Travailleurs -> 1 Concaténeur.
    Le dictionnaire 'config' proviendra de l'interface graphique.
    """
    workers = config.get("workers", [])
    if not workers:
        workers = ["gemini-3.5-flash-lite"] # Fallback de sécurité
    
    user_prompt = history[-1].content
    formatted_history = [{"role": msg.role, "content": msg.content} for msg in history[:-1]]

    # SCÉNARIO 1 : Un seul travailleur (Pas besoin de prompteur/concaténeur)
    if len(workers) == 1:
        worker_model = workers[0]
        client = get_client_for_model(worker_model, settings)
        messages = formatted_history + [{"role": "user", "content": user_prompt}]
        return await ask_agent(client, worker_model, messages, "openrouter" in worker_model.lower())

    # SCÉNARIO 2 : Multi-Travailleurs (Le pipeline complet)
    try:
        # Étape 1 : Le Prompteur améliore la requête
        prompter_model = config.get("prompter", "gemini-3.5-flash-lite")
        p_client = get_client_for_model(prompter_model, settings)
        p_messages = [{"role": "system", "content": "Tu es un expert en Prompt Engineering. Optimise la requête de l'utilisateur pour qu'elle soit claire, directive et parfaite pour des IAs de génération. Retourne UNIQUEMENT le prompt optimisé."}]
        p_messages.append({"role": "user", "content": user_prompt})
        
        system_logger.info("Démarrage du Prompteur...")
        optimized_prompt = await ask_agent(p_client, prompter_model, p_messages)

        # Étape 2 : Les Travailleurs en parallèle (Magie de l'Asynchrone)
        system_logger.info(f"Lancement de {len(workers)} travailleurs en parallèle...")
        w_tasks = []
        for w_model in workers:
            w_client = get_client_for_model(w_model, settings)
            w_messages = formatted_history + [{"role": "user", "content": optimized_prompt}]
            # On stocke les tâches sans les attendre immédiatement
            w_tasks.append(ask_agent(w_client, w_model, w_messages, "openrouter" in w_model.lower()))
        
        # 'gather' exécute toutes les requêtes en même temps !
        workers_responses = await asyncio.gather(*w_tasks, return_exceptions=True)

        # Étape 3 : Le Concaténeur synthétise
        concat_model = config.get("concatenator", "gemini-3.5-flash-lite")
        c_client = get_client_for_model(concat_model, settings)
        
        synthesis_prompt = f"Voici la requête initiale : {user_prompt}\n\nVoici les réponses de {len(workers)} experts IA différents :\n"
        for i, resp in enumerate(workers_responses):
            synthesis_prompt += f"--- EXPERT {i+1} ---\n{resp if not isinstance(resp, Exception) else 'Erreur de génération'}\n\n"
        synthesis_prompt += "Fais une synthèse finale parfaite, complète et structurée de ces réponses, en gardant le meilleur de chacune."

        system_logger.info("Démarrage du Concaténeur...")
        c_messages = [{"role": "user", "content": synthesis_prompt}]
        return await ask_agent(c_client, concat_model, c_messages)

    except Exception as e:
        system_logger.error(f"Erreur Pipeline Multi-Agents: {e}")
        raise HTTPException(status_code=502, detail=f"Échec de l'orchestration : {str(e)}")