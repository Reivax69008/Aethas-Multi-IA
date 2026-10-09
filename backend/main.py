from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, UploadFile, File
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import List
import os, json, asyncio, shutil, base64, io, csv, zipfile
from datetime import datetime, timedelta, timezone
import pytz

from .database import engine, Base, get_db, SessionLocal
from .auth import get_password_hash, generate_totp_secret, get_totp_uri, verify_password, verify_totp, create_access_token, verify_token
from .schemas import AdminCreate, LoginRequest, ProjectCreate, ProjectResponse, ProjectRename, MessageCreate, MessageResponse, PasswordChange, ModelReplacementRequest, LogRequest, SystemSettingsUpdate, SystemSettingsResponse
from .models import User, Project, Message, SystemSettings, AIModel, FinancialLog
from .orchestrator import run_orchestrator, sync_providers_models, sync_finances, activity_logs, log_activity

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
            try:
                settings = db.query(SystemSettings).first()
                if settings:
                    try: await sync_providers_models(db, settings, "Automatique")
                    except: pass
                
                cutoff = datetime.now(timezone.utc) - timedelta(days=7)
                old_projects = db.query(Project).filter(Project.is_pinned == False, Project.created_at < cutoff).all()
                if old_projects:
                    log_activity(f"[Nettoyage] Suppression de {len(old_projects)} discussion(s) de plus de 7 jours.")
                    for op in old_projects:
                        db.delete(op)
                    db.commit()
            except Exception as e:
                db.rollback()
                log_activity(f"[Erreur Nettoyage] {str(e)}")
            finally:
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
    
    # Session valide 8 heures (28800 secondes)
    response.set_cookie(key="session_token", value=create_access_token(data={"sub": user.username}), httponly=True, max_age=28800, samesite="lax")
    return {"message": "Connexion réussie"}

@app.get("/dashboard")
def dashboard(request: Request):
    token = request.cookies.get("session_token")
    if not token or not verify_token(token): return RedirectResponse(url="/login")
    return FileResponse(os.path.join(os.getcwd(), "frontend", "dashboard.html"))

@app.get("/api/logs")
def get_logs():
    return {"logs": activity_logs}

@app.post("/api/logs")
def add_frontend_log(req: LogRequest):
    log_activity(f"[Système UI] {req.message}")
    return {"status": "ok"}

@app.post("/api/models/suggest_replacement")
async def suggest_replacement(req: ModelReplacementRequest, db: Session = Depends(get_db)):
    log_activity(f"⚠️ Modèle indisponible: {req.missing_model}. Demande de suggestion à Gemini...")
    settings = db.query(SystemSettings).first()
    if not settings or not settings.gemini_api_key:
        log_activity("Clé Gemini non trouvée. Fallback forcé sur gemini-3.5-flash-lite.")
        return {"suggestion": "gemini-3.5-flash-lite", "reason": "Clé API Gemini non configurée dans le système."}

    models = db.query(AIModel).all()
    available = [m.model_id for m in models]
    
    prompt = f"Le modèle IA '{req.missing_model}' n'est plus disponible. Voici les modèles disponibles : {', '.join(available)}. Trouve le modèle le plus proche techniquement. Réponds UNIQUEMENT avec ce format strict : ID_DU_MODELE | Brève explication en français de 10 mots max. Si aucun ne correspond, renvoie gemini-3.5-flash-lite | Par défaut."
    
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=settings.gemini_api_key)
        resp = await client.chat.completions.create(model="gemini-3.5-flash-lite", messages=[{"role": "user", "content": prompt}], max_tokens=50)
        res = resp.choices[0].message.content.strip()
        
        if "|" in res:
            parts = res.split("|")
            sugg = parts[0].strip()
            reason = parts[1].strip()
        else:
            sugg = res.strip()
            reason = "Sélectionné par Gemini."
            
        if sugg not in available and sugg != "gemini-3.5-flash-lite":
            sugg = "gemini-3.5-flash-lite"
            reason = "Gemini a suggéré un modèle invalide. Fallback par défaut."

        log_activity(f"✅ Remplacement trouvé : {req.missing_model} -> {sugg}")
        return {"suggestion": sugg, "reason": reason}
    except Exception as e:
        log_activity(f"Erreur d'interrogation Gemini: {str(e)}. Fallback par défaut.")
        return {"suggestion": "gemini-3.5-flash-lite", "reason": f"Erreur API."}

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

# --- ROUTES SUPER-ADMIN ---
@app.get("/api/settings", response_model=SystemSettingsResponse)
def get_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_superadmin: raise HTTPException(status_code=403, detail="Super-Admin requis.")
    return db.query(SystemSettings).first()

