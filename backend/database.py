import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Récupération de l'URL de connexion injectée par Docker via le .env
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

# Création du moteur de connexion (engine)
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# Création de la fabrique de sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Classe de base pour définir nos futures tables (modèles)
Base = declarative_base()

# Dépendance FastAPI pour ouvrir et fermer proprement les sessions BDD
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()