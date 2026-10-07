from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, List

class AdminCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
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

class ProjectBase(BaseModel):
    title: str

class ProjectCreate(ProjectBase): pass

class ProjectResponse(ProjectBase):
    id: int
    created_at: datetime
    is_pinned: bool
    class Config: from_attributes = True

class ProjectRename(BaseModel):
    title: str

class OrchestratorConfig(BaseModel):
    workers: List[str]
    prompter: Optional[str] = "gemini-3.5-flash-lite"
    concatenator: Optional[str] = "gemini-3.5-flash-lite"

class MessageBase(BaseModel):
    role: str
    content: str

class MessageCreate(MessageBase):
    config: Optional[OrchestratorConfig] = None

class MessageResponse(MessageBase):
    id: int
    created_at: datetime
    project_id: int
    class Config: from_attributes = True

class PasswordChange(BaseModel):
    old_password: str
    new_password: str