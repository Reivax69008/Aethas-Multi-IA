from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Float
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    totp_secret = Column(String)
    is_admin = Column(Boolean, default=False)
    projects = relationship("Project", back_populates="owner")

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_pinned = Column(Boolean, default=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="projects")
    messages = relationship("Message", back_populates="project", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    role = Column(String)
    content = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    project_id = Column(Integer, ForeignKey("projects.id"))
    project = relationship("Project", back_populates="messages")

class SystemSettings(Base):
    __tablename__ = "system_settings"
    id = Column(Integer, primary_key=True, index=True)
    smtp_host = Column(String, nullable=False)
    smtp_port = Column(Integer, nullable=False)
    smtp_user = Column(String, nullable=False)
    smtp_password = Column(String, nullable=False)
    openrouter_api_key = Column(String, nullable=True)
    openrouter_management_key = Column(String, nullable=True)
    groq_api_key = Column(String, nullable=True)
    gemini_api_key = Column(String, nullable=True)
    deepseek_api_key = Column(String, nullable=True)
    mistral_api_key = Column(String, nullable=True)
    cloudflare_account_id = Column(String, nullable=True)
    cloudflare_api_token = Column(String, nullable=True)
    huggingface_api_key = Column(String, nullable=True)

class AIModel(Base):
    """Stocke la liste des modèles extraits depuis les fournisseurs."""
    __tablename__ = "ai_models"
    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, index=True)
    model_id = Column(String, unique=True, index=True)
    name = Column(String)
    context_length = Column(Integer)
    pricing_prompt = Column(Float)
    pricing_completion = Column(Float)
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class FinancialLog(Base):
    """Suivi financier par fournisseur."""
    __tablename__ = "financial_logs"
    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, index=True)
    balance = Column(Float)
    total_usage = Column(Float)
    checked_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))