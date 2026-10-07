from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import List
import os

# Importation de nos modules locaux
from .database import engine, Base, get_db
from .models import User, Project, Message
from .auth import get_password_hash, generate_totp_secret, get_totp_uri, verify_password, verify_totp, create_access_token, verify_token
from .schemas import AdminCreate, LoginRequest, ProjectCreate, ProjectResponse, ProjectRename, MessageCreate, MessageResponse
from .models import User, Project, Message, SystemSettings

# Création des tables dans la base de données
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AETHAS38 - Orchestrateur Multi-IA")

# Configuration des fichiers statiques (images, css locaux, etc.)
assets_path = os.path.join(os.getcwd(), "frontend", "assets")
os.makedirs(assets_path, exist_ok=True) # Crée le dossier s'il n'existe pas
app.mount("/assets", StaticFiles(directory=assets_path), name="assets")
# Définition des routes du logo dans login


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
    """Reçoit les données du frontend, crée l'admin, sauvegarde la configuration et retourne le QR Code 2FA."""
    if not is_setup_required(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="L'installation a déjà été effectuée."
        )

    # Création du Super Admin
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

    # Sauvegarde des paramètres système
    new_settings = SystemSettings(
        smtp_host=admin_data.smtp_host,
        smtp_port=admin_data.smtp_port,
        smtp_user=admin_data.smtp_user,
        smtp_password=admin_data.smtp_password,
        openrouter_api_key=admin_data.openrouter_api_key,
        openrouter_management_key=admin_data.openrouter_management_key,
        groq_api_key=admin_data.groq_api_key,
        gemini_api_key=admin_data.gemini_api_key,
        deepseek_api_key=admin_data.deepseek_api_key,
        mistral_api_key=admin_data.mistral_api_key,
        cloudflare_account_id=admin_data.cloudflare_account_id,
        cloudflare_api_token=admin_data.cloudflare_api_token,
        huggingface_api_key=admin_data.huggingface_api_key
    )
    db.add(new_settings)

    db.commit()
    db.refresh(new_admin)

    totp_uri = get_totp_uri(totp_secret, new_admin.username)
    return {
        "message": "Configuration terminée avec succès.",
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

# --- GESTION DES PROJETS ---

def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Extrait l'utilisateur actuel à partir du cookie de session JWT."""
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="Non authentifié")
    
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Session expirée")
        
    user = db.query(User).filter(User.username == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")
    return user

@app.get("/api/projects", response_model=List[ProjectResponse])
def get_projects(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Récupère tous les projets de l'utilisateur connecté."""
    return db.query(Project).filter(Project.user_id == current_user.id).order_by(Project.created_at.desc()).all()

@app.post("/api/projects", response_model=ProjectResponse)
def create_project(project: ProjectCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Crée un nouveau projet pour l'utilisateur connecté."""
    new_project = Project(title=project.title, user_id=current_user.id)
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    return new_project

@app.put("/api/projects/{project_id}/rename", response_model=ProjectResponse)
def rename_project(project_id: int, project_data: ProjectRename, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Renomme un projet existant."""
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    
    project.title = project_data.title
    db.commit()
    db.refresh(project)
    return project

@app.put("/api/projects/{project_id}/pin", response_model=ProjectResponse)
def toggle_pin_project(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Bascule le statut épinglé (is_pinned) d'un projet."""
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    
    project.is_pinned = not project.is_pinned
    db.commit()
    db.refresh(project)
    return project

@app.delete("/api/projects/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Supprime définitivement un projet et tous ses messages associés."""
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    
    db.delete(project)
    db.commit()
    return {"message": "Projet supprimé"}

# --- GESTION DES MESSAGES ---

@app.get("/api/projects/{project_id}/messages", response_model=List[MessageResponse])
def get_messages(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Récupère tous les messages d'un projet spécifique."""
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    return db.query(Message).filter(Message.project_id == project_id).order_by(Message.created_at.asc()).all()

@app.post("/api/projects/{project_id}/messages", response_model=MessageResponse)
def create_message(project_id: int, message: MessageCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Ajoute un message à un projet."""
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    
    new_message = Message(role=message.role, content=message.content, project_id=project_id)
    db.add(new_message)
    db.commit()
    db.refresh(new_message)
    return new_message