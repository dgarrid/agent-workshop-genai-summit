"""
Models module - Contratos de datos Pydantic.

Contiene:
- incoming.py: Validación de entradas (emails, webhooks, CLI)
- decision.py: Estructura determinista de salidas
"""

from src.models.incoming import (
    AgentRequest,
    EmailInput,
    WebhookInput,
    CLIInput,
    InputChannel,
    Priority,
)
from src.models.decision import (
    Decision,
    DecisionType,
    ConfidenceLevel,
    EscalationReason,
    ToolCall,
    ToolResult,
    AgentResponse,
)

__all__ = [
    # Incoming
    "AgentRequest",
    "EmailInput",
    "WebhookInput",
    "CLIInput",
    "InputChannel",
    "Priority",
    # Decision
    "Decision",
    "DecisionType",
    "ConfidenceLevel",
    "EscalationReason",
    "ToolCall",
    "ToolResult",
    "AgentResponse",
]