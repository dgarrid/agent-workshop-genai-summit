"""
Contratos de entrada para el agente.

Este módulo define los esquemas Pydantic que validan y sanitizan
TODA la información que entra al sistema, ya sea desde:
- Emails simulados
- Webhooks
- API REST
- CLI

Principio: Si no pasa validación, no entra al agente.
"""

import re
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator


# =============================================================================
# ENUMS
# =============================================================================

class InputChannel(str, Enum):
    """Canales de entrada soportados."""
    EMAIL = "email"
    WEBHOOK = "webhook"
    API = "api"
    CLI = "cli"


class Priority(str, Enum):
    """Niveles de prioridad para el procesamiento."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


# =============================================================================
# MODELOS DE ENTRADA
# =============================================================================

class EmailInput(BaseModel):
    """
    Representa un email entrante al sistema.
    
    Valida y sanitiza:
    - Formato de email del remitente
    - Longitud máxima de asunto y cuerpo
    - Caracteres peligrosos (inyección)
    
    Example:
        >>> email = EmailInput(
        ...     sender="cliente@empresa.com",
        ...     subject="Consulta sobre mi pedido",
        ...     body="Hola, quisiera saber el estado de mi pedido #12345"
        ... )
    """
    
    sender: str = Field(
        ...,
        min_length=5,
        max_length=254,
        description="Dirección de email del remitente",
        examples=["cliente@empresa.com"],
    )
    
    subject: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Asunto del email",
        examples=["Consulta sobre mi pedido"],
    )
    
    body: str = Field(
        ...,
        min_length=1,
        max_length=50_000,  # ~10 páginas de texto
        description="Cuerpo del email",
    )
    
    received_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp de recepción (UTC)",
    )
    
    priority: Priority = Field(
        default=Priority.NORMAL,
        description="Prioridad asignada",
    )
    
    # -------------------------------------------------------------------------
    # Validadores
    # -------------------------------------------------------------------------
    @field_validator("sender")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        """Valida formato básico de email."""
        # Regex simple pero efectivo para emails
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(pattern, v.strip()):
            raise ValueError(f"Formato de email inválido: {v}")
        return v.strip().lower()
    
    @field_validator("subject", "body")
    @classmethod
    def sanitize_text(cls, v: str) -> str:
        """
        Sanitiza texto para prevenir inyecciones.
        
        Elimina:
        - Caracteres de control (excepto newlines)
        - Secuencias de escape peligrosas
        """
        # Eliminar caracteres de control excepto \n y \t
        sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', v)
        
        # Normalizar espacios múltiples
        sanitized = re.sub(r' +', ' ', sanitized)
        
        # Normalizar saltos de línea múltiples (máx 2 consecutivos)
        sanitized = re.sub(r'\n{3,}', '\n\n', sanitized)
        
        return sanitized.strip()
    
    @field_validator("body")
    @classmethod
    def detect_path_traversal(cls, v: str) -> str:
        """
        Detecta intentos de path traversal en el contenido.
        
        Esto es crítico para el workshop: demuestra defensa en profundidad.
        """
        dangerous_patterns = [
            r'\.\./',           # ../
            r'\.\.\\',          # ..\
            r'/etc/',           # /etc/passwd, etc.
            r'\\windows\\',     # \windows\
            r'%2e%2e',          # URL encoded ..
            r'%252e%252e',      # Double URL encoded
        ]
        
        v_lower = v.lower()
        for pattern in dangerous_patterns:
            if re.search(pattern, v_lower):
                raise ValueError(
                    f"Contenido bloqueado: patrón de path traversal detectado. "
                    f"Esto podría ser un intento de acceso no autorizado."
                )
        
        return v


class WebhookInput(BaseModel):
    """
    Representa un webhook entrante (ej: desde CRM, Slack, etc.).
    
    Más estructurado que un email, con metadatos del sistema origen.
    """
    
    source_system: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Sistema que envía el webhook",
        examples=["salesforce", "hubspot", "slack"],
    )
    
    event_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Tipo de evento",
        examples=["ticket.created", "lead.updated"],
    )
    
    payload: dict = Field(
        ...,
        description="Datos del evento",
    )
    
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp del evento (UTC)",
    )
    
    correlation_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="ID para correlación de eventos",
    )
    
    @field_validator("source_system", "event_type")
    @classmethod
    def sanitize_identifiers(cls, v: str) -> str:
        """Solo permite caracteres seguros en identificadores."""
        sanitized = re.sub(r'[^a-zA-Z0-9._-]', '', v)
        if sanitized != v:
            raise ValueError(
                f"Identificador contiene caracteres no permitidos: {v}"
            )
        return sanitized.lower()


class CLIInput(BaseModel):
    """
    Entrada desde la interfaz de línea de comandos.
    
    Más permisiva que email/webhook pero con límites.
    """
    
    message: str = Field(
        ...,
        min_length=1,
        max_length=100_000,
        description="Mensaje del usuario",
    )
    
    session_id: Optional[str] = Field(
        default=None,
        max_length=50,
        description="ID de sesión para continuidad",
    )
    
    @field_validator("message")
    @classmethod
    def sanitize_cli_input(cls, v: str) -> str:
        """Sanitización básica para CLI."""
        # Eliminar caracteres de control
        sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', v)
        return sanitized.strip()


# =============================================================================
# MODELO UNIFICADO DE REQUEST
# =============================================================================

class AgentRequest(BaseModel):
    """
    Request unificado que envuelve cualquier tipo de entrada.
    
    Este es el contrato que recibe el orquestador, independientemente
    del canal de origen.
    
    Example:
        >>> request = AgentRequest(
        ...     channel=InputChannel.EMAIL,
        ...     content="¿Cuál es el estado de mi pedido #12345?",
        ...     metadata={"sender": "cliente@empresa.com", "subject": "Consulta"}
        ... )
    """
    
    channel: InputChannel = Field(
        ...,
        description="Canal de origen de la request",
    )
    
    content: str = Field(
        ...,
        min_length=1,
        max_length=100_000,
        description="Contenido principal (ya sanitizado)",
    )
    
    metadata: dict = Field(
        default_factory=dict,
        description="Metadatos adicionales del canal",
    )
    
    priority: Priority = Field(
        default=Priority.NORMAL,
        description="Prioridad de procesamiento",
    )
    
    request_id: str = Field(
        default_factory=lambda: datetime.utcnow().strftime("%Y%m%d%H%M%S%f"),
        description="ID único de la request",
    )
    
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp de creación",
    )
    
    @classmethod
    def from_email(cls, email: EmailInput) -> "AgentRequest":
        """Factory method para crear request desde email."""
        # Combinar subject y body como contenido
        content = f"Asunto: {email.subject}\n\n{email.body}"
        
        return cls(
            channel=InputChannel.EMAIL,
            content=content,
            metadata={
                "sender": email.sender,
                "subject": email.subject,
                "received_at": email.received_at.isoformat(),
            },
            priority=email.priority,
        )
    
    @classmethod
    def from_webhook(cls, webhook: WebhookInput) -> "AgentRequest":
        """Factory method para crear request desde webhook."""
        import json
        content = f"Evento: {webhook.event_type}\n\nDatos:\n{json.dumps(webhook.payload, indent=2)}"
        
        return cls(
            channel=InputChannel.WEBHOOK,
            content=content,
            metadata={
                "source_system": webhook.source_system,
                "event_type": webhook.event_type,
                "correlation_id": webhook.correlation_id,
            },
        )
    
    @classmethod
    def from_cli(cls, cli: CLIInput) -> "AgentRequest":
        """Factory method para crear request desde CLI."""
        return cls(
            channel=InputChannel.CLI,
            content=cli.message,
            metadata={
                "session_id": cli.session_id,
            },
        )