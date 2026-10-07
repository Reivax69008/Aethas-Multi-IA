from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, UploadFile, File
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import List
import os
import json

# Importation de nos modules locaux
from .database import engine, Base, get_db
from .auth import get_password_hash, generate_totp_secret, get_totp_uri, verify_password, verify_totp, create_access_token, verify_token
from .schemas import AdminCreate, LoginRequest, ProjectCreate, ProjectResponse, ProjectRename, MessageCreate, MessageResponse, PasswordChange
from .models import User, Project, Message, SystemSettings, AIModel
from .orchestrator import run_orchestrator, sync_providers_models

# Création des tables dans la base de données
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AETHAS38 - Orchestrateur Multi-IA")

# Configuration des fichiers statiques
assets_path = os.path.join(os.getcwd(), "frontend", "assets")
os.makedirs(assets_path, exist_ok=True)
app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

def is_setup_required(db: Session) -> bool:
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
    frontend_path = os.path.join(os.getcwd(), "frontend", "index.html")
    if not os.path.exists(frontend_path):
        raise HTTPException(status_code=404, detail="Interface introuvable.")
    return FileResponse(frontend_path)

@app.get("/login")
def login_page(db: Session = Depends(get_db)):
    if is_setup_required(db):
        return RedirectResponse(url="/setup")
    frontend_path = os.path.join(os.getcwd(), "frontend", "login.html")
    if not os.path.exists(frontend_path):
        raise HTTPException(status_code=404, detail="Interface de connexion introuvable.")
    return FileResponse(frontend_path)

@app.post("/api/setup")
def create_admin(admin_data: AdminCreate, db: Session = Depends(get_db)):
    if not is_setup_required(db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="L'installation a déjà été effectuée.")

    hashed_pw = get_password_hash(admin_data.password)
    totp_secret = generate_totp_secret()
    new_admin = User(email=admin_data.email, username=admin_data.username, hashed_password=hashed_pw, totp_secret=totp_secret, is_admin=True)
    db.add(new_admin)

    new_settings = SystemSettings(
        smtp_host=admin_data.smtp_host, smtp_port=admin_data.smtp_port, smtp_user=admin_data.smtp_user, smtp_password=admin_data.smtp_password,
        openrouter_api_key=admin_data.openrouter_api_key, openrouter_management_key=admin_data.openrouter_management_key,
        groq_api_key=admin_data.groq_api_key, gemini_api_key=admin_data.gemini_api_key, deepseek_api_key=admin_data.deepseek_api_key,
        mistral_api_key=admin_data.mistral_api_key, cloudflare_account_id=admin_data.cloudflare_account_id, cloudflare_api_token=admin_data.cloudflare_api_token,
        huggingface_api_key=admin_data.huggingface_api_key
    )
    db.add(new_settings)
    db.commit()
    db.refresh(new_admin)

    return {"message": "Configuration terminée avec succès.", "totp_secret": totp_secret, "totp_uri": get_totp_uri(totp_secret, new_admin.username)}

