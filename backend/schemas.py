from pydantic import BaseModel, EmailStr

class AdminCreate(BaseModel):
    email: EmailStr
    username: str
    password: str

# NOUVEAU : Schéma pour la connexion
class LoginRequest(BaseModel):
    username: str
    password: str
    totp_code: str