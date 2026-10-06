import bcrypt
import pyotp

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifie si le mot de passe en clair correspond au hash."""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password: str) -> str:
    """Génère le hash sécurisé d'un mot de passe."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

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