from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, UploadFile, File
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import List
import os, json, asyncio, shutil
from datetime import datetime
import pytz

from .database import engine, Base, get_db, SessionLocal
from .auth import get_password_hash, generate_totp_secret, get_totp_uri, verify_password, verify_totp, create_access_token, verify_token
from .schemas import AdminCreate, LoginRequest, ProjectCreate, ProjectResponse, ProjectRename, MessageCreate, MessageResponse, PasswordChange
from .models import User, Project, Message, SystemSettings, AIModel, FinancialLog
from .orchestrator import run_orchestrator, sync_providers_models, sync_finances

Base.metadata.create_all(bind=engine)
app = FastAPI(title="AETHAS38")

assets_path = os.path.join(os.getcwd(), "frontend", "assets")
avatars_path = os.path.join(assets_path, "avatars")
os.makedirs(assets_path, exist_ok=True)
os.makedirs(avatars_path, exist_ok=True)
app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

async def scheduler_task():
    tz = pytz.timezone('Europe/Paris')
    while True:
        now = datetime.now(tz)
        if (now.hour == 0 or now.hour == 12) and now.minute == 0:
            db = SessionLocal()
            settings = db.query(SystemSettings).first()
            if settings:
                try: await sync_providers_models(db, settings, "Automatique")
                except: pass
            db.close()
            await asyncio.sleep(60)
        await asyncio.sleep(30)

@app.on_event("startup")
async def startup_event(): asyncio.create_task(scheduler_task())

def is_setup_required(db: Session) -> bool: return db.query(User).filter(User.is_superadmin == True).first() is None

def get_current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("session_token")
    if not token: raise HTTPException(status_code=401, detail="Non authentifié")
    payload = verify_token(token)
    if not payload: raise HTTPException(status_code=401, detail="Session expirée")
    user = db.query(User).filter(User.username == payload.get("sub")).first()
    if not user: raise HTTPException(status_code=401, detail="Utilisateur introuvable")
    return user

@app.get("/")
def read_root(db: Session = Depends(get_db)): return RedirectResponse(url="/setup") if is_setup_required(db) else RedirectResponse(url="/login")
@app.get("/setup")
def setup_page(db: Session = Depends(get_db)): return RedirectResponse(url="/login") if not is_setup_required(db) else FileResponse(os.path.join(os.getcwd(), "frontend", "index.html"))
@app.get("/login")
def login_page(db: Session = Depends(get_db)): return RedirectResponse(url="/setup") if is_setup_required(db) else FileResponse(os.path.join(os.getcwd(), "frontend", "login.html"))

@app.post("/api/setup")
def create_admin(admin_data: AdminCreate, db: Session = Depends(get_db)):
    if not is_setup_required(db): raise HTTPException(status_code=403, detail="Déjà installé.")
    new_admin = User(email=admin_data.email, username=admin_data.username, hashed_password=get_password_hash(admin_data.password), totp_secret=generate_totp_secret(), is_admin=True, is_superadmin=True)
    db.add(new_admin)
    new_settings = SystemSettings(smtp_host=admin_data.smtp_host, smtp_port=admin_data.smtp_port, smtp_user=admin_data.smtp_user, smtp_password=admin_data.smtp_password, openrouter_api_key=admin_data.openrouter_api_key, openrouter_management_key=admin_data.openrouter_management_key, groq_api_key=admin_data.groq_api_key, gemini_api_key=admin_data.gemini_api_key, deepseek_api_key=admin_data.deepseek_api_key, mistral_api_key=admin_data.mistral_api_key, cloudflare_account_id=admin_data.cloudflare_account_id, cloudflare_api_token=admin_data.cloudflare_api_token, huggingface_api_key=admin_data.huggingface_api_key)
    db.add(new_settings)
    db.commit()
    db.refresh(new_admin)
    return {"message": "Succès", "totp_secret": new_admin.totp_secret, "totp_uri": get_totp_uri(new_admin.totp_secret, new_admin.username)}

@app.post("/api/login")
def login(login_data: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == login_data.username).first()
    if not user or not verify_password(login_data.password, user.hashed_password): raise HTTPException(status_code=401, detail="Identifiants incorrects.")
    if not verify_totp(user.totp_secret, login_data.totp_code): raise HTTPException(status_code=401, detail="2FA invalide.")
    response.set_cookie(key="session_token", value=create_access_token(data={"sub": user.username}), httponly=True, max_age=3600, samesite="lax")
    return {"message": "Connexion réussie"}

@app.get("/dashboard")
def dashboard(request: Request):
    token = request.cookies.get("session_token")
    if not token or not verify_token(token): return RedirectResponse(url="/login")
    return FileResponse(os.path.join(os.getcwd(), "frontend", "dashboard.html"))

