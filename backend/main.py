from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
import requests
import asyncio
import os
import uuid
import json
import subprocess
import urllib3
import socket
import config

# Forçage IPv4
old_getaddrinfo = socket.getaddrinfo
def force_ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return old_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = force_ipv4_getaddrinfo

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = FastAPI(title="AETHAS38 API")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
MEDIA_DIR = os.path.join(SESSIONS_DIR, "media")
TEMP_DIR = os.path.join(SESSIONS_DIR, "temp")

os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")

class ExportRequest(BaseModel):
    content: str
    format: str  # pdf, txt, md, json
    type: str    # prompt ou response

@app.get("/", response_class=HTMLResponse)
async def serve_admin():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/config")
async def get_config():
    return config.load_config()

@app.post("/api/config")
async def update_config(data: dict):
    config.save_config(data)
    return {"status": "success", "message": "Configuration sauvegardée avec succès."}

@app.post("/api/export")
async def export_content(req: ExportRequest):
    filename_base = f"aethas38_{req.type}_{uuid.uuid4().hex[:8]}"
    
    if req.format == "txt":
        return Response(
            content=req.content,
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.txt"}
        )
    
    elif req.format == "md":
        return Response(
            content=f"# AETHAS38 Export ({req.type.upper()})\n\n{req.content}",
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.md"}
        )
        
    elif req.format == "json":
        json_data = json.dumps({"type": req.type, "content": req.content}, indent=4, ensure_ascii=False)
        return Response(
            content=json_data,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.json"}
        )
        
    elif req.format == "pdf":
        # Utilisation de LibreOffice en mode headless
        html_filename = os.path.join(TEMP_DIR, f"{filename_base}.html")
        pdf_filename = os.path.join(TEMP_DIR, f"{filename_base}.pdf")
        
        # Création d'un HTML propre pour la conversion
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; color: #333; }}
                h1 {{ color: #00e5ff; border-bottom: 2px solid #ddd; padding-bottom: 10px; }}
                pre, p {{ white-space: pre-wrap; line-height: 1.6; background: #f4f4f4; padding: 15px; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <h1>AETHAS38 - Export {req.type.upper()}</h1>
            <p>{req.content}</p>
        </body>
        </html>
        """
        
        with open(html_filename, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        try:
            # Commande LibreOffice headless pour convertir le HTML en PDF
            # Note: selon l'OS (Windows vs Linux Docker), la commande peut s'appeler 'soffice' ou 'libreoffice'
            cmd = ["soffice", "--headless", "--convert-to", "pdf", "--outdir", TEMP_DIR, html_filename]
            
            # Exécution synchrone dans un thread pour ne pas bloquer l'API
            def run_libreoffice():
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
            await asyncio.to_thread(run_libreoffice)
            
            if not os.path.exists(pdf_filename):
                raise Exception("La génération du PDF par LibreOffice a échoué.")
                
            with open(pdf_filename, "rb") as pdf_file:
                pdf_bytes = pdf_file.read()
                
            # Nettoyage des fichiers temporaires
            os.remove(html_filename)
            os.remove(pdf_filename)
            
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={filename_base}.pdf"}
            )
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erreur de génération PDF via LibreOffice : {str(e)}")
        
    raise HTTPException(status_code=400, detail="Format d'export non supporté.")