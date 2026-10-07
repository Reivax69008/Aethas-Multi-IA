# 📚 WIKI AETHAS38 - Configuration des Fournisseurs IA

Ce document détaille la procédure pour obtenir les clés API avec les droits complets (Inférence + Accès financier) nécessaires au fonctionnement de l'Orchestrateur AETHAS38.

## 1. OpenRouter (Prioritaire)
OpenRouter agit comme un agrégateur. C'est le fournisseur recommandé car il permet d'accéder à presque tous les modèles (y compris Gemini, Claude, Llama) avec un seul portefeuille prépayé.
*   **Obtenir la clé API :** Allez sur [OpenRouter Keys](https://openrouter.ai/keys). Créez une clé standard sans limite de crédit pour permettre à AETHAS38 de requêter les modèles.
*   **Accès Financier (Management Key) :** Pour que AETHAS38 lise votre solde en temps réel, vous devez générer une clé spécifique d'administration (Management Key) sur la même page, ou accorder les droits `read_balance` à votre clé API principale selon les dernières mises à jour de leur interface.

## 2. Google Gemini Studio
*   **Obtenir la clé API :** Rendez-vous sur [Google AI Studio](https://aistudio.google.com/app/apikey).
*   **Levée des quotas :** Par défaut, la clé est gratuite mais soumise à des limites strictes (ex: 15 requêtes/minute) qui bloqueront le travail en parallèle d'AETHAS38. Pour un accès total, liez votre projet AI Studio à un compte de facturation Google Cloud Platform (GCP).

## 3. DeepSeek & Groq
*   **DeepSeek :** [DeepSeek Platform](https://platform.deepseek.com/api_keys). Facturation à l'usage (Token). Il faut provisionner le compte par carte bancaire (Top-up).
*   **Groq :** [Groq Console](https://console.groq.com/keys). Actuellement en phase gratuite avec quotas de requêtes très élevés, idéal pour les travailleurs de base de l'orchestrateur.

## 4. Cloudflare Workers AI & HuggingFace
*   **Cloudflare :** [Cloudflare Dash](https://dash.cloudflare.com/profile/api-tokens). Créez un token personnalisé avec la permission `Workers AI : Read/Write`. L'ID de compte (Account ID) est visible dans la barre latérale droite de l'aperçu de la zone.
*   **HuggingFace :** [HF Settings](https://huggingface.co/settings/tokens). Générez un token *Fine-Grained* et cochez les permissions liées à l'`Inference API` pour permettre l'exécution des modèles serverless.