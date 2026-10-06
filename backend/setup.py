import os
import platform
import re
import pyotp
import qrcode
import psutil
from dotenv import load_dotenv

def clear_screen():
    os.system('cls' if platform.system() == 'Windows' else 'clear')

def check_hardware():
    print("=" * 60)
    print(" 🖥️  ANALYSE DU MATÉRIEL ET LOGICIEL DU SERVEUR")
    print("=" * 60)
    
    cpu_count = psutil.cpu_count(logical=True)
    ram_gb = round(psutil.virtual_memory().total / (1024**3), 2)
    os_info = f"{platform.system()} {platform.release()}"
    
    print(f"• Système d'exploitation : {os_info}")
    print(f"• Cœurs CPU logiques : {cpu_count}")
    print(f"• Mémoire RAM totale : {ram_gb} Go")
    
    # Évaluation pour phuzzy/minecraft
    print("\n[Vérification du modèle lourd : phuzzy/minecraft]")
    if ram_gb < 16:
        print("⚠️  AVERTISSEMENT CRITIQUE : Votre serveur dispose de moins de 16 Go de RAM/VRAM.")
        print("   Le modèle 'phuzzy/minecraft' requiert des ressources importantes.")
        print("   Risque de ralentissements sévères ou de plantage par manque de mémoire (OOM).")
    else:
        print("✅ La configuration matérielle semble suffisante pour exécuter les modèles locaux (Qwen & Phuzzy).")
    print("-" * 60 + "\n")

def validate_password(password):
    if len(password) < 12:
        return "Le mot de passe doit contenir au moins 12 caractères."
    if not re.search(r"[A-Z]", password):
        return "Le mot de passe doit contenir au moins une majuscule."
    if not re.search(r"[a-z]", password):
        return "Le mot de passe doit contenir au moins une minuscule."
    if not re.search(r"[0-9]", password):
        return "Le mot de passe doit contenir au moins un chiffre."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return "Le mot de passe doit contenir au moins un caractère spécial."
    return None

def configure_admin():
    print("=" * 60)
    print(" 🔑 CRÉATION DU COMPTE ADMINISTRATEUR & SÉCURITÉ 2FA")
    print("=" * 60)
    
    email = input("Entrez l'e-mail administrateur : ").strip()
    
    while True:
        password = input("Définissez le mot de passe (min. 12 caractères, majuscules, minuscules, chiffres, symboles) : ").strip()
        err = validate_password(password)
        if err:
            print(f"❌ Erreur : {err}")
        else:
            print("✅ Mot de passe valide.")
            break
            
    # Génération 2FA (TOTP)
    totp_secret = pyotp.random_base32()
    totp_uri = pyotp.totp.TOTP(totp_secret).provisioning_uri(name=email, issuer_name="AETHAS38-Hub")
    
    print("\n--- DOUBLE AUTHENTIFICATION (2FA) ---")
    print("Scannez le QR code ci-dessous avec votre application (Google Authenticator, KeePassXC, etc.) :")
    
    # Génération d'un QR code dans le terminal en texte ASCII
    qr = qrcode.QRCode()
    qr.add_data(totp_uri)
    qr.make(fit=True)
    qr.print_ascii(invert=True)
    
    print(nis := f"Clé secrète manuelle (si besoin) : {totp_secret}")
    print("-" * 60 + "\n")
    return email, password, totp_secret

def configure_api_keys():
    print("=" * 60)
    print(" 🌐 CONFIGURATION DES CLÉS API (PAR SPÉCIALITÉ)")
    print("=" * 60)
    print("Laissez vide si vous ne possédez pas la clé pour l'instant.\n")
    
    keys = {}
    
    print("1. [CODAGE & RAISONNEMENT] - OpenRouter & Management Key")
    print("   -> Où la trouver : https://openrouter.ai/settings/keys")
    keys["OPENROUTER_API_KEY"] = input("   Entrez OPENROUTER_API_KEY : ").strip()
    keys["OPENROUTER_MANAGEMENT_KEY"] = input("   Entrez OPENROUTER_MANAGEMENT_KEY (pour le suivi du budget) : ").strip()
    
    print("\n2. [CODAGE ULTRA-RAPIDE] - Groq")
    print("   -> Où la trouver : https://console.groq.com/keys")
    keys["GROQ_API_KEY"] = input("   Entrez GROQ_API_KEY : ").strip()
    
    print("\n3. [MULTIMODAL & CODE] - Google Gemini")
    print("   -> Où la trouver : https://aistudio.google.com/app/apikey")
    keys["GEMINI_API_KEY"] = input("   Entrez GEMINI_API_KEY : ").strip()
    
    print("\n4. [CODAGE AVANCÉ] - DeepSeek")
    print("   -> Où la trouver : https://platform.deepseek.com/api_keys")
    keys["DEEPSEEK_API_KEY"] = input("   Entrez DEEPSEEK_API_KEY : ").strip()
    
    print("\n5. [TEXTE & GÉNÉRAL] - Mistral AI")
    print("   -> Où la trouver : https://console.mistral.ai/api-keys/")
    keys["MISTRAL_API_KEY"] = input("   Entrez MISTRAL_API_KEY : ").strip()
    
    print("\n6. [INFRASTRUCTURE & IA EDGE] - Cloudflare")
    print("   -> Où la trouver : Tableau de bord Cloudflare (Workers & Pages > AI)")
    keys["CLOUDFLARE_ACCOUNT_ID"] = input("   Entrez CLOUDFLARE_ACCOUNT_ID : ").strip()
    keys["CLOUDFLARE_API_TOKEN"] = input("   Entrez CLOUDFLARE_API_TOKEN : ").strip()

    print("\n7. [MODÈLES LIBRES] - HuggingFace")
    print("   -> Où la trouver : https://huggingface.co/settings/tokens")
    keys["HUGGINGFACE_API_KEY"] = input("   Entrez HUGGINGFACE_API_KEY : ").strip()
    
    print("-" * 60 + "\n")
    return keys

def save_env(keys, admin_data):
    env_content = f"""# ==========================================
# AETHAS38 - CONFIGURATION AUTOMATISÉE
# ==========================================

# Administrateur principal
ADMIN_EMAIL={admin_data[0]}
ADMIN_PASSWORD_HASH={admin_data[1]}
ADMIN_2FA_SECRET={admin_data[2]}

# Clés API Distantes
"""
    for k, v in keys.items():
        env_content += f"{k}={v}\n"
        
    with open(".env", "w", encoding="utf-8") as f:
        f.write(env_content)
    print("✅ Fichier .env généré avec succès !")

if __name__ == "__main__":
    clear_screen()
    check_hardware()
    admin_data = configure_admin()
    keys = configure_api_keys()
    save_env(keys, admin_data)
    print("\n🎉 Installation et configuration initiale terminées avec succès !")
    print("Vous pouvez maintenant lancer le service Dockge / Docker.")