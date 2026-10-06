FROM python:3.13-slim

WORKDIR /app

# Installation de LibreOffice (Headless) et dépendances système
RUN apt-get update && apt-get install -y \
    libreoffice-calc \
    libreoffice-writer \
    libreoffice-impress \
    libreoffice-common \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code source
COPY . .

EXPOSE 5001

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "5001"]