FROM python:3.13-slim

WORKDIR /app

# --no-install-recommends évite d'installer 1 Go de pilotes graphiques/audio inutiles
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-calc \
    libreoffice-writer \
    libreoffice-impress \
    libreoffice-common \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Seule cette couche est reconstruite quand vous modifiez le code (durée : ~3 secondes)
COPY . .

EXPOSE 5001
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "5001"]