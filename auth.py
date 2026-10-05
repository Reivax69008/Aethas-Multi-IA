import re
import pyotp
import hashlib
import hmac

def validate_password_strength(password):
    """Vérifie que le mot de passe respecte les critères de sécurité stricts."""
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

def hash_password(password):
    """Hachage sécurisé du mot de passe."""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(stored_hash, provided_password):
    """Vérifie un mot de passe par rapport à son haché."""
    return hmac.compare_digest(stored_hash, hash_password(provided_password))

def generate_totp_secret():
    """Génère une clé secrète pour le 2FA."""
    return pyotp.random_base32()

def verify_totp(secret, code):
    """Vérifie le code TOTP fourni par l'application d'authentification."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code)