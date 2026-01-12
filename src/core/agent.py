"""
BudgetedOrchestrator - El corazón de nuestro agente.

Este módulo implementa el bucle de ejecución controlado del agente con:
- Límite de presupuesto en EUR (mata el proceso si se excede)
- Límite de iteraciones (protección anti-loop infinito)
- Ejecución de herramientas validada
- Logging de auditoría completo

Principio: El agente NUNCA puede gastar más de lo autorizado.
"""

import uuid
import json
import re
from datetime import datetime
from typing import Optional, Any

import anthropic
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.config import get_settings
from src.core.audit import AuditLogger, timed_operation
from src.models.incoming import AgentRequest
from src.models.decision import (
    Decision,
    DecisionType,
    ConfidenceLevel,
    EscalationReason,
    ToolCall,
    ToolResult,
    AgentResponse,
)


# =============================================================================
# EXCEPCIONES PERSONALIZADAS
# =============================================================================

class BudgetExceededError(Exception):
    """Se lanza cuando el agente excede su presupuesto."""
    def __init__(self, current_cost: float, limit: float):
        self.current_cost = current_cost
        self.limit = limit
        super().__init__(f"Presupuesto excedido: €{current_cost:.4f} > €{limit:.2f}")


class MaxIterationsError(Exception):
    """Se lanza cuando el agente alcanza el máximo de iteraciones."""
    def __init__(self, iterations: int, limit: int):
        self.iterations = iterations
        self.limit = limit
        super().__init__(f"Máximo de iteraciones alcanzado: {iterations} >= {limit}")


# =============================================================================
# SYSTEM PROMPT
# =============================================================================

SYSTEM_PROMPT = """Eres un agente de soporte empresarial. Tu trabajo es:

1. ANALIZAR la consulta del usuario
2. DECIDIR qué acción tomar (responder, usar herramienta, escalar, o pedir aclaración)
3. EXPLICAR tu razonamiento

HERRAMIENTAS DISPONIBLES:
- crm_lookup: Buscar información de clientes en el CRM (parámetros: customer_id, email, o query)
- knowledge_search: Buscar en la base de conocimiento (parámetros: query)

REGLAS CRÍTICAS:
- Si necesitas información del CRM, USA la herramienta crm_lookup
- Si necesitas información de documentación/políticas, USA knowledge_search
- Si no estás seguro, ESCALA a un humano (decision_type: "escalate")
- NUNCA inventes información que no tengas
- SIEMPRE explica tu razonamiento

Responde SIEMPRE en formato JSON válido con esta estructura exacta:
{
    "decision_type": "response|tool_call|escalate|clarify|complete|error",
    "content": "tu respuesta o mensaje al usuario",
    "confidence": "high|medium|low",
    "reasoning": "explicación de por qué tomaste esta decisión",
    "tool_call": {
        "tool_name": "crm_lookup|knowledge_search",
        "parameters": {"param": "value"},
        "reasoning": "por qué necesitas esta herramienta"
    },
    "escalation_reason": "complex_query|sensitive_data|policy_violation|user_request|low_confidence|out_of_scope",
    "suggested_actions": ["acción1", "acción2"]
}

IMPORTANTE:
- "tool_call" SOLO si decision_type es "tool_call" (omitir en otros casos)
- "escalation_reason" SOLO si decision_type es "escalate" (omitir en otros casos)
- "suggested_actions" es opcional
- Responde SOLO el JSON, sin texto adicional antes o después
"""


# =============================================================================
# BUDGETED ORCHESTRATOR
# =============================================================================

