from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

# Importation de nos modules locaux
from .database import engine, Base, get_db
from .models import User
from .auth import get_password_hash, generate_totp_secret, get_totp_uri
from .schemas import AdminCreate

# Création des tables dans la base de données
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AETHAS38 - Orchestrateur Multi-IA")

def is_setup_required(db: Session) -> bool:
    """Vérifie si la base de données contient au moins un administrateur."""
    admin = db.query(User).filter(User.is_admin == True).first()
    return admin is None

@app.get("/")
def read_root(db: Session = Depends(get_db)):
    if is_setup_required(db):
        return RedirectResponse(url="/setup")
    return RedirectResponse(url="/login")

@app.get("/setup")
def setup_page(db: Session = Depends(get_db)):
    if not is_setup_required(db):
        return RedirectResponse(url="/login")
    return {"message": "Assistant d'installation AETHAS38. Veuillez créer le compte Administrateur."}

@app.get("/login")
def login_page(db: Session = Depends(get_db)):
    if is_setup_required(db):
        return RedirectResponse(url="/setup")
    return {"message": "Page de connexion."}

@app.post("/api/setup")
def create_admin(admin_data: AdminCreate, db: Session = Depends(get_db)):
    """Reçoit les données du frontend, crée l'admin et retourne le QR Code 2FA."""
    if not is_setup_required(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="L'installation a déjà été effectuée."
        )

    # Sécurisation des accès
    hashed_pw = get_password_hash(admin_data.password)
    totp_secret = generate_totp_secret()

    new_admin = User(
        email=admin_data.email,
        username=admin_data.username,
        hashed_password=hashed_pw,
        totp_secret=totp_secret,
        is_admin=True
    )

    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)

    # Génération de l'URI pour l'affichage du QR Code côté frontend
    totp_uri = get_totp_uri(totp_secret, new_admin.username)

    return {
        "message": "Administrateur créé avec succès.",
        "totp_secret": totp_secret,
        "totp_uri": totp_uri
    }