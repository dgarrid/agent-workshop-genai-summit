"""
Tools module - Las manos de nuestro agente.

Contiene:
- registry.py: Definiciones JSON Schema y factory de herramientas
- crm.py: Acceso READ-ONLY al CRM
- knowledge.py: Búsqueda en base de conocimiento
"""

from src.tools.registry import (
    get_tool_registry,
    get_tools_for_prompt,
    validate_tool_params,
    list_available_tools,
)
from src.tools.crm import crm_lookup, get_vip_customers
from src.tools.knowledge import knowledge_search, get_document, list_categories

__all__ = [
    # Registry
    "get_tool_registry",
    "get_tools_for_prompt",
    "validate_tool_params",
    "list_available_tools",
    # CRM
    "crm_lookup",
    "get_vip_customers",
    # Knowledge
    "knowledge_search",
    "get_document",
    "list_categories",
]