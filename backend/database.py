import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

# Récupération de l'URL injectée par Docker via .env (avec repli SQLite pour les tests locaux)
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./aethas38.db")

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()