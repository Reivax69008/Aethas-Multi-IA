from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class AdminCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    # Serveur Mail (Obligatoire)
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    # Clés API (Optionnelles)
    openrouter_api_key: Optional[str] = None
    openrouter_management_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    mistral_api_key: Optional[str] = None
    cloudflare_account_id: Optional[str] = None
    cloudflare_api_token: Optional[str] = None
    huggingface_api_key: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str
    totp_code: str

# --- NOUVEAU : Schémas pour les Projets ---
class ProjectBase(BaseModel):
    title: str

class ProjectCreate(ProjectBase):
    pass

class ProjectResponse(ProjectBase):
    id: int
    created_at: datetime
    is_pinned: bool

class Config:
        from_attributes = True

# --- NOUVEAU : Schémas pour les Messages ---
class MessageBase(BaseModel):
    role: str
    content: str

class MessageCreate(MessageBase):
    pass

class MessageResponse(MessageBase):
    id: int
    created_at: datetime
    project_id: int

class ProjectRename(BaseModel):
    title: str