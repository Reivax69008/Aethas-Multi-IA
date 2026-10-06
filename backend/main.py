from fastapi import FastAPI, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

# Importation de nos modules locaux
from .database import engine, Base, get_db
from .models import User

# Création des tables dans la base de données (si elles n'existent pas)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AETHAS38 - Orchestrateur Multi-IA")

def is_setup_required(db: Session) -> bool:
    """Vérifie si la base de données contient au moins un administrateur."""
    admin = db.query(User).filter(User.is_admin == True).first()
    return admin is None

@app.get("/")
def read_root(db: Session = Depends(get_db)):
    """Route principale : redirige selon l'état de l'installation."""
    if is_setup_required(db):
        return RedirectResponse(url="/setup")
    return RedirectResponse(url="/login")

@app.get("/setup")
def setup_page(db: Session = Depends(get_db)):
    """Affiche l'assistant d'installation (Frontend Vue.js à venir)."""
    if not is_setup_required(db):
        return RedirectResponse(url="/login")
    return {"message": "Assistant d'installation AETHAS38. Veuillez créer le compte Administrateur."}

@app.get("/login")
def login_page(db: Session = Depends(get_db)):
    """Affiche la page de connexion sécurisée."""
    if is_setup_required(db):
        return RedirectResponse(url="/setup")
    return {"message": "Page de connexion (Frontend Vue.js à venir)."}