@app.post("/api/login")
def login(login_data: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == login_data.username).first()
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Identifiants incorrects.")
    if not verify_totp(user.totp_secret, login_data.totp_code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Code 2FA invalide.")
    
    access_token = create_access_token(data={"sub": user.username})
    response.set_cookie(key="session_token", value=access_token, httponly=True, max_age=3600, samesite="lax")
    return {"message": "Connexion réussie"}

@app.get("/dashboard")
def dashboard(request: Request):
    token = request.cookies.get("session_token")
    if not token or not verify_token(token):
        return RedirectResponse(url="/login")
    frontend_path = os.path.join(os.getcwd(), "frontend", "dashboard.html")
    return FileResponse(frontend_path)

@app.put("/api/users/me/password")
def change_password(passwords: PasswordChange, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Permet à l'utilisateur connecté de modifier son propre mot de passe."""
    if not verify_password(passwords.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="L'ancien mot de passe est incorrect.")
    
    if len(passwords.new_password) < 8:
        raise HTTPException(status_code=400, detail="Le nouveau mot de passe doit contenir au moins 8 caractères.")
        
    current_user.hashed_password = get_password_hash(passwords.new_password)
    db.commit()
    return {"message": "Mot de passe mis à jour avec succès."}

def get_current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("session_token")
    if not token: raise HTTPException(status_code=401, detail="Non authentifié")
    payload = verify_token(token)
    if not payload: raise HTTPException(status_code=401, detail="Session expirée")
    user = db.query(User).filter(User.username == payload.get("sub")).first()
    if not user: raise HTTPException(status_code=401, detail="Utilisateur introuvable")
    return user

# --- GESTION DES PROJETS ---
@app.get("/api/projects", response_model=List[ProjectResponse])
def get_projects(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Project).filter(Project.user_id == current_user.id).order_by(Project.created_at.desc()).all()

@app.post("/api/projects", response_model=ProjectResponse)
def create_project(project: ProjectCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    new_project = Project(title=project.title, user_id=current_user.id)
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    return new_project

@app.put("/api/projects/{project_id}/rename", response_model=ProjectResponse)
def rename_project(project_id: int, project_data: ProjectRename, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not project: raise HTTPException(status_code=404, detail="Projet introuvable")
    project.title = project_data.title
    db.commit()
    db.refresh(project)
    return project

@app.put("/api/projects/{project_id}/pin", response_model=ProjectResponse)
def toggle_pin_project(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not project: raise HTTPException(status_code=404, detail="Projet introuvable")
    project.is_pinned = not project.is_pinned
    db.commit()
    db.refresh(project)
    return project

@app.delete("/api/projects/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not project: raise HTTPException(status_code=404, detail="Projet introuvable")
    db.delete(project)
    db.commit()
    return {"message": "Projet supprimé"}

# --- GESTION DES MESSAGES ---
@app.get("/api/projects/{project_id}/messages", response_model=List[MessageResponse])
def get_messages(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not project: raise HTTPException(status_code=404, detail="Projet introuvable")
    return db.query(Message).filter(Message.project_id == project_id).order_by(Message.created_at.asc()).all()

@app.post("/api/projects/{project_id}/messages", response_model=List[MessageResponse])
async def create_message(project_id: int, message: MessageCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not project: raise HTTPException(status_code=404, detail="Projet introuvable")
    
    user_message = Message(role=message.role, content=message.content, project_id=project_id)
    db.add(user_message)
    db.commit()

    history = db.query(Message).filter(Message.project_id == project_id).order_by(Message.created_at.asc()).all()
    settings = db.query(SystemSettings).first()

    orchestrator_config = message.config.dict() if message.config else {"workers": ["gemini-3.5-flash-lite"]} 
    
    ai_response_text = await run_orchestrator(history, settings, orchestrator_config)

    ai_message = Message(role="assistant", content=ai_response_text, project_id=project_id)
    db.add(ai_message)
    db.commit()

    return db.query(Message).filter(Message.project_id == project_id).order_by(Message.created_at.asc()).all()

# --- GESTION DES MODELES ---
@app.post("/api/models/sync")
async def trigger_model_sync(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs.")
    settings = db.query(SystemSettings).first()
    return await sync_providers_models(db, settings)

@app.get("/api/models")
def get_models(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(AIModel).order_by(AIModel.name.asc()).all()

@app.get("/api/models/export")
def export_models(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_admin: raise HTTPException(status_code=403, detail="Accès admin requis.")
    models = db.query(AIModel).all()
    models_data = [{"provider": m.provider, "model_id": m.model_id, "name": m.name, "context_length": m.context_length, "pricing_prompt": m.pricing_prompt, "pricing_completion": m.pricing_completion} for m in models]
    return Response(content=json.dumps(models_data), media_type="application/json", headers={"Content-Disposition": "attachment; filename=aethas38_models.json"})

@app.post("/api/models/import")
async def import_models(file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_admin: raise HTTPException(status_code=403, detail="Accès admin requis.")
    content = await file.read()
    try:
        data = json.loads(content)
        imported_count = 0
        for item in data:
            existing = db.query(AIModel).filter(AIModel.model_id == item["model_id"]).first()
            if not existing:
                db.add(AIModel(**item))
                imported_count += 1
        db.commit()
        return {"message": f"Import réussi. {imported_count} nouveaux modèles ajoutés."}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Fichier JSON invalide ou mal formaté.")