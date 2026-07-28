FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

WORKDIR /app

# Dépendances système, Docker CLI et DDEV
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    jq \
    fonts-dejavu-core \
    procps \
    gnupg \
    ca-certificates \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://pkg.ddev.com/apt/gpg.key | gpg --dearmor -o /etc/apt/keyrings/ddev.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/ddev.gpg] https://pkg.ddev.com/apt/ * *" > /etc/apt/sources.list.d/ddev.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends ddev docker.io \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY cli.py start.py ./

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
