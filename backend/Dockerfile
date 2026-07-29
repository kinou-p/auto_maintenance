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

# Configurer pwuser avec accès docker et ddev
RUN groupadd -g 999 hostdocker || true && \
    usermod -aG hostdocker pwuser || true && \
    mkdir -p /home/pwuser/ddev-projects /app/data && \
    chown -R pwuser:pwuser /app /home/pwuser

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY cli.py start.py ./

RUN chown -R pwuser:pwuser /app

USER pwuser

RUN ddev config global --docker-buildx-version=0.35.0 --router-http-port=8088 --router-https-port=8443 --router-bind-all-interfaces=true

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "backend.main:app"]
