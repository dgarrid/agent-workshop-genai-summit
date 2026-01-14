"""
Sistema de Auditoría para el agente.

Este módulo proporciona logging estructurado para:
- Trazabilidad completa de cada decisión del agente
- Métricas de coste en tiempo real
- Cumplimiento normativo (quién hizo qué, cuándo, por qué)

Principio: Si no está logueado, no pasó.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.decision import Decision
from contextlib import contextmanager
import time

import structlog
import logging
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import box

from src.config import get_settings


# =============================================================================
# CONFIGURACIÓN DE STRUCTLOG
# =============================================================================

def configure_logging() -> None:
    """
    Configura structlog para logging estructurado.
    
    Los logs se emiten en formato JSON para fácil parsing en producción,
    y en formato legible para desarrollo.
    """
    settings = get_settings()
    
    # Determinar si estamos en modo desarrollo (TTY) o producción
    is_dev = sys.stdout.isatty()
    
    if is_dev:
        # Desarrollo: logs bonitos en consola
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # Producción: JSON para sistemas de logging
        renderer = structlog.processors.JSONRenderer()
    
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level, logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


# =============================================================================
# AUDIT LOGGER
# =============================================================================

class AuditLogger:
    """
    Logger de auditoría para el agente.
    
    Registra cada acción con:
    - Timestamp preciso
    - ID de sesión para correlación
    - Métricas de coste acumuladas
    - Contexto completo de la decisión
    
    Example:
        >>> audit = AuditLogger(session_id="sess_123")
        >>> audit.log_iteration_start(iteration=1)
        >>> audit.log_llm_call(input_tokens=150, output_tokens=50, cost_usd=0.001)
        >>> audit.log_decision(decision)
        >>> audit.log_session_end()
    """
    
    def __init__(
        self,
        session_id: str,
        request_id: str,
        persist_to_file: bool = True,
    ):
        self.session_id = session_id
        self.request_id = request_id
        self.persist_to_file = persist_to_file
        
        # Métricas acumuladas
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost_usd = 0.0
        self.iteration_count = 0
        self.tool_calls: list[dict] = []
        
        # Timestamps
        self.session_start = datetime.now(timezone.utc)
        self.session_end: Optional[datetime] = None
        
        # Logger estructurado
        self.log = structlog.get_logger().bind(
            session_id=session_id,
            request_id=request_id,
        )
        
        # Consola Rich para output visual
        self.console = Console()
        
        # Archivo de auditoría
        self.audit_file: Optional[Path] = None
        if persist_to_file:
            self._init_audit_file()
    
    def _init_audit_file(self) -> None:
        """Inicializa el archivo de auditoría."""
        settings = get_settings()
        audit_dir = settings.audit_log_path
        audit_dir.mkdir(parents=True, exist_ok=True)
        
        # Nombre: session_id + timestamp
        filename = f"{self.session_id}_{self.session_start.strftime('%Y%m%d_%H%M%S')}.jsonl"
        self.audit_file = audit_dir / filename
    
    def _persist_event(self, event: dict) -> None:
        """Persiste un evento al archivo de auditoría (JSON Lines)."""
        if self.audit_file:
            with open(self.audit_file, "a") as f:
                f.write(json.dumps(event, default=str) + "\n")

    def _emit(self, level: str, event_name: str, event: dict, **extra) -> None:
        """Emitir evento al logger structlog evitando duplicar la clave 'event'.

        structlog usa el primer argumento posicional como `event`, por lo que si
        `event` también está presente en `event` dict como clave, se produce
        "multiple values for argument 'event'". Eliminamos esa clave antes de
        pasar kwargs al logger.
        """
        kwargs = {k: v for k, v in event.items() if k != "event"}
        # merge extra kwargs if any
        kwargs.update(extra)
        log_method = getattr(self.log, level)
        log_method(event_name, **kwargs)
    
    # -------------------------------------------------------------------------
    # Eventos de Sesión
    # -------------------------------------------------------------------------
    def log_session_start(self, request_content: str, channel: str) -> None:
        """Registra el inicio de una sesión."""
        settings = get_settings()
        
        event = {
            "event": "session_start",
            "timestamp": datetime.now(timezone.utc),
            "session_id": self.session_id,
            "request_id": self.request_id,
            "channel": channel,
            "content_length": len(request_content),
            "model": settings.anthropic_model,
            "budget_limit_eur": settings.budget_limit_eur,
            "max_iterations": settings.max_iterations,
        }
        
        self._emit("info", "session_started", event)
        self._persist_event(event)
        
        # Visual output
        self.console.print(Panel(
            f"[bold green]Sesión iniciada[/bold green]\n"
            f"ID: {self.session_id}\n"
            f"Modelo: {settings.anthropic_model}\n"
            f"Presupuesto: €{settings.budget_limit_eur:.2f}",
            title="Agent",
            box=box.ROUNDED,
        ))
    
    def log_session_end(self, reason: str = "completed") -> None:
        """Registra el fin de una sesión."""
        self.session_end = datetime.now(timezone.utc)
        duration_ms = (self.session_end - self.session_start).total_seconds() * 1000
        
        settings = get_settings()
        cost_eur = self.total_cost_usd / settings.eur_usd_rate
        
        event = {
            "event": "session_end",
            "timestamp": self.session_end.isoformat(),
            "session_id": self.session_id,
            "reason": reason,
            "total_iterations": self.iteration_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_cost_eur": round(cost_eur, 6),
            "duration_ms": round(duration_ms, 2),
            "tool_calls_count": len(self.tool_calls),
        }
        
        self._emit("info", "session_ended", event)
        self._persist_event(event)
        
        # Resumen visual
        self._print_session_summary(reason, duration_ms, cost_eur)
    
    def _print_session_summary(self, reason: str, duration_ms: float, cost_eur: float) -> None:
        """Imprime resumen visual de la sesión."""
        table = Table(title="Resumen de Sesión", box=box.ROUNDED)
        table.add_column("Métrica", style="cyan")
        table.add_column("Valor", style="green")
        
        table.add_row("Razón de fin", reason)
        table.add_row("Iteraciones", str(self.iteration_count))
        table.add_row("Tokens entrada", f"{self.total_input_tokens:,}")
        table.add_row("Tokens salida", f"{self.total_output_tokens:,}")
        table.add_row("Coste USD", f"${self.total_cost_usd:.4f}")
        table.add_row("Coste EUR", f"€{cost_eur:.4f}")
        table.add_row("Duración", f"{duration_ms:.0f}ms")
        table.add_row("Tools ejecutadas", str(len(self.tool_calls)))
        
        if self.audit_file:
            table.add_row("Archivo audit", str(self.audit_file))
        
        self.console.print(table)
    
    # -------------------------------------------------------------------------
    # Eventos de Iteración
    # -------------------------------------------------------------------------
    def log_iteration_start(self, iteration: int) -> None:
        """Registra el inicio de una iteración."""
        self.iteration_count = iteration
        
        event = {
            "event": "iteration_start",
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": self.session_id,
            "iteration": iteration,
        }
        
        self.log.debug("iteration_started", iteration=iteration)
        self._persist_event(event)
        
        self.console.print(f"\n[dim]─── Iteración {iteration} ───[/dim]")
    
    def log_llm_call(
        self,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        latency_ms: float,
    ) -> None:
        """Registra una llamada al LLM."""
        # Acumular métricas
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost_usd += cost_usd
        
        settings = get_settings()
        cost_eur = cost_usd / settings.eur_usd_rate
        budget_remaining = settings.budget_limit_eur - (self.total_cost_usd / settings.eur_usd_rate)
        
        event = {
            "event": "llm_call",
            "timestamp": datetime.now(timezone.utc),
            "session_id": self.session_id,
            "iteration": self.iteration_count,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost_usd, 6),
            "cost_eur": round(cost_eur, 6),
            "latency_ms": round(latency_ms, 2),
            "cumulative_cost_usd": round(self.total_cost_usd, 6),
            "budget_remaining_eur": round(budget_remaining, 6),
            # NUEVO: buckets para agregación en dashboards
            "cost_bucket": self._get_cost_bucket(cost_eur),
            "latency_bucket": self._get_latency_bucket(latency_ms),        
        }
        
        self._emit("info", "llm_call", event)
        self._persist_event(event)
        
        # Visual: barra de presupuesto
        budget_pct = (self.total_cost_usd / settings.eur_usd_rate) / settings.budget_limit_eur * 100
        bar_color = "green" if budget_pct < 50 else "yellow" if budget_pct < 80 else "red"
        
        self.console.print(
            f"  💰 Coste: €{cost_eur:.4f} | "
            f"Acumulado: €{self.total_cost_usd / settings.eur_usd_rate:.4f} | "
            f"[{bar_color}]Presupuesto: {budget_pct:.1f}%[/{bar_color}] | "
            f"⏱️ {latency_ms:.0f}ms"
        )
    
    # -------------------------------------------------------------------------
    # Eventos de Decisión
    # -------------------------------------------------------------------------
    def log_decision(self, decision: "Decision") -> None:
        """Registra una decisión del agente."""
        
        event = {
            "event": "decision",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "iteration": self.iteration_count,
            **decision.to_audit_dict(),
        }
        
        self._emit("info", "decision_made", event)
        self._persist_event(event)
        
        # Visual
        icon = {
            "response": "💬",
            "tool_call": "🔧",
            "escalate": "🚨",
            "clarify": "❓",
            "complete": "✅",
            "error": "❌",
        }.get(decision.decision_type.value, "❔")
        
        self.console.print(
            f"  {icon} Decisión: [bold]{decision.decision_type.value}[/bold] | "
            f"Confianza: {decision.confidence.value}"
        )
    
    # -------------------------------------------------------------------------
    # Eventos de Tools
    # -------------------------------------------------------------------------
    def log_tool_call(
        self,
        tool_name: str,
        parameters: dict,
        success: bool,
        result: Any,
        execution_time_ms: float,
        error: Optional[str] = None,
    ) -> None:
        """Registra la ejecución de una herramienta."""
        tool_record = {
            "tool_name": tool_name,
            "parameters": parameters,
            "success": success,
            "execution_time_ms": execution_time_ms,
            "error": error,
        }
        self.tool_calls.append(tool_record)
        
        event = {
            "event": "tool_call",
            "timestamp": datetime.now(timezone.utc),
            "session_id": self.session_id,
            "iteration": self.iteration_count,
            **tool_record,
        }
        
        level = "info" if success else "warning"
        self._emit(level, "tool_executed", event)
        self._persist_event(event)
        
        # Visual
        status = "[green]✓[/green]" if success else "[red]✗[/red]"
        self.console.print(
            f"  🔧 Tool: {tool_name} {status} | ⏱️ {execution_time_ms:.0f}ms"
        )
    
    # -------------------------------------------------------------------------
    # Eventos de Error y Budget
    # -------------------------------------------------------------------------
    def log_budget_exceeded(self, current_cost_eur: float, limit_eur: float) -> None:
        """Registra que se excedió el presupuesto."""
        event = {
            "event": "budget_exceeded",
            "timestamp": datetime.now(timezone.utc),
            "session_id": self.session_id,
            "iteration": self.iteration_count,
            "current_cost_eur": round(current_cost_eur, 6),
            "limit_eur": limit_eur,
        }
        
        self._emit("warning", "budget_exceeded", event)
        self._persist_event(event)
        
        self.console.print(Panel(
            f"[bold red]⚠️ PRESUPUESTO EXCEDIDO[/bold red]\n"
            f"Coste actual: €{current_cost_eur:.4f}\n"
            f"Límite: €{limit_eur:.2f}",
            title="💸 Budget Limiter",
            box=box.HEAVY,
            border_style="red",
        ))
    
# -----------------------------------------------------------------------------
# 3. BUCKETS PARA MÉTRICAS (opcional, útil para dashboards)
#    Añadir categorización de costes y latencias para facilitar agregaciones 
    
    @staticmethod
    def _get_cost_bucket(cost_eur: float) -> str:
        """Categoriza el coste para dashboards."""
        if cost_eur < 0.001:
            return "micro"      # < €0.001
        elif cost_eur < 0.01:
            return "small"      # €0.001 - €0.01
        elif cost_eur < 0.1:
            return "medium"     # €0.01 - €0.1
        else:
            return "large"      # > €0.1
    
    @staticmethod
    def _get_latency_bucket(latency_ms: float) -> str:
        """Categoriza la latencia para dashboards."""
        if latency_ms < 500:
            return "fast"       # < 500ms
        elif latency_ms < 2000:
            return "normal"     # 500ms - 2s
        elif latency_ms < 5000:
            return "slow"       # 2s - 5s
        else:
            return "very_slow"  # > 5s
    def log_max_iterations_reached(self, max_iterations: int) -> None:
        """Registra que se alcanzó el máximo de iteraciones."""
        event = {
            "event": "max_iterations_reached",
            "timestamp": datetime.now(timezone.utc),
            "session_id": self.session_id,
            "iteration": self.iteration_count,
            "max_iterations": max_iterations,
        }
        
        self._emit("warning", "max_iterations_reached", event)
        self._persist_event(event)
        
        self.console.print(Panel(
            f"[bold yellow]⚠️ MÁXIMO DE ITERACIONES[/bold yellow]\n"
            f"Iteración actual: {self.iteration_count}\n"
            f"Límite: {max_iterations}",
            title="🔄 Loop Protection",
            box=box.HEAVY,
            border_style="yellow",
        ))
    
    def log_error(self, error: Exception, context: str = "") -> None:
        """Registra un error."""
        event = {
            "event": "error",
            "timestamp": datetime.now(timezone.utc),
            "session_id": self.session_id,
            "iteration": self.iteration_count,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context,
        }
        
        self._emit("error", "error_occurred", event, exc_info=True)
        self._persist_event(event)
        
        self.console.print(Panel(
            f"[bold red]❌ ERROR[/bold red]\n"
            f"Tipo: {type(error).__name__}\n"
            f"Mensaje: {str(error)}\n"
            f"Contexto: {context}",
            title="Error",
            box=box.HEAVY,
            border_style="red",
        ))
    
    # =============================================================================
# AÑADIR ESTE MÉTODO A LA CLASE AuditLogger
# (después de log_error, antes del cierre de la clase)
# =============================================================================

def log_event(self, event_type: str, data: dict) -> None:
    """
    Registra un evento genérico.
    
    Útil para eventos personalizados como alertas de budget,
    métricas custom, o cualquier evento no cubierto por los
    métodos específicos.
    
    Args:
        event_type: Tipo de evento (ej: "budget_warning", "custom_metric")
        data: Datos adicionales del evento
        
    Example:
        >>> audit.log_event("budget_warning", {
        ...     "threshold": "50%",
        ...     "current_cost_eur": 2.50,
        ...     "limit_eur": 5.00,
        ... })
    """
    event = {
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": self.session_id,
        "iteration": self.iteration_count,
        **data,
    }
    
    # Determinar nivel de log según tipo de evento
    if "warning" in event_type.lower() or "alert" in event_type.lower():
        level = "warning"
    elif "error" in event_type.lower() or "critical" in event_type.lower():
        level = "error"
    else:
        level = "info"
    
    self._emit(level, event_type, event)
    self._persist_event(event)
    
    # Visual output según tipo
    if "budget" in event_type.lower():
        threshold = data.get("threshold", "N/A")
        current = data.get("current_cost_eur", 0)
        limit = data.get("limit_eur", 0)
        
        if "critical" in event_type.lower() or "80" in str(threshold):
            style = "bold red"
            icon = "🔴"
        elif "warning" in event_type.lower() or "50" in str(threshold):
            style = "bold yellow"
            icon = "🟡"
        else:
            style = "bold cyan"
            icon = "🔵"
        
        self.console.print(
            f"  {icon} [{style}]Budget Alert ({threshold})[/{style}]: "
            f"€{current:.4f} / €{limit:.2f}"
        )
    else:
        # Evento genérico
        self.console.print(f"  📌 Event: {event_type}")



# =============================================================================
# CONTEXT MANAGER PARA TIMING
# =============================================================================

@contextmanager
def timed_operation(operation_name: str, console: Optional[Console] = None):
    """
    Context manager para medir tiempo de operaciones.
    
    Example:
        >>> with timed_operation("llm_call") as timer:
        ...     response = client.messages.create(...)
        >>> print(f"Took {timer.elapsed_ms}ms")
    """
    class Timer:
        def __init__(self):
            self.start_time = time.perf_counter()
            self.elapsed_ms = 0.0
    
    timer = Timer()
    
    try:
        yield timer
    finally:
        timer.elapsed_ms = (time.perf_counter() - timer.start_time) * 1000


# Inicializar logging al importar
configure_logging()