# auth.py
import re
import pyotp
import hashlib
import hmac
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def validate_password_strength(password):
    if len(password) < 12: return "Le mot de passe doit contenir au moins 12 caractères."
    if not re.search(r"[A-Z]", password): return "Le mot de passe doit contenir au moins une majuscule."
    if not re.search(r"[a-z]", password): return "Le mot de passe doit contenir au moins une minuscule."
    if not re.search(r"[0-9]", password): return "Le mot de passe doit contenir au moins un chiffre."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password): return "Le mot de passe doit contenir au moins un caractère spécial."
    return None

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(stored_hash, provided_password):
    return hmac.compare_digest(stored_hash, hash_password(provided_password))

def generate_totp_secret():
    return pyotp.random_base32()

def verify_totp(secret, code):
    totp = pyotp.TOTP(secret)
    return totp.verify(code)

def send_invite_email(to_email, setup_link):
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    
    if not all([smtp_server, smtp_user, smtp_pass]):
        return False

    msg = MIMEMultipart()
    msg['From'] = f"AETHAS38 <{smtp_user}>"
    msg['To'] = to_email
    msg['Subject'] = "Invitation au Hub AETHAS38"
    body = f"Vous avez été invité(e) à rejoindre le hub IA AETHAS38.\nLien de configuration 2FA : {setup_link}"
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        server.quit()
        return True
    except Exception:
        return False