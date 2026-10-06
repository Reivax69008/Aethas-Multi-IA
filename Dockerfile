FROM python:3.13-slim

WORKDIR /app

# Installation des dépendances système (LibreOffice, etc.)
RUN apt-get update && apt-get install -y \
    libreoffice \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copie et installation des dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie de tout le code source de la racine
COPY . .

EXPOSE 5001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5001"]