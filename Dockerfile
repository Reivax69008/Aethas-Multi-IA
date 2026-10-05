FROM python:3.13-slim

WORKDIR /app

# Installation des dépendances système de base
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copie et installation des bibliothèques Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code source
COPY . .

EXPOSE 5001

CMD ["python", "main.py"]