"""
API REST para el agente

Uso:
    uvicorn src.main:app --reload

Endpoints:
    POST /agent/process  - Procesar una consulta
    GET  /agent/health   - Health check
    GET  /agent/config   - Ver configuración (sin secretos)
"""

import asyncio
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.config import get_settings, validate_environment
from src.core.agent import BudgetedOrchestrator
from src.models.incoming import (
    AgentRequest,
    InputChannel,
    Priority,
    EmailInput,
    CLIInput,
)
from src.models.decision import AgentResponse, DecisionType
from src.tools.registry import get_tool_registry, list_available_tools


# =============================================================================
# SCHEMAS DE REQUEST/RESPONSE
# =============================================================================

class ProcessRequest(BaseModel):
    """Request para procesar un mensaje."""
    
    message: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="Mensaje a procesar",
        examples=["¿Cuál es el estado del cliente CUST-001?"],
    )
    
    channel: str = Field(
        default="api",
        description="Canal de origen",
        examples=["api", "email", "webhook"],
    )
    
    priority: str = Field(
        default="normal",
        description="Prioridad del mensaje",
        examples=["low", "normal", "high", "urgent"],
    )
    
    metadata: Optional[dict] = Field(
        default=None,
        description="Metadatos adicionales",
    )


class ProcessResponse(BaseModel):
    """Response del procesamiento."""
    
    success: bool
    message: str
    decision_type: str
    confidence: str
    
    # Métricas
    session_id: str
    request_id: str
    total_iterations: int
    total_cost_eur: float
    execution_time_ms: float
    budget_remaining_eur: float
    
    # Detalles opcionales
    stopped_reason: Optional[str] = None
    reasoning: Optional[str] = None


class HealthResponse(BaseModel):
    """Response del health check."""
    
    status: str
    timestamp: str
    version: str = "1.0.0"
    model: str
    tools_available: list[str]


class ConfigResponse(BaseModel):
    """Response de configuración (sin secretos)."""
    
    model: str
    budget_limit_eur: float
    max_iterations: int
    eur_usd_rate: float
    tools_available: list[str]


