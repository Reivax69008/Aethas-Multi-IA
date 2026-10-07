from openai import OpenAI
from fastapi import HTTPException
from .models import SystemSettings

def get_ai_response(messages: list, settings: SystemSettings) -> str:
    """
    Route la conversation vers le premier fournisseur IA disponible configuré par l'admin.
    Prend l'historique des messages et retourne le texte généré.
    """
    if not settings:
        raise HTTPException(status_code=500, detail="Configuration système introuvable.")

    # Formatage de l'historique pour l'API (OpenAI compatible)
    formatted_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

    # 1. Test OpenRouter (Idéal car donne accès à tout)
    if settings.openrouter_api_key:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key,
        )
        model = "google/gemini-pro" # Fallback par défaut via OpenRouter
    
    # 2. Test DeepSeek
    elif settings.deepseek_api_key:
        client = OpenAI(
            base_url="https://api.deepseek.com/v1",
            api_key=settings.deepseek_api_key,
        )
        model = "deepseek-chat"
        
    # 3. Test Groq
    elif settings.groq_api_key:
        client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.groq_api_key,
        )
        model = "llama3-8b-8192"
        
    else:
        raise HTTPException(status_code=400, detail="Aucun moteur IA (OpenRouter, DeepSeek, Groq) n'est configuré avec une clé API.")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=formatted_messages,
            # Identifiant unique de l'application pour OpenRouter
            extra_headers={"HTTP-Referer": "https://aethas38.duckdns.org", "X-Title": "AETHAS38 Multi-IA"} if settings.openrouter_api_key else {}
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Erreur API IA : {str(e)}")
        raise HTTPException(status_code=502, detail="Erreur de communication avec le fournisseur IA.")