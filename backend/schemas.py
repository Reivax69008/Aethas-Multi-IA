from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class AdminCreate(BaseModel):
    email: EmailStr
    username: str
    password: str

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

    class Config:
        from_attributes = True