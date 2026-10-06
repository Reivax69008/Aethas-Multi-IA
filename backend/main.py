from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import os
import config

app = FastAPI(title="AETHAS38 API")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# Montage dynamique
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

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