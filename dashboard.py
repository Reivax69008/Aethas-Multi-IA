import os
import requests
from dotenv import load_dotenv

# Couleurs pour le terminal (Inspiration AETHAS38 / SERFIM TIC)
CYAN = '\033[96m'
MAGENTA = '\033[95m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
RESET = '\033[0m'

def print_header():
    print(f"\n{CYAN}=================================================={RESET}")
    print(f"{MAGENTA}           A E T H A S 3 8   T E C H   C O R E    {RESET}")
    print(f"{CYAN}=================================================={RESET}")
    print(f"       Interface de Développement & Budget LLM    \n")

def check_openrouter_budget():
    """Interroge l'API OpenRouter avec la Management Key pour lire le solde."""
    load_dotenv()
    
    # On récupère STRICTEMENT la Management Key
    mgmt_key = os.getenv("OPENROUTER_MANAGEMENT_KEY")
    
    if not mgmt_key:
        print(f"{RED}[ERREUR] OPENROUTER_MANAGEMENT_KEY introuvable dans le fichier .env.{RESET}")
        print("Veuillez créer une Management API Key sur OpenRouter et l'ajouter au .env.")
        return

    print(f"{YELLOW}Interrogation des serveurs OpenRouter...{RESET}")
    
    url = "https://openrouter.ai/api/v1/credits"
    headers = {
        "Authorization": f"Bearer {mgmt_key}"
    }
    
    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json().get("data", {})
            total_credits = data.get("total_credits", 0)
            total_usage = data.get("total_usage", 0)
            remaining = total_credits - total_usage
            
            print(f"\n{GREEN}--- STATUT BUDGET OPENROUTER ---{RESET}")
            print(f"Crédits achetés : {total_credits:.4f} $")
            print(f"Crédits consommés : {total_usage:.4f} $")
            
            # Alerte visuelle si le budget est bas
            if remaining < 1.0:
                print(f"Solde restant   : {RED}{remaining:.4f} ${RESET} ⚠️ (Recharge conseillée)")
            else:
                print(f"Solde restant   : {CYAN}{remaining:.4f} ${RESET}")
            print(f"{GREEN}--------------------------------{RESET}\n")
            
        elif response.status_code == 403:
            print(f"{RED}[ERREUR 403] Accès refusé.{RESET} Vérifiez que vous utilisez bien une Management Key et non une clé API standard.")
        else:
            print(f"{RED}[ERREUR {response.status_code}]{RESET} {response.text}")
            
    except Exception as e:
        print(f"{RED}[ERREUR RESEAU] Impossible de joindre OpenRouter : {e}{RESET}")

if __name__ == "__main__":
    print_header()
    check_openrouter_budget()