"""
Core module - El cerebro del agente.

Contiene:
- BudgetedOrchestrator: Bucle de ejecución con control de presupuesto
- AuditLogger: Sistema de logging estructurado
"""

from src.core.agent import BudgetedOrchestrator, BudgetExceededError, MaxIterationsError
from src.core.audit import AuditLogger, configure_logging

__all__ = [
    "BudgetedOrchestrator",
    "BudgetExceededError",
    "MaxIterationsError",
    "AuditLogger",
    "configure_logging",
]