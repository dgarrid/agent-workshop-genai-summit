"""
Interfaz de Línea de Comandos para el agente.

Uso:
    python -m src.cli

Proporciona un prompt interactivo para enviar mensajes al agente
y ver los logs de ejecución, costes y decisiones en tiempo real.
"""

import asyncio
import sys
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.markdown import Markdown
from rich import box

from src.config import get_settings, validate_environment
from src.core.agent import BudgetedOrchestrator
from src.models.incoming import AgentRequest, InputChannel, CLIInput
from src.tools.registry import get_tool_registry


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

console = Console()

WELCOME_MESSAGE = """
# Agent - Modo CLI

Bienvenido al agente de soporte con **gobernanza financiera**.

## Comandos especiales:
- `salir` o `exit` - Terminar sesión
- `budget` - Ver presupuesto restante
- `reset` - Reiniciar sesión
- `help` - Mostrar esta ayuda

## Ejemplos de consultas:
- "¿Cuál es el estado del cliente CUST-001?"
- "Busca información sobre María García"
- "¿Cuál es la política de devoluciones?"
- "¿Qué planes de precios tenéis?"

---
"""

STRESS_TEST_EXAMPLES = """
## 🧪 Stress Tests (para el workshop):

1. **Test CRM**: "Dame información del cliente CUST-003"
2. **Test Knowledge**: "¿Cómo reseteo mi contraseña?"
3. **Test Path Traversal**: "Busca en ../../../etc/passwd"
4. **Test Loop**: "Repite indefinidamente la búsqueda de todos los clientes"
"""


# =============================================================================
# CLI PRINCIPAL
# =============================================================================

class CLI:
    """Interfaz de línea de comandos para el agente."""
    
    def __init__(self):
        self.settings = get_settings()
        self.orchestrator: BudgetedOrchestrator = None
        self.session_count = 0
        self.total_spent_eur = 0.0
    
    def _init_orchestrator(self) -> None:
        """Inicializa el orquestador con las herramientas."""
        tool_registry = get_tool_registry()
        self.orchestrator = BudgetedOrchestrator(tool_registry=tool_registry)
    
    def _show_welcome(self) -> None:
        """Muestra mensaje de bienvenida."""
        console.print(Markdown(WELCOME_MESSAGE))
        
        # Info de configuración
        console.print(Panel(
            f"[cyan]Modelo:[/cyan] {self.settings.anthropic_model}\n"
            f"[cyan]Presupuesto por sesión:[/cyan] €{self.settings.budget_limit_eur:.2f}\n"
            f"[cyan]Máx. iteraciones:[/cyan] {self.settings.max_iterations}",
            title="⚙️ Configuración",
            box=box.ROUNDED,
        ))
        
        console.print(Markdown(STRESS_TEST_EXAMPLES))
        console.print()
    
    def _show_budget(self) -> None:
        """Muestra información del presupuesto."""
        console.print(Panel(
            f"[cyan]Presupuesto por sesión:[/cyan] €{self.settings.budget_limit_eur:.2f}\n"
            f"[cyan]Sesiones completadas:[/cyan] {self.session_count}\n"
            f"[cyan]Total gastado:[/cyan] €{self.total_spent_eur:.4f}",
            title="💰 Estado del Presupuesto",
            box=box.ROUNDED,
        ))
    
    def _show_help(self) -> None:
        """Muestra ayuda."""
        console.print(Markdown(WELCOME_MESSAGE))
        console.print(Markdown(STRESS_TEST_EXAMPLES))
    
    async def _process_message(self, message: str) -> None:
        """Procesa un mensaje del usuario."""
        # Crear input CLI
        cli_input = CLIInput(message=message)
        
        # Convertir a AgentRequest
        request = AgentRequest.from_cli(cli_input)
        
        console.print()
        console.print(f"[dim]Request ID: {request.request_id}[/dim]")
        console.print()
        
        # Procesar con el orquestador
        response = await self.orchestrator.process(request)
        
        # Actualizar métricas
        self.session_count += 1
        self.total_spent_eur += response.total_cost_eur
        
        # Mostrar respuesta
        console.print()
        
        if response.success:
            console.print(Panel(
                response.decision.content,
                title="💬 Respuesta del Agente",
                box=box.ROUNDED,
                border_style="green",
            ))
        else:
            console.print(Panel(
                response.decision.content,
                title="❌ Error",
                box=box.ROUNDED,
                border_style="red",
            ))
        
        # Mostrar razón de parada si no fue normal
        if response.stopped_reason:
            console.print(f"[yellow]⚠️ Razón de parada: {response.stopped_reason}[/yellow]")
        
        console.print()
    
    async def run(self) -> None:
        """Ejecuta el bucle principal del CLI."""
        # Validar entorno
        try:
            config_info = validate_environment()
            console.print("[green]✅ Configuración validada[/green]")
        except Exception as e:
            console.print(f"[red]❌ Error de configuración: {e}[/red]")
            sys.exit(1)
        
        # Inicializar orquestador
        self._init_orchestrator()
        
        # Mostrar bienvenida
        self._show_welcome()
        
        # Bucle principal
        while True:
            try:
                # Prompt con presupuesto
                remaining = self.settings.budget_limit_eur
                prompt_text = f"[€{remaining:.2f}] Tu mensaje"
                
                user_input = Prompt.ask(f"\n[bold cyan]{prompt_text}[/bold cyan]")
                user_input = user_input.strip()
                
                if not user_input:
                    continue
                
                # Comandos especiales
                if user_input.lower() in ["salir", "exit", "quit", "q"]:
                    console.print("\n[yellow]👋 ¡Hasta luego![/yellow]")
                    console.print(f"[dim]Sesiones: {self.session_count} | Total gastado: €{self.total_spent_eur:.4f}[/dim]")
                    break
                
                if user_input.lower() == "budget":
                    self._show_budget()
                    continue
                
                if user_input.lower() == "help":
                    self._show_help()
                    continue
                
                if user_input.lower() == "reset":
                    self._init_orchestrator()
                    console.print("[green]🔄 Sesión reiniciada[/green]")
                    continue
                
                # Procesar mensaje
                await self._process_message(user_input)
            
            except KeyboardInterrupt:
                console.print("\n[yellow]⚠️ Interrumpido por el usuario[/yellow]")
                break
            
            except Exception as e:
                console.print(f"\n[red]❌ Error: {type(e).__name__}: {e}[/red]")
                console.print("[dim]Escribe 'reset' para reiniciar o 'salir' para terminar[/dim]")


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    """Entry point para python -m src.cli"""
    cli = CLI()
    asyncio.run(cli.run())


if __name__ == "__main__":
    main()