# =============================================================================
# LIFESPAN (STARTUP/SHUTDOWN)
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestión del ciclo de vida de la aplicación.
    
    - Startup: Valida configuración, inicializa orquestador
    - Shutdown: Limpieza
    """
    # ─────────────────────────────────────────────────────────────────────────
    # STARTUP
    # ─────────────────────────────────────────────────────────────────────────
    print("Iniciando Agent API...")
    
    try:
        # Validar configuración
        config_info = validate_environment()
        print(f"   ✅ Configuración validada")
        print(f"   📦 Modelo: {config_info['model']}")
        print(f"   💰 Budget: €{config_info['budget_eur']}")
        
        # Inicializar orquestador global
        tool_registry = get_tool_registry()
        app.state.orchestrator = BudgetedOrchestrator(tool_registry=tool_registry)
        app.state.settings = get_settings()
        
        print(f"   🔧 Tools: {list(tool_registry.keys())}")
        print("   ✅ API lista para recibir requests")
        
    except Exception as e:
        print(f"   ❌ Error de inicialización: {e}")
        raise
    
    yield  # La aplicación se ejecuta aquí
    
    # ─────────────────────────────────────────────────────────────────────────
    # SHUTDOWN
    # ─────────────────────────────────────────────────────────────────────────
    print("Cerrando Agent API...")


# =============================================================================
# APLICACIÓN FASTAPI
# =============================================================================

app = FastAPI(
    title="Agent API",
    description=(
        "API REST para el agente de soporte con gobernanza financiera. "
        "Incluye límite de presupuesto, auditoría completa, y herramientas MCP."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS (permitir todo en desarrollo)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get(
    "/",
    summary="Root",
    description="Información básica de la API",
)
async def root():
    """Endpoint raíz con información de la API."""
    return {
        "name": "Agent API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/agent/health",
    }


@app.get(
    "/agent/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Verifica que la API esté funcionando correctamente",
)
async def health_check():
    """
    Health check endpoint.
    
    Útil para:
    - Kubernetes liveness/readiness probes
    - Load balancers
    - Monitorización
    """
    settings = app.state.settings
    
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        model=settings.anthropic_model,
        tools_available=list_available_tools(),
    )


@app.get(
    "/agent/config",
    response_model=ConfigResponse,
    summary="Ver Configuración",
    description="Muestra la configuración actual (sin secretos)",
)
async def get_config():
    """
    Devuelve la configuración actual del agente.
    
    No incluye secretos como la API key.
    """
    settings = app.state.settings
    
    return ConfigResponse(
        model=settings.anthropic_model,
        budget_limit_eur=settings.budget_limit_eur,
        max_iterations=settings.max_iterations,
        eur_usd_rate=settings.eur_usd_rate,
        tools_available=list_available_tools(),
    )


@app.post(
    "/agent/process",
    response_model=ProcessResponse,
    summary="Procesar Mensaje",
    description="Envía un mensaje al agente para su procesamiento",
    responses={
        200: {"description": "Mensaje procesado exitosamente"},
        400: {"description": "Request inválida"},
        500: {"description": "Error interno del servidor"},
    },
)
async def process_message(request: ProcessRequest):
    """
    Procesa un mensaje con el agente.
    
    El agente:
    1. Analiza el mensaje
    2. Decide si necesita usar herramientas (CRM, Knowledge Base)
    3. Ejecuta las herramientas necesarias
    4. Genera una respuesta
    
    Todo el proceso está limitado por:
    - Presupuesto en EUR
    - Máximo de iteraciones
    - Timeout por llamada
    
    La respuesta incluye métricas de coste y auditoría.
    """
    try:
        # Crear AgentRequest
        agent_request = AgentRequest(
            channel=InputChannel(request.channel) if request.channel in ["api", "email", "webhook", "cli"] else InputChannel.API,
            content=request.message,
            priority=Priority(request.priority) if request.priority in ["low", "normal", "high", "urgent"] else Priority.NORMAL,
            metadata=request.metadata or {},
        )
        
        # Procesar con el orquestador
        orchestrator: BudgetedOrchestrator = app.state.orchestrator
        response: AgentResponse = await orchestrator.process(agent_request)
        
        # Construir respuesta
        return ProcessResponse(
            success=response.success,
            message=response.decision.content,
            decision_type=response.decision.decision_type.value,
            confidence=response.decision.confidence.value,
            session_id=response.session_id,
            request_id=response.request_id,
            total_iterations=response.total_iterations,
            total_cost_eur=response.total_cost_eur,
            execution_time_ms=response.execution_time_ms,
            budget_remaining_eur=response.budget_remaining_eur,
            stopped_reason=response.stopped_reason,
            reasoning=response.decision.reasoning,
        )
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request inválida: {str(e)}",
        )
    
    except Exception as e:
        # Log del error (en producción usar un logger apropiado)
        print(f"❌ Error procesando mensaje: {type(e).__name__}: {e}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor. Por favor, inténtalo de nuevo.",
        )


@app.post(
    "/agent/email",
    response_model=ProcessResponse,
    summary="Procesar Email",
    description="Procesa un email entrante",
)
async def process_email(
    sender: str,
    subject: str,
    body: str,
    priority: str = "normal",
):
    """
    Procesa un email como si llegara al sistema.
    
    Útil para integración con sistemas de ticketing o email.
    """
    try:
        # Validar email
        email_input = EmailInput(
            sender=sender,
            subject=subject,
            body=body,
            priority=Priority(priority) if priority in ["low", "normal", "high", "urgent"] else Priority.NORMAL,
        )
        
        # Convertir a AgentRequest
        agent_request = AgentRequest.from_email(email_input)
        
        # Procesar
        orchestrator: BudgetedOrchestrator = app.state.orchestrator
        response: AgentResponse = await orchestrator.process(agent_request)
        
        return ProcessResponse(
            success=response.success,
            message=response.decision.content,
            decision_type=response.decision.decision_type.value,
            confidence=response.decision.confidence.value,
            session_id=response.session_id,
            request_id=response.request_id,
            total_iterations=response.total_iterations,
            total_cost_eur=response.total_cost_eur,
            execution_time_ms=response.execution_time_ms,
            budget_remaining_eur=response.budget_remaining_eur,
            stopped_reason=response.stopped_reason,
            reasoning=response.decision.reasoning,
        )
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email inválido: {str(e)}",
        )


# =============================================================================
# ERROR HANDLERS
# =============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handler global para excepciones no controladas."""
    print(f"❌ Excepción no controlada: {type(exc).__name__}: {exc}")
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Error interno del servidor",
            "type": type(exc).__name__,
        },
    )