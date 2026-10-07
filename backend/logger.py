import logging
from logging.handlers import TimedRotatingFileHandler
import os

# Création du dossier logs à la racine du projet
log_dir = os.path.join(os.getcwd(), "logs")
os.makedirs(log_dir, exist_ok=True)

# Configuration du logger
system_logger = logging.getLogger("AETHAS38_Logger")
system_logger.setLevel(logging.INFO)

# Rotation tous les jours à minuit, conservation sur 7 jours
handler = TimedRotatingFileHandler(
    filename=os.path.join(log_dir, "aethas38_system.log"),
    when="midnight",
    interval=1,
    backupCount=7,
    encoding="utf-8"
)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%d/%m/%Y %H:%M:%S')
handler.setFormatter(formatter)
system_logger.addHandler(handler)