@app.get("/api/users/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {"username": current_user.username, "is_admin": current_user.is_admin, "is_superadmin": current_user.is_superadmin, "avatar_path": current_user.avatar_path}

@app.put("/api/users/me/password")
def change_password(passwords: PasswordChange, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not verify_password(passwords.old_password, current_user.hashed_password): raise HTTPException(status_code=400, detail="L'ancien mot de passe est incorrect.")
    if len(passwords.new_password) < 8: raise HTTPException(status_code=400, detail="8 caractères minimum.")
    current_user.hashed_password = get_password_hash(passwords.new_password)
    db.commit()
    return {"message": "Mot de passe mis à jour."}

@app.post("/api/users/me/avatar")
async def upload_avatar(file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    file_location = os.path.join(avatars_path, f"user_{current_user.id}.jpg")
    with open(file_location, "wb") as buffer: shutil.copyfileobj(file.file, buffer)
    current_user.avatar_path = f"/assets/avatars/user_{current_user.id}.jpg?v={int(datetime.now().timestamp())}"
    db.commit()
    return {"message": "Avatar mis à jour", "avatar_path": current_user.avatar_path}

@app.get("/api/projects", response_model=List[ProjectResponse])
def get_projects(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)): return db.query(Project).filter(Project.user_id == current_user.id).order_by(Project.created_at.desc()).all()

@app.post("/api/projects", response_model=ProjectResponse)
def create_project(project: ProjectCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = Project(title=project.title, user_id=current_user.id); db.add(p); db.commit(); db.refresh(p); return p

@app.put("/api/projects/{project_id}/rename", response_model=ProjectResponse)
def rename_project(project_id: int, project_data: ProjectRename, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not p: raise HTTPException(status_code=404)
    p.title = project_data.title; db.commit(); db.refresh(p); return p

@app.put("/api/projects/{project_id}/pin", response_model=ProjectResponse)
def toggle_pin_project(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not p: raise HTTPException(status_code=404)
    p.is_pinned = not p.is_pinned; db.commit(); db.refresh(p); return p

@app.delete("/api/projects/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not p: raise HTTPException(status_code=404)
    db.delete(p); db.commit(); return {"message": "Supprimé"}

@app.get("/api/projects/{project_id}/export")
def export_project(project_id: int, format: str = "txt", db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    messages = db.query(Message).filter(Message.project_id == project_id).order_by(Message.created_at.asc()).all()
    if format == "json":
        data = [{"role": m.role, "content": m.content, "date": m.created_at.isoformat()} for m in messages]
        return Response(content=json.dumps(data, indent=2), media_type="application/json", headers={"Content-Disposition": f"attachment; filename=export_{project_id}.json"})
    text = f"--- HISTORIQUE : {p.title} ---\n\n"
    for m in messages: text += f"[{m.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {'VOUS' if m.role == 'user' else 'AETHAS38'}:\n{m.content}\n\n{'-'*50}\n\n"
    return Response(content=text, media_type="text/plain;charset=utf-8", headers={"Content-Disposition": f"attachment; filename=export_{project_id}.txt"})

@app.get("/api/projects/{project_id}/messages", response_model=List[MessageResponse])
def get_messages(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)): return db.query(Message).filter(Message.project_id == project_id).order_by(Message.created_at.asc()).all()

@app.post("/api/projects/{project_id}/messages", response_model=List[MessageResponse])
async def create_message(project_id: int, message: MessageCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    final_content = message.content
    if message.file_content and message.file_name:
        final_content = f"[Fichier attaché : {message.file_name}]\n```\n{message.file_content}\n```\n\n{message.content}"

    db.add(Message(role=message.role, content=final_content, project_id=project_id))
    db.commit()
    
    history = db.query(Message).filter(Message.project_id == project_id).order_by(Message.created_at.asc()).all()
    settings = db.query(SystemSettings).first()
    conf = message.config.dict() if message.config else {"workers": ["gemini-3.5-flash-lite"]} 
    
    ai_resp = await run_orchestrator(db, history, settings, conf)
    
    db.add(Message(role="assistant", content=ai_resp, project_id=project_id))
    db.commit()
    return db.query(Message).filter(Message.project_id == project_id).order_by(Message.created_at.asc()).all()

# --- ROUTES MODÈLES & FINANCES ---
@app.get("/api/models/info")
def get_models_info(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    settings = db.query(SystemSettings).first()
    return {
        "last_sync_date": settings.last_sync_date.isoformat() if settings and settings.last_sync_date else None,
        "last_sync_type": settings.last_sync_type if settings else None,
        "models": db.query(AIModel).order_by(AIModel.name.asc()).all(),
        "finances": db.query(FinancialLog).all()
    }

@app.get("/api/finances")
def get_finances(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(FinancialLog).all()

@app.post("/api/models/sync")
async def trigger_model_sync(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_admin: raise HTTPException(status_code=403, detail="Accès admin requis.")
    settings = db.query(SystemSettings).first()
    return await sync_providers_models(db, settings, "Manuelle")

@app.get("/api/models/export")
def export_models(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_admin: raise HTTPException(status_code=403, detail="Accès admin requis.")
    models = db.query(AIModel).all()
    data = [{"provider": m.provider, "model_id": m.model_id, "name": m.name, "description_fr": m.description_fr, "domain": m.domain, "is_free": m.is_free, "context_length": m.context_length, "pricing_prompt": m.pricing_prompt, "pricing_completion": m.pricing_completion} for m in models]
    return Response(content=json.dumps(data), media_type="application/json", headers={"Content-Disposition": "attachment; filename=aethas38_models.json"})