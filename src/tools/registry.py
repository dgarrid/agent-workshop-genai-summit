"""
Registro de herramientas para Agent.

Este módulo define:
- JSON Schemas de cada herramienta (para que el LLM sepa cómo usarlas)
- Factory function para crear el registry completo
- Validación de parámetros

Principio MCP: Las herramientas se definen UNA vez y se usan con cualquier modelo.
"""

from typing import Any, Callable

from src.tools.crm import crm_lookup
from src.tools.knowledge import knowledge_search


# =============================================================================
# JSON SCHEMAS DE HERRAMIENTAS
# =============================================================================
# Estos schemas siguen el formato JSON Schema y son los que el LLM
# "ve" para entender qué parámetros acepta cada herramienta.
# =============================================================================

CRM_LOOKUP_SCHEMA = {
    "name": "crm_lookup",
    "description": (
        "Busca información de clientes en el CRM corporativo. "
        "Puede buscar por ID de cliente, email, o realizar una búsqueda general. "
        "Devuelve datos del cliente como nombre, email, estado VIP, historial de compras, etc."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "description": "ID único del cliente (ej: 'CUST-001')",
            },
            "email": {
                "type": "string",
                "description": "Email del cliente para búsqueda",
            },
            "query": {
                "type": "string",
                "description": "Búsqueda general por nombre o cualquier campo",
            },
        },
        "required": [],  # Al menos uno debe proporcionarse
    },
    "examples": [
        {"customer_id": "CUST-001"},
        {"email": "cliente@empresa.com"},
        {"query": "García Madrid"},
    ],
}

KNOWLEDGE_SEARCH_SCHEMA = {
    "name": "knowledge_search",
    "description": (
        "Busca información en la base de conocimiento corporativa. "
        "Contiene documentación de productos, políticas de la empresa, "
        "FAQs, procedimientos de soporte, y guías técnicas. "
        "Usa esta herramienta para responder preguntas sobre políticas, "
        "procedimientos, o información del producto."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Términos de búsqueda (ej: 'política devoluciones', 'precio premium')",
            },
            "category": {
                "type": "string",
                "enum": ["faq", "policies", "products", "procedures", "all"],
                "description": "Categoría donde buscar. Por defecto 'all'.",
                "default": "all",
            },
            "max_results": {
                "type": "integer",
                "description": "Número máximo de resultados a devolver",
                "default": 3,
                "minimum": 1,
                "maximum": 10,
            },
        },
        "required": ["query"],
    },
    "examples": [
        {"query": "política de devoluciones"},
        {"query": "precio plan premium", "category": "products"},
        {"query": "resetear contraseña", "category": "faq", "max_results": 5},
    ],
}


# =============================================================================
# CATÁLOGO DE HERRAMIENTAS
# =============================================================================

TOOL_CATALOG = {
    "crm_lookup": {
        "schema": CRM_LOOKUP_SCHEMA,
        "handler": crm_lookup,
    },
    "knowledge_search": {
        "schema": KNOWLEDGE_SEARCH_SCHEMA,
        "handler": knowledge_search,
    },
}


# =============================================================================
# FUNCIONES DE REGISTRO
# =============================================================================

def get_tool_registry() -> dict[str, dict[str, Any]]:
    """
    Obtiene el registro completo de herramientas.
    
    Returns:
        Diccionario {nombre: {"handler": callable, "schema": dict}}
        
    Example:
        >>> registry = get_tool_registry()
        >>> orchestrator = BudgetedOrchestrator(tool_registry=registry)
    """
    return {
        name: {
            "handler": info["handler"],
            "schema": info["schema"],
        }
        for name, info in TOOL_CATALOG.items()
    }


def get_tools_for_prompt() -> str:
    """
    Genera descripción de herramientas para incluir en el prompt.
    
    Returns:
        String formateado con las herramientas disponibles
        
    Example:
        >>> tools_desc = get_tools_for_prompt()
        >>> system_prompt = f"Tienes estas herramientas:\\n{tools_desc}"
    """
    lines = ["HERRAMIENTAS DISPONIBLES:", ""]
    
    for name, info in TOOL_CATALOG.items():
        schema = info["schema"]
        lines.append(f"### {name}")
        lines.append(f"Descripción: {schema['description']}")
        lines.append("Parámetros:")
        
        params = schema["parameters"]["properties"]
        required = schema["parameters"].get("required", [])
        
        for param_name, param_info in params.items():
            req_marker = "(requerido)" if param_name in required else "(opcional)"
            param_type = param_info.get("type", "any")
            param_desc = param_info.get("description", "Sin descripción")
            lines.append(f"  - {param_name} [{param_type}] {req_marker}: {param_desc}")
        
        if schema.get("examples"):
            lines.append("Ejemplos de uso:")
            for ex in schema["examples"][:2]:  # Max 2 ejemplos
                lines.append(f"  {ex}")
        
        lines.append("")
    
    return "\n".join(lines)


def validate_tool_params(tool_name: str, params: dict) -> tuple[bool, str]:
    """
    Valida los parámetros de una herramienta contra su schema.
    
    Args:
        tool_name: Nombre de la herramienta
        params: Parámetros proporcionados
        
    Returns:
        Tupla (es_válido, mensaje_error)
        
    Example:
        >>> valid, error = validate_tool_params("crm_lookup", {"customer_id": "CUST-001"})
        >>> if not valid:
        ...     print(f"Error: {error}")
    """
    if tool_name not in TOOL_CATALOG:
        return False, f"Herramienta '{tool_name}' no existe"
    
    schema = TOOL_CATALOG[tool_name]["schema"]["parameters"]
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    
    # Verificar campos requeridos
    for req_field in required:
        if req_field not in params:
            return False, f"Falta campo requerido: {req_field}"
    
    # Verificar que al menos un campo está presente (para crm_lookup)
    if tool_name == "crm_lookup" and not any(params.get(k) for k in ["customer_id", "email", "query"]):
        return False, "Debe proporcionar al menos customer_id, email, o query"
    
    # Verificar tipos básicos
    for param_name, param_value in params.items():
        if param_name not in properties:
            continue  # Ignorar campos extra
        
        expected_type = properties[param_name].get("type")
        
        if expected_type == "string" and not isinstance(param_value, str):
            return False, f"'{param_name}' debe ser string, recibido: {type(param_value).__name__}"
        
        if expected_type == "integer" and not isinstance(param_value, int):
            return False, f"'{param_name}' debe ser integer, recibido: {type(param_value).__name__}"
        
        # Verificar enum si existe
        if "enum" in properties[param_name]:
            allowed = properties[param_name]["enum"]
            if param_value not in allowed:
                return False, f"'{param_name}' debe ser uno de: {allowed}"
    
    return True, ""


def list_available_tools() -> list[str]:
    """Retorna lista de nombres de herramientas disponibles."""
    return list(TOOL_CATALOG.keys())