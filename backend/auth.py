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

import jwt
from datetime import datetime, timedelta, timezone
import os

# Dans l'idéal, cette clé secrète sera à placer dans votre fichier .env plus tard
SECRET_KEY = os.getenv("SECRET_KEY", r"`*\$Tu*CCc5hglT$mX'HykxERDljBz")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

def create_access_token(data: dict):
    """Crée un jeton JWT valable 60 minutes."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str):
    """Vérifie la validité du jeton JWT."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None  # Le jeton a expiré (60 min écoulées)
    except jwt.InvalidTokenError:
        return None  # Le jeton est invalide