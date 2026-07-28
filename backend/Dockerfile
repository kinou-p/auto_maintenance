FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

WORKDIR /app

# Dépendances système supplémentaires si besoin
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    jq \
    fonts-dejavu-core \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Copier le fichier des exigences et installer les packages Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copier le code backend
COPY backend/ ./backend/
COPY cli.py start.py ./

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
