from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.responses import RedirectResponse, FileResponse
from sqlalchemy.orm import Session
import os

# Importation de nos modules locaux
from .database import engine, Base, get_db
from .models import User
from .auth import get_password_hash, generate_totp_secret, get_totp_uri, verify_password, verify_totp, create_access_token, verify_token
from .schemas import AdminCreate, LoginRequest

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
    """Affiche l'interface d'installation Vue.js."""
    if not is_setup_required(db):
        return RedirectResponse(url="/login")
    
    # Chemin vers le fichier HTML depuis la racine de l'application Docker (/app)
    frontend_path = os.path.join(os.getcwd(), "frontend", "index.html")
    if not os.path.exists(frontend_path):
        raise HTTPException(status_code=404, detail="Interface introuvable.")
        
    return FileResponse(frontend_path)

@app.get("/login")
def login_page(db: Session = Depends(get_db)):
    """Affiche la page de connexion sécurisée."""
    if is_setup_required(db):
        return RedirectResponse(url="/setup")
        
    frontend_path = os.path.join(os.getcwd(), "frontend", "login.html")
    if not os.path.exists(frontend_path):
        raise HTTPException(status_code=404, detail="Interface de connexion introuvable.")
        
    return FileResponse(frontend_path)

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

@app.post("/api/login")
def login(login_data: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """Vérifie les identifiants et crée une session de 60 minutes."""
    user = db.query(User).filter(User.username == login_data.username).first()
    
    # Vérification de l'utilisateur et du mot de passe
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nom d'utilisateur ou mot de passe incorrect."
        )
    
    # Vérification du code 2FA
    if not verify_totp(user.totp_secret, login_data.totp_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Code 2FA invalide."
        )
    
    # Création du jeton de session
    access_token = create_access_token(data={"sub": user.username})
    
    # Injection du jeton dans un cookie sécurisé (invisible pour le JavaScript côté client)
    response.set_cookie(
        key="session_token",
        value=access_token,
        httponly=True,
        max_age=3600, # 3600 secondes = 60 minutes
        samesite="lax"
    )
    
    return {"message": "Connexion réussie"}

@app.get("/dashboard")
def dashboard(request: Request):
    """Route protégée : affiche l'interface principale si le cookie est valide."""
    token = request.cookies.get("session_token")
    if not token:
        return RedirectResponse(url="/login")
        
    payload = verify_token(token)
    if not payload:
        return RedirectResponse(url="/login")
        
    frontend_path = os.path.join(os.getcwd(), "frontend", "dashboard.html")
    if not os.path.exists(frontend_path):
        raise HTTPException(status_code=404, detail="Interface du tableau de bord introuvable.")
        
    return FileResponse(frontend_path)