from passlib.context import CryptContext
import pyotp

# Configuration du hachage (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifie si le mot de passe en clair correspond au hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Génère le hash d'un mot de passe."""
    return pwd_context.hash(password)

def generate_totp_secret() -> str:
    """Génère un secret aléatoire pour l'application 2FA (Authenticator, Keepassium)."""
    return pyotp.random_base32()

def get_totp_uri(secret: str, username: str) -> str:
    """Génère l'URI pour créer le QR Code."""
    return pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name="AETHAS38")

def verify_totp(secret: str, code: str) -> bool:
    """Vérifie le code à 6 chiffres soumis par l'utilisateur."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code)