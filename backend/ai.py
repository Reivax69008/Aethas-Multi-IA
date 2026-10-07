from openai import OpenAI
from fastapi import HTTPException
from .models import SystemSettings

def get_ai_response(messages: list, settings: SystemSettings) -> str:
    """Route la conversation vers le premier fournisseur IA disponible, priorité à Gemini Direct."""
    if not settings:
        raise HTTPException(status_code=500, detail="Configuration système introuvable.")

    formatted_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

    try:
        # 1. Priorité absolue : Test Gemini direct
        if settings.gemini_api_key:
            client = OpenAI(
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/", 
                api_key=settings.gemini_api_key
            )
            # Correction : Utilisation exacte du modèle 3.5 Flash-Lite
            model = "gemini-3.5-flash-lite" 
            response = client.chat.completions.create(model=model, messages=formatted_messages)

        # 2. Test OpenRouter (Fallback)
        elif settings.openrouter_api_key:
            client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=settings.openrouter_api_key)
            model = "google/gemini-3.5-flash-lite"
            response = client.chat.completions.create(
                model=model,
                messages=formatted_messages,
                extra_headers={"HTTP-Referer": "https://aethas38.duckdns.org", "X-Title": "AETHAS38"}
            )

        # 3. Test DeepSeek
        elif settings.deepseek_api_key:
            client = OpenAI(base_url="https://api.deepseek.com/v1", api_key=settings.deepseek_api_key)
            model = "deepseek-chat"
            response = client.chat.completions.create(model=model, messages=formatted_messages)
            
        # 4. Test Groq
        elif settings.groq_api_key:
            client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=settings.groq_api_key)
            model = "llama3-8b-8192"
            response = client.chat.completions.create(model=model, messages=formatted_messages)
            
        else:
            raise HTTPException(status_code=400, detail="Aucune clé API IA n'est configurée.")

        return response.choices[0].message.content

    except Exception as e:
        print(f"Erreur API IA : {str(e)}")
        raise HTTPException(status_code=502, detail=f"Détail du fournisseur : {str(e)}")