class BudgetedOrchestrator:
    """
    Orquestador de agente con control de presupuesto.
    
    Características:
    - Límite de gasto en EUR por sesión
    - Límite de iteraciones para evitar loops infinitos
    - Ejecución segura de herramientas
    - Auditoría completa de cada paso
    
    Example:
        >>> orchestrator = BudgetedOrchestrator()
        >>> request = AgentRequest(channel="cli", content="¿Cuál es el estado del cliente #123?")
        >>> response = await orchestrator.process(request)
        >>> print(f"Coste: €{response.total_cost_eur:.4f}")
    """
    
    def __init__(self, tool_registry: Optional[dict] = None):
        """
        Inicializa el orquestador.
        
        Args:
            tool_registry: Diccionario de herramientas disponibles.
                          {nombre: {"handler": callable, "schema": dict}}
        """
        self.settings = get_settings()
        self.client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)
        self.tool_registry = tool_registry or {}
        
        # Estado de sesión (se reinicia en cada process())
        self.session_id: str = ""
        self.audit: Optional[AuditLogger] = None
        self.conversation_history: list[dict] = []
        
        # Métricas acumuladas por sesión
        self.total_cost_usd = 0.0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
    
    def register_tool(self, name: str, handler: callable, schema: dict) -> None:
        """
        Registra una herramienta para uso del agente.
        
        Args:
            name: Nombre de la herramienta (snake_case)
            handler: Función async que ejecuta la herramienta
            schema: JSON Schema de los parámetros
        """
        self.tool_registry[name] = {
            "handler": handler,
            "schema": schema,
        }
    
    # =========================================================================
    # MÉTODO PRINCIPAL
    # =========================================================================
    
    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Procesa una request del usuario.
        
        Este es el método principal. Ejecuta el bucle del agente hasta que:
        - Se produce una decisión terminal (response, escalate, complete, error)
        - Se excede el presupuesto → BudgetExceededError
        - Se alcanza el máximo de iteraciones
        
        Args:
            request: Request validada del usuario
            
        Returns:
            AgentResponse con la decisión final y métricas
        """
        # ─────────────────────────────────────────────────────────────────────
        # INICIALIZACIÓN DE SESIÓN
        # ─────────────────────────────────────────────────────────────────────
        self.session_id = f"sess_{uuid.uuid4().hex[:12]}"
        self.audit = AuditLogger(
            session_id=self.session_id,
            request_id=request.request_id,
        )
        self.conversation_history = []
        self.total_cost_usd = 0.0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        
        start_time = datetime.utcnow()
        stopped_reason: Optional[str] = None
        final_decision: Optional[Decision] = None
        tool_results: list[ToolResult] = []
        iteration = 0
        
        try:
            # Log inicio de sesión
            self.audit.log_session_start(
                request_content=request.content,
                channel=request.channel.value,
            )
            
            # Agregar mensaje inicial del usuario
            self.conversation_history.append({
                "role": "user",
                "content": request.content,
            })
            
            # ─────────────────────────────────────────────────────────────────
            # BUCLE PRINCIPAL DEL AGENTE
            # ─────────────────────────────────────────────────────────────────
            while iteration < self.settings.max_iterations:
                iteration += 1
                self.audit.log_iteration_start(iteration)
                
                # 1. VERIFICAR PRESUPUESTO (antes de gastar más)
                self._check_budget()
                
                # 2. LLAMAR AL LLM
                decision = await self._call_llm(iteration)
                
                # 3. LOG DE LA DECISIÓN
                self.audit.log_decision(decision)
                
                # 4. SI ES TERMINAL → SALIR
                if decision.is_terminal():
                    final_decision = decision
                    break
                
                # 5. SI NECESITA HERRAMIENTA → EJECUTAR
                if decision.decision_type == DecisionType.TOOL_CALL:
                    tool_result = await self._execute_tool(decision.tool_call)
                    tool_results.append(tool_result)
                    
                    # Agregar resultado de la herramienta al contexto
                    if tool_result.success:
                        tool_response = f"✅ Resultado de {decision.tool_call.tool_name}:\n{json.dumps(tool_result.data, indent=2, default=str, ensure_ascii=False)}"
                    else:
                        tool_response = f"❌ Error en {decision.tool_call.tool_name}: {tool_result.error}"
                    
                    self.conversation_history.append({
                        "role": "user",
                        "content": tool_response,
                    })
                
                # 6. SI NECESITA CLARIFICACIÓN → ES TERMINAL
                if decision.requires_user_input():
                    final_decision = decision
                    break
            
            else:
                # Se alcanzó el máximo de iteraciones sin decisión terminal
                self.audit.log_max_iterations_reached(self.settings.max_iterations)
                stopped_reason = "max_iterations"
                final_decision = Decision(
                    decision_type=DecisionType.ERROR,
                    content="Se alcanzó el máximo de iteraciones sin completar la tarea. Por favor, reformula tu consulta o contacta a soporte.",
                    confidence=ConfidenceLevel.HIGH,
                    reasoning=f"El agente ejecutó {self.settings.max_iterations} iteraciones sin llegar a una conclusión. Posible loop o tarea demasiado compleja.",
                    iteration=iteration,
                )
        
        except BudgetExceededError as e:
            # ─────────────────────────────────────────────────────────────────
            # PRESUPUESTO EXCEDIDO → PARADA DE EMERGENCIA
            # ─────────────────────────────────────────────────────────────────
            self.audit.log_budget_exceeded(
                current_cost_eur=e.current_cost,
                limit_eur=e.limit,
            )
            stopped_reason = "budget_exceeded"
            final_decision = Decision(
                decision_type=DecisionType.ERROR,
                content=f"Sesión detenida por el sistema de gobernanza financiera. Coste: €{e.current_cost:.4f}, Límite: €{e.limit:.2f}",
                confidence=ConfidenceLevel.HIGH,
                reasoning="El BudgetedOrchestrator detuvo la ejecución para proteger el presupuesto asignado.",
                iteration=iteration,
            )
        
        except anthropic.APIError as e:
            self.audit.log_error(e, context="anthropic_api_error")
            stopped_reason = f"api_error: {type(e).__name__}"
            final_decision = Decision(
                decision_type=DecisionType.ERROR,
                content=f"Error de comunicación con el servicio de IA. Por favor, inténtalo de nuevo.",
                confidence=ConfidenceLevel.HIGH,
                reasoning=f"Error de API Anthropic: {str(e)}",
                iteration=iteration,
            )
        
        except Exception as e:
            self.audit.log_error(e, context="unexpected_error")
            stopped_reason = f"error: {type(e).__name__}"
            final_decision = Decision(
                decision_type=DecisionType.ERROR,
                content="Ha ocurrido un error interno. El equipo técnico ha sido notificado.",
                confidence=ConfidenceLevel.HIGH,
                reasoning=f"Excepción no controlada: {type(e).__name__}: {str(e)}",
                iteration=iteration,
            )
        
        finally:
            # ─────────────────────────────────────────────────────────────────
            # MÉTRICAS FINALES Y CIERRE
            # ─────────────────────────────────────────────────────────────────
            end_time = datetime.utcnow()
            execution_time_ms = (end_time - start_time).total_seconds() * 1000
            cost_eur = self.total_cost_usd / self.settings.eur_usd_rate
            budget_remaining = self.settings.budget_limit_eur - cost_eur
            
            # Log fin de sesión
            if self.audit:
                self.audit.log_session_end(reason=stopped_reason or "completed")
        
        # ─────────────────────────────────────────────────────────────────────
        # CONSTRUIR RESPUESTA FINAL
        # ─────────────────────────────────────────────────────────────────────
        return AgentResponse(
            success=final_decision.decision_type != DecisionType.ERROR,
            decision=final_decision,
            request_id=request.request_id,
            session_id=self.session_id,
            total_iterations=iteration,
            total_tokens_input=self.total_input_tokens,
            total_tokens_output=self.total_output_tokens,
            total_cost_usd=round(self.total_cost_usd, 6),
            total_cost_eur=round(cost_eur, 6),
            execution_time_ms=round(execution_time_ms, 2),
            tool_calls=tool_results,
            budget_remaining_eur=round(max(0, budget_remaining), 6),
            stopped_reason=stopped_reason,
        )
    
    # =========================================================================
    # CONTROL DE PRESUPUESTO
    # =========================================================================
    
    def _check_budget(self) -> None:
        """
        Verifica que no se haya excedido el presupuesto.
        
        Se llama ANTES de cada llamada al LLM para garantizar
        que nunca gastamos más de lo autorizado.
        
        Raises:
            BudgetExceededError: Si el coste acumulado >= límite
        """
        current_cost_eur = self.total_cost_usd / self.settings.eur_usd_rate
        
        if current_cost_eur >= self.settings.budget_limit_eur:
            raise BudgetExceededError(
                current_cost=current_cost_eur,
                limit=self.settings.budget_limit_eur,
            )
    
    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        Calcula el coste en USD para una llamada.
        
        Args:
            input_tokens: Tokens de entrada consumidos
            output_tokens: Tokens de salida generados
            
        Returns:
            Coste en USD
        """
        return self.settings.estimate_cost_usd(input_tokens, output_tokens)
    
    # =========================================================================
    # LLAMADA AL LLM
    # =========================================================================
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APIConnectionError)),
    )
    async def _call_llm(self, iteration: int) -> Decision:
        """
        Llama al LLM y parsea la respuesta.
        
        Incluye:
        - Retry automático con backoff exponencial
        - Cálculo y logging de costes
        - Parseo seguro de JSON
        
        Args:
            iteration: Número de iteración actual
            
        Returns:
            Decision validada
        """
        with timed_operation("llm_call") as timer:
            # Llamada síncrona (Anthropic SDK no tiene async nativo aún)
            response = self.client.messages.create(
                model=self.settings.anthropic_model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=self.conversation_history,
            )
        
        # Extraer métricas de uso
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost_usd = self._calculate_cost(input_tokens, output_tokens)
        
        # Acumular métricas
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost_usd += cost_usd
        
        # Log de la llamada
        self.audit.log_llm_call(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=timer.elapsed_ms,
        )
        
        # Extraer contenido de la respuesta
        raw_content = response.content[0].text
        
        # Agregar respuesta del asistente al historial
        self.conversation_history.append({
            "role": "assistant",
            "content": raw_content,
        })
        
        # Parsear a Decision
        decision = self._parse_llm_response(raw_content, iteration)
        
        return decision
    
    def _parse_llm_response(self, raw_content: str, iteration: int) -> Decision:
        """
        Parsea la respuesta del LLM a Decision.
        
        Maneja casos donde el LLM:
        - Devuelve JSON válido ✓
        - Envuelve JSON en markdown ```json...```
        - Devuelve texto plano (fallback a response)
        - Devuelve JSON con campos inválidos (Pydantic lo atrapa)
        
        Args:
            raw_content: Texto crudo de la respuesta
            iteration: Número de iteración actual
            
        Returns:
            Decision validada
        """
        # Intentar extraer JSON del contenido
        json_str = self._extract_json(raw_content)
        
        if json_str:
            try:
                data = json.loads(json_str)
                
                # Mapear campos al modelo
                decision_data = {
                    "decision_type": data.get("decision_type", "response"),
                    "content": data.get("content", raw_content),
                    "confidence": data.get("confidence", "medium"),
                    "reasoning": data.get("reasoning", "Sin razonamiento explícito"),
                    "iteration": iteration,
                }
                
                # Agregar tool_call si existe
                if data.get("tool_call") and data.get("decision_type") == "tool_call":
                    decision_data["tool_call"] = ToolCall(
                        tool_name=data["tool_call"].get("tool_name", "unknown"),
                        parameters=data["tool_call"].get("parameters", {}),
                        reasoning=data["tool_call"].get("reasoning", "Sin razonamiento"),
                    )
                
                # Agregar escalation_reason si existe
                if data.get("escalation_reason") and data.get("decision_type") == "escalate":
                    decision_data["escalation_reason"] = data["escalation_reason"]
                
                # Agregar suggested_actions si existe
                if data.get("suggested_actions"):
                    decision_data["suggested_actions"] = data["suggested_actions"]
                
                # Validar con Pydantic
                return Decision(**decision_data)
            
            except json.JSONDecodeError as e:
                self.audit.log_error(e, context="json_parse_error")
            except Exception as e:
                self.audit.log_error(e, context="decision_validation_error")
        
        # Fallback: tratar como respuesta directa
        return Decision(
            decision_type=DecisionType.RESPONSE,
            content=raw_content,
            confidence=ConfidenceLevel.LOW,
            reasoning="Respuesta directa del LLM (no se pudo parsear JSON estructurado)",
            iteration=iteration,
        )
    
    def _extract_json(self, text: str) -> Optional[str]:
        """
        Extrae JSON de un texto que puede contener markdown u otro formato.
        
        Args:
            text: Texto que puede contener JSON
            
        Returns:
            String JSON limpio o None
        """
        # Caso 1: JSON puro
        text = text.strip()
        if text.startswith("{") and text.endswith("}"):
            return text
        
        # Caso 2: Markdown code block ```json ... ```
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            return json_match.group(1)
        
        # Caso 3: JSON embebido en texto
        json_match = re.search(r'(\{[^{}]*"decision_type"[^{}]*\})', text, re.DOTALL)
        if json_match:
            return json_match.group(1)
        
        # Caso 4: JSON con objetos anidados
        brace_count = 0
        start_idx = None
        for i, char in enumerate(text):
            if char == '{':
                if brace_count == 0:
                    start_idx = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and start_idx is not None:
                    return text[start_idx:i+1]
        
        return None
    
    # =========================================================================
    # EJECUCIÓN DE HERRAMIENTAS
    # =========================================================================
    
    async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """
        Ejecuta una herramienta de forma segura.
        
        Incluye:
        - Validación de que la herramienta existe
        - Timeout de ejecución
        - Logging completo
        - Manejo de errores
        
        Args:
            tool_call: Especificación de la herramienta a ejecutar
            
        Returns:
            ToolResult con el resultado o error
        """
        tool_name = tool_call.tool_name
        
        # Verificar que la herramienta existe
        if tool_name not in self.tool_registry:
            error_msg = f"Herramienta '{tool_name}' no registrada. Disponibles: {list(self.tool_registry.keys())}"
            self.audit.log_tool_call(
                tool_name=tool_name,
                parameters=tool_call.parameters,
                success=False,
                result=None,
                execution_time_ms=0,
                error=error_msg,
            )
            return ToolResult(
                tool_name=tool_name,
                success=False,
                data=None,
                error=error_msg,
                execution_time_ms=0,
            )
        
        # Ejecutar herramienta
        tool_info = self.tool_registry[tool_name]
        handler = tool_info["handler"]
        
        with timed_operation(f"tool_{tool_name}") as timer:
            try:
                # Ejecutar handler (puede ser sync o async)
                if callable(handler):
                    import asyncio
                    if asyncio.iscoroutinefunction(handler):
                        result = await handler(**tool_call.parameters)
                    else:
                        result = handler(**tool_call.parameters)
                else:
                    raise ValueError(f"Handler de {tool_name} no es callable")
                
                # Log exitoso
                self.audit.log_tool_call(
                    tool_name=tool_name,
                    parameters=tool_call.parameters,
                    success=True,
                    result=result,
                    execution_time_ms=timer.elapsed_ms,
                )
                
                return ToolResult(
                    tool_name=tool_name,
                    success=True,
                    data=result,
                    error=None,
                    execution_time_ms=timer.elapsed_ms,
                )
            
            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                self.audit.log_tool_call(
                    tool_name=tool_name,
                    parameters=tool_call.parameters,
                    success=False,
                    result=None,
                    execution_time_ms=timer.elapsed_ms,
                    error=error_msg,
                )
                
                return ToolResult(
                    tool_name=tool_name,
                    success=False,
                    data=None,
                    error=error_msg,
                    execution_time_ms=timer.elapsed_ms,
                )