@app.put("/api/settings")
def update_settings(settings_data: SystemSettingsUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_superadmin: raise HTTPException(status_code=403, detail="Super-Admin requis.")
    s = db.query(SystemSettings).first()
    if not s: raise HTTPException(status_code=404)
    for k, v in settings_data.dict(exclude_unset=True).items():
        setattr(s, k, v)
    db.commit()
    log_activity("Configuration système mise à jour par le Super-Admin.")
    return {"message": "Paramètres mis à jour avec succès."}

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
    p = db.query(Project).filter(Project.id == project_id).first()
    if p and p.title == "Nouvelle discussion":
        user_msgs = db.query(Message).filter(Message.project_id == project_id, Message.role == "user").order_by(Message.created_at.asc()).all()
        if len(user_msgs) == 1:
            first_content = user_msgs[0].content.split("\n\n[Fichiers joints")[0].strip()
            new_title = first_content.split('\n')[0][:35].strip()
            if not new_title: new_title = "Discussion"
            p.title = new_title + ("..." if len(first_content) > 35 else "")
            db.commit()

    extracted_files_data = []
    files_names = []
    
    if message.files:
        for f in message.files:
            files_names.append(f.name)
            content = f.content
            if content.startswith("data:"):
                try:
                    header, b64data = content.split(",", 1)
                    file_bytes = base64.b64decode(b64data)
                    ext = f.name.split('.')[-1].lower()
                    extracted_text = ""

                    if ext == 'pdf':
                        try:
                            import PyPDF2
                            reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
                            extracted_text = "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
                        except ImportError:
                            extracted_text = "[Erreur: L'administrateur doit exécuter 'pip install PyPDF2' sur le serveur pour lire les PDF.]"
                    
                    elif ext in ['xls', 'xlsx', 'xlsm', 'xlsb']:
                        try:
                            import openpyxl
                            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=False)
                            for sheet_name in wb.sheetnames:
                                sheet = wb[sheet_name]
                                extracted_text += f"\n--- Feuille : {sheet_name} ---\n"
                                for row in sheet.iter_rows(values_only=True):
                                    row_vals = [str(cell) if cell is not None else "" for cell in row]
                                    if any(row_vals):
                                        extracted_text += "\t".join(row_vals) + "\n"
                            
                            if ext in ['xlsm', 'xlsb', 'xls']:
                                try:
                                    from oletools.olevba import VBA_Parser
                                    vbaparser = VBA_Parser("filename", data=file_bytes)
                                    if vbaparser.detect_vba_macros():
                                        extracted_text += "\n\n--- MACROS VBA DETECTEES ---\n"
                                        for (filename, stream_path, vba_filename, vba_code) in vbaparser.extract_macros():
                                            extracted_text += f"\n// Module: {vba_filename}\n{vba_code}\n"
                                except ImportError:
                                    extracted_text += "\n[Extraction VBA impossible: L'administrateur doit exécuter 'pip install oletools' sur le serveur.]\n"
                                except Exception as e:
                                    extracted_text += f"\n[Erreur de lecture VBA interne: {str(e)}]\n"

                        except ImportError:
                            extracted_text = "[Erreur: L'administrateur doit exécuter 'pip install openpyxl' sur le serveur pour lire Excel.]"
                    else:
                        extracted_text = file_bytes.decode('utf-8', errors='replace')
                    
                    extracted_files_data.append({"name": f.name, "content": extracted_text})
                except Exception as e:
                    extracted_files_data.append({"name": f.name, "content": f"[ERREUR DE DECODAGE: {str(e)}]"})
            else:
                extracted_files_data.append({"name": f.name, "content": content})

    db_content = message.content
    if files_names:
        db_content += f"\n\n[Fichiers joints pour analyse : {', '.join(files_names)}]"

    db.add(Message(role=message.role, content=db_content, project_id=project_id))
    db.commit()
    
    history = db.query(Message).filter(Message.project_id == project_id).order_by(Message.created_at.asc()).all()
    settings = db.query(SystemSettings).first()
    conf = message.config.dict() if message.config else {"workers": ["gemini-3.5-flash-lite"]} 
    
    ai_resp = await run_orchestrator(db, history, settings, conf, extracted_files_data)
    
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
    models = db.query(AIModel).order_by(AIModel.provider.asc(), AIModel.name.asc()).all()

    csv_io = io.StringIO()
    writer = csv.writer(csv_io, delimiter=',')
    writer.writerow(["Provider", "Model ID", "Name", "Domain", "Is Free", "Context Length", "Pricing Prompt", "Pricing Completion", "Description"])
    for m in models:
        writer.writerow([m.provider, m.model_id, m.name, m.domain, m.is_free, m.context_length, m.pricing_prompt, m.pricing_completion, m.description_fr])
    
    md_content = f"# Extraction des Modèles IA - AETHAS38\n\n**Date d'extraction :** {datetime.now().strftime('%d/%m/%Y à %H:%M:%S')}\n\n"
    providers = sorted(list(set(m.provider for m in models)))
    for prov in providers:
        md_content += f"## Fournisseur : {prov.upper()}\n\n"
        prov_models = [m for m in models if m.provider == prov]
        for m in prov_models:
            price_info = "**GRATUIT**" if m.is_free else f"In: ${m.pricing_prompt:.2f} / Out: ${m.pricing_completion:.2f}"
            ctx_info = f"{int(m.context_length/1000)}k"
            desc = m.description_fr.replace('\n', ' ') if m.description_fr else ""
            md_content += f"- **{m.name or m.model_id}** (`{m.model_id}`)\n"
            md_content += f"  - *Domaine :* {m.domain}\n"
            md_content += f"  - *Prix (1M tokens) :* {price_info}\n"
            md_content += f"  - *Contexte :* {ctx_info}\n"
            md_content += f"  - *Description :* {desc}\n\n"

    zip_io = io.BytesIO()
    with zipfile.ZipFile(zip_io, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("models_export.csv", csv_io.getvalue().encode('utf-8'))
        zf.writestr(f"{datetime.now().strftime('%Y%m%d')}-extraction-modeles.md", md_content.encode('utf-8'))

    zip_io.seek(0)
    return Response(
        content=zip_io.getvalue(), 
        media_type="application/zip", 
        headers={"Content-Disposition": f"attachment; filename=aethas38_models_{datetime.now().strftime('%Y%m%d')}.zip"}
    )