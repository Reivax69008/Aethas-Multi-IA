import logging
from logging.handlers import TimedRotatingFileHandler
import os
import sys
import time

# Création du dossier logs à la racine du projet (/app/logs dans Docker)
log_dir = os.path.join(os.getcwd(), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "aethas38_system.log")

# Configuration du logger
system_logger = logging.getLogger("AETHAS38_Logger")
system_logger.setLevel(logging.INFO)

if not system_logger.handlers:
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%d/%m/%Y %H:%M:%S')

    # Rotation tous les jours à minuit, conservation sur 30 jours (Point 10)
    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    system_logger.addHandler(file_handler)

    # Sortie console pour Docker / Dockge
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    system_logger.addHandler(console_handler)

    system_logger.info("Initialisation du système de logs AETHAS38 (rétention 30 jours).")

def cleanup_old_logs(retention_days: int = 30) -> int:
    """Supprime physiquement les fichiers de logs de plus de 30 jours."""
    deleted = 0
    now = time.time()
    cutoff = now - (retention_days * 86400)
    if not os.path.exists(log_dir):
        return 0
    for fname in os.listdir(log_dir):
        fpath = os.path.join(log_dir, fname)
        if os.path.isfile(fpath):
            try:
                if os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
                    deleted += 1
            except Exception:
                pass
    if deleted > 0:
        system_logger.info(f"[Purge Logs] {deleted} fichier(s) de log de plus de {retention_days} jours supprimé(s).")
    return deleted