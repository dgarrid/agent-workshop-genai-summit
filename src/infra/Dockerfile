# =============================================================================
# AGENTE - Dockerfile
# =============================================================================
# Build:
#   docker build -t agent -f infra/Dockerpipfile .
#
# Run:
#   docker run -p 8080:8080 -e ANTHROPIC_API_KEY=sk-ant-... agent
#
# Imagen optimizada para producción (~150MB)
# =============================================================================

# -----------------------------------------------------------------------------
# STAGE 1: Builder
# -----------------------------------------------------------------------------
FROM python:3.11-slim as builder

WORKDIR /app

# Instalar dependencias de build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primero (cache de Docker)
COPY requirements.txt .

# Crear virtualenv e instalar dependencias
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# -----------------------------------------------------------------------------
# STAGE 2: Runtime
# -----------------------------------------------------------------------------
FROM python:3.11-slim as runtime

# Labels
LABEL org.opencontainers.image.title="Agent"
LABEL org.opencontainers.image.description="Agente IA con gobernanza financiera"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.authors="GenAI Summit Workshop"

# Crear usuario no-root por seguridad
RUN groupadd --gid 1000 agente && \
    useradd --uid 1000 --gid agente --shell /bin/bash --create-home agente

WORKDIR /app

# Copiar virtualenv del builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copiar código fuente
COPY --chown=agente:agente src/ ./src/
COPY --chown=agente:agente data/ ./data/

# Crear directorios necesarios
RUN mkdir -p /app/logs/audit && \
    chown -R agente:agente /app/logs

# Variables de entorno por defecto
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Configuración del agente
    ANTHROPIC_MODEL=claude-sonnet-4-5-20250929 \
    BUDGET_LIMIT_EUR=5.00 \
    MAX_ITERATIONS=25 \
    LOG_LEVEL=INFO \
    # Paths
    CRM_DATABASE_PATH=data/crm.db \
    KNOWLEDGE_BASE_PATH=data/knowledge \
    AUDIT_LOG_PATH=logs/audit \
    # Puerto
    PORT=8080

# Cambiar a usuario no-root
USER agente

# Inicializar datos de simulación
RUN python data/setup_data.py

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:${PORT}/agent/health').raise_for_status()" || exit 1

# Puerto
EXPOSE ${PORT}

# Comando por defecto
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT}"]