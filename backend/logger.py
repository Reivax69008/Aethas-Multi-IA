import logging
from logging.handlers import TimedRotatingFileHandler
import os
import sys

# Création du dossier logs à la racine du projet
log_dir = os.path.join(os.getcwd(), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "aethas38_system.log")

# Configuration du logger
system_logger = logging.getLogger("AETHAS38_Logger")
system_logger.setLevel(logging.INFO)

if not system_logger.handlers:
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%d/%m/%Y %H:%M:%S')

    # 1. Rotation fichier tous les jours à minuit, conservation sur 7 jours
    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    system_logger.addHandler(file_handler)

    # 2. Sortie standard (visible dans docker logs / Dockge)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    system_logger.addHandler(console_handler)

    system_logger.info("Initialisation du système de logs AETHAS38 réussie.")