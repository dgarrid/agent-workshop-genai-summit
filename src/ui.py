"""
Interfaz Gráfica (Streamlit) para el Nexus Agent.

Proporciona una experiencia visual tipo chat con:
- Historial de conversación
- Panel lateral de métricas financieras (Presupuesto)
- Visualización de logs de auditoría y decisiones internas
"""

import sys
import os
import asyncio
from datetime import datetime

# --- HACK DEL TALLER: Path Setup ---
# Esto permite ejecutar 'streamlit run src/ui.py' sin líos de PYTHONPATH
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)
# -----------------------------------

import streamlit as st

# Importamos los módulos del agente con manejo de errores
try:
    from src.core.agent import BudgetedOrchestrator
    from src.models.incoming import AgentRequest
    # Intentamos importar InputChannel o ChannelType según la versión
    try:
        from src.models.incoming import InputChannel as ChannelEnum
    except ImportError:
        from src.models.incoming import ChannelType as ChannelEnum
        
    from src.tools.registry import get_tool_registry
    from src.config import get_settings
except ImportError as e:
    st.error(f"🔥 Error de importación crítico: {e}")
    st.stop()

# ==============================================================================
# CONFIGURACIÓN DE PÁGINA
# ==============================================================================
st.set_page_config(
    page_title="Nexus Agent | Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS (Modo Matrix)
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    .stChatInputContainer { padding-bottom: 20px; }
    div[data-testid="stExpander"] { background-color: #262730; border-radius: 5px; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# ESTADO DE SESIÓN
# ==============================================================================
if "messages" not in st.session_state:
    st.session_state.messages = []
if "budget_spent" not in st.session_state:
    st.session_state.budget_spent = 0.0
if "audit_logs" not in st.session_state:
    st.session_state.audit_logs = []
if "orchestrator" not in st.session_state:
    try:
        registry = get_tool_registry()
        st.session_state.orchestrator = BudgetedOrchestrator(tool_registry=registry)
    except Exception as e:
        st.error(f"Error iniciando orquestador: {e}")

# ==============================================================================
# LÓGICA
# ==============================================================================
async def run_agent(user_input: str):
    """Ejecuta el agente y devuelve la respuesta."""
    # Usamos el canal CLI/API para simular
    # Nota: Ajusta 'cli' o 'api' según tu enum InputChannel
    channel = ChannelEnum.CLI if hasattr(ChannelEnum, 'CLI') else ChannelEnum.API
    
    request = AgentRequest(
        channel=channel,
        content=user_input
    )
    return await st.session_state.orchestrator.process(request)

# ==============================================================================
# SIDEBAR
# ==============================================================================
with st.sidebar:
    st.header("🛡️ Gobernanza")
    
    try:
        settings = get_settings()
        limit = settings.budget_limit_eur
        spent = st.session_state.budget_spent
        percent = min(100, (spent / limit) * 100) if limit > 0 else 100
        
        # Semáforo
        color = "🟢" if percent < 50 else "🟡" if percent < 80 else "🔴"
        st.progress(percent / 100, text=f"{color} Uso: {percent:.1f}%")
        
        c1, c2 = st.columns(2)
        c1.metric("Límite", f"€{limit:.2f}")
        c2.metric("Gastado", f"€{spent:.4f}")
        
        st.divider()
        st.subheader("🔍 Auditoría")
        
        if not st.session_state.audit_logs:
            st.caption("Sin eventos recientes.")
            
        for log in reversed(st.session_state.audit_logs[-10:]): # Mostrar últimos 10
            with st.expander(f"{log['time']} - {log['type']}", expanded=False):
                st.write(log['data'])
                
    except Exception as e:
        st.error(f"Error sidebar: {e}")

# ==============================================================================
# MAIN CHAT
# ==============================================================================
st.title("Nexus Agent 🤖")

# 1. Renderizar historial
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "metrics" in msg:
            with st.expander("📊 Detalles Técnicos"):
                st.json(msg["metrics"])

# 2. Input de usuario
if prompt := st.chat_input("Escribe tu consulta..."):
    # Guardar mensaje usuario
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Procesar respuesta
    with st.chat_message("assistant"):
        status_container = st.status("🧠 Procesando...", expanded=True)
        response = None
        error_msg = None
        
        try:
            # Llamada al agente (Async wrapper)
            response = asyncio.run(run_agent(prompt))
            
            # Procesar éxito
            status_container.update(label="✅ Completado", state="complete", expanded=False)
            
            # Mostrar contenido
            content = response.decision.content
            st.markdown(content)
            
            # Guardar en historial
            metrics = {
                "cost_eur": response.total_cost_eur,
                "latency": f"{response.execution_time_ms:.0f}ms",
                "tokens": response.total_tokens_input + response.total_tokens_output
            }
            st.session_state.messages.append({
                "role": "assistant",
                "content": content,
                "metrics": metrics
            })
            
            # Actualizar estado global (Presupuesto/Audit)
            st.session_state.budget_spent += response.total_cost_eur
            st.session_state.audit_logs.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "type": response.decision.decision_type.value,
                "data": {"reasoning": response.decision.reasoning, "cost": response.total_cost_eur}
            })
            
            # Flag para recargar (lo hacemos al final para no interrumpir el renderizado actual)
            should_rerun = True

        except Exception as e:
            status_container.update(label="❌ Error", state="error")
            st.error(f"Error del sistema: {str(e)}")
            should_rerun = False

    if should_rerun:
        st.rerun()