"""
Contratos de salida para el agente.

Este módulo define la estructura DETERMINISTA de las decisiones del agente.
Si el LLM alucina un campo o devuelve un tipo incorrecto, Pydantic 
detiene la ejecución antes de que llegue a producción.

Principio: El caos probabilístico del LLM se convierte en objetos Python validados.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any, Annotated, Literal, Union
from pydantic import BaseModel, Field, field_validator, model_validator


# =============================================================================
# ENUMS DE DECISIÓN
# =============================================================================

class DecisionType(str, Enum):
    """Tipos de decisión que puede tomar el agente."""
    RESPONSE = "response"           # Respuesta directa al usuario
    TOOL_CALL = "tool_call"         # Necesita ejecutar una herramienta
    ESCALATE = "escalate"           # Escalar a humano
    CLARIFY = "clarify"             # Pedir aclaración al usuario
    COMPLETE = "complete"           # Tarea completada
    ERROR = "error"                 # Error en el procesamiento


class ConfidenceLevel(str, Enum):
    """Nivel de confianza del agente en su decisión."""
    HIGH = "high"         # >90% seguro
    MEDIUM = "medium"     # 60-90% seguro
    LOW = "low"           # <60% seguro


class EscalationReason(str, Enum):
    """Razones para escalar a un humano."""
    COMPLEX_QUERY = "complex_query"           # Consulta demasiado compleja
    SENSITIVE_DATA = "sensitive_data"         # Involucra datos sensibles
    POLICY_VIOLATION = "policy_violation"     # Posible violación de políticas
    USER_REQUEST = "user_request"             # El usuario lo pidió
    LOW_CONFIDENCE = "low_confidence"         # Agente no está seguro
    OUT_OF_SCOPE = "out_of_scope"             # Fuera del alcance del agente


# =============================================================================
# MODELOS DE HERRAMIENTAS
# =============================================================================

class ToolCall(BaseModel):
    """
    Representa una llamada a herramienta que el agente quiere ejecutar.
    
    El agente NO ejecuta la herramienta directamente. El orquestador
    valida la llamada, la ejecuta, y devuelve el resultado.
    """
    
    tool_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Nombre de la herramienta a ejecutar",
        examples=["crm_lookup", "knowledge_search"],
    )
    
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Parámetros para la herramienta",
    )
    
    reasoning: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Por qué el agente necesita esta herramienta",
    )
    
    @field_validator("tool_name")
    @classmethod
    def validate_tool_name(cls, v: str) -> str:
        """Solo permite nombres de herramientas válidos."""
        import re
        if not re.match(r'^[a-z][a-z0-9_]*$', v):
            raise ValueError(
                f"Nombre de herramienta inválido: {v}. "
                f"Debe ser snake_case (ej: crm_lookup)"
            )
        return v


class ToolResult(BaseModel):
    """Resultado de la ejecución de una herramienta."""
    
    tool_name: str = Field(..., description="Herramienta ejecutada")
    success: bool = Field(..., description="Si la ejecución fue exitosa")
    data: Any = Field(default=None, description="Datos devueltos")
    error: Optional[str] = Field(default=None, description="Mensaje de error si falló")
    execution_time_ms: float = Field(..., ge=0, description="Tiempo de ejecución en ms")


# =============================================================================
# MODELO PRINCIPAL DE DECISIÓN
# =============================================================================

class Decision(BaseModel):
    """
    Estructura determinista de salida del agente.
    
    Este es EL contrato central del sistema. Cada iteración del bucle
    del agente produce una Decision que el orquestador procesa.
    
    Garantías:
    - Todos los campos tienen tipos estrictos
    - Los enums limitan los valores posibles
    - Los validadores detectan inconsistencias
    
    Example:
        >>> decision = Decision(
        ...     decision_type=DecisionType.RESPONSE,
        ...     content="Su pedido #12345 está en camino.",
        ...     confidence=ConfidenceLevel.HIGH,
        ...     reasoning="Encontré el pedido en el CRM y tiene estado 'enviado'."
        ... )
    """
    
    # -------------------------------------------------------------------------
    # Campos principales
    # -------------------------------------------------------------------------
    decision_type: DecisionType = Field(
        ...,
        description="Tipo de decisión tomada",
    )
    
    content: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="Contenido principal (respuesta, pregunta, etc.)",
    )
    
    confidence: ConfidenceLevel = Field(
        default=ConfidenceLevel.MEDIUM,
        description="Nivel de confianza en la decisión",
    )
    
    reasoning: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Explicación del razonamiento (para auditoría)",
    )
    
    # -------------------------------------------------------------------------
    # Campos opcionales según tipo de decisión
    # -------------------------------------------------------------------------
    tool_call: Optional[ToolCall] = Field(
        default=None,
        description="Herramienta a ejecutar (si decision_type=TOOL_CALL)",
    )
    
    escalation_reason: Optional[EscalationReason] = Field(
        default=None,
        description="Razón de escalación (si decision_type=ESCALATE)",
    )
    
    suggested_actions: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Acciones sugeridas para seguimiento",
    )
    
    # -------------------------------------------------------------------------
    # Metadatos
    # -------------------------------------------------------------------------
    iteration: int = Field(
        default=0,
        ge=0,
        description="Número de iteración en el bucle del agente",
    )
    
    created_at: datetime = Field(
        default_factory=datetime.now(timezone.utc),
        description="Timestamp de creación",
    )
    
    # -------------------------------------------------------------------------
    # Validadores de consistencia
    # -------------------------------------------------------------------------
    @model_validator(mode="after")
    def validate_consistency(self) -> "Decision":
        """
        Valida que los campos opcionales sean consistentes con el tipo de decisión.
        
        Esto es CRÍTICO: detecta cuando el LLM alucina combinaciones inválidas.
        """
        # Si es TOOL_CALL, debe tener tool_call
        if self.decision_type == DecisionType.TOOL_CALL and self.tool_call is None:
            raise ValueError(
                "decision_type es TOOL_CALL pero no se proporcionó tool_call"
            )
        
        # Si es ESCALATE, debe tener escalation_reason
        if self.decision_type == DecisionType.ESCALATE and self.escalation_reason is None:
            raise ValueError(
                "decision_type es ESCALATE pero no se proporcionó escalation_reason"
            )
        
        # Si NO es TOOL_CALL, no debería tener tool_call
        if self.decision_type != DecisionType.TOOL_CALL and self.tool_call is not None:
            raise ValueError(
                f"decision_type es {self.decision_type} pero se proporcionó tool_call. "
                f"Solo TOOL_CALL puede tener tool_call."
            )
        
        return self
    
    # -------------------------------------------------------------------------
    # Métodos de utilidad
    # -------------------------------------------------------------------------
    def is_terminal(self) -> bool:
        """Indica si esta decisión termina el bucle del agente."""
        return self.decision_type in {
            DecisionType.RESPONSE,
            DecisionType.ESCALATE,
            DecisionType.COMPLETE,
            DecisionType.ERROR,
        }
    
    def requires_user_input(self) -> bool:
        """Indica si esta decisión requiere input del usuario."""
        return self.decision_type == DecisionType.CLARIFY
    
    def to_audit_dict(self) -> dict:
        """Convierte a diccionario para logging de auditoría."""
        return {
            "decision_type": self.decision_type.value,
            "confidence": self.confidence.value,
            "reasoning": self.reasoning,
            "content_length": len(self.content),
            "has_tool_call": self.tool_call is not None,
            "escalation_reason": self.escalation_reason.value if self.escalation_reason else None,
            "iteration": self.iteration,
            "created_at": self.created_at.isoformat(),
        }


# =============================================================================
# RESPONSE FINAL DEL AGENTE
# =============================================================================

class AgentResponse(BaseModel):
    """
    Respuesta completa del agente tras procesar una request.
    
    Incluye la decisión final más métricas de ejecución para auditoría.
    """
    
    # -------------------------------------------------------------------------
    # Resultado
    # -------------------------------------------------------------------------
    success: bool = Field(
        ...,
        description="Si el procesamiento fue exitoso",
    )
    
    decision: Decision = Field(
        ...,
        description="Decisión final del agente",
    )
    
    # -------------------------------------------------------------------------
    # Trazabilidad
    # -------------------------------------------------------------------------
    request_id: str = Field(
        ...,
        description="ID de la request original",
    )
    
    session_id: str = Field(
        ...,
        description="ID de sesión del agente",
    )
    
    # -------------------------------------------------------------------------
    # Métricas de ejecución
    # -------------------------------------------------------------------------
    total_iterations: int = Field(
        ...,
        ge=0,
        description="Iteraciones totales del bucle",
    )
    
    total_tokens_input: int = Field(
        ...,
        ge=0,
        description="Tokens de entrada consumidos",
    )
    
    total_tokens_output: int = Field(
        ...,
        ge=0,
        description="Tokens de salida generados",
    )
    
    total_cost_usd: float = Field(
        ...,
        ge=0,
        description="Coste total en USD",
    )
    
    total_cost_eur: float = Field(
        ...,
        ge=0,
        description="Coste total en EUR",
    )
    
    execution_time_ms: float = Field(
        ...,
        ge=0,
        description="Tiempo total de ejecución en ms",
    )
    
    # -------------------------------------------------------------------------
    # Historial de herramientas
    # -------------------------------------------------------------------------
    tool_calls: list[ToolResult] = Field(
        default_factory=list,
        description="Historial de herramientas ejecutadas",
    )
    
    # -------------------------------------------------------------------------
    # Metadatos
    # -------------------------------------------------------------------------
    created_at: datetime = Field(
        default_factory=datetime.now(timezone.utc),
        description="Timestamp de creación",
    )
    
    budget_remaining_eur: float = Field(
        ...,
        ge=0,
        description="Presupuesto restante en EUR",
    )
    
    stopped_reason: Optional[str] = Field(
        default=None,
        description="Razón de parada si no fue normal (budget, max_iterations, etc.)",
    )