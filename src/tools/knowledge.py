"""
Herramienta Knowledge Base para nuestro agente.

Esta herramienta proporciona acceso READ-ONLY a la base de conocimiento
corporativa (archivos Markdown). Implementa:
- Búsqueda por términos en contenido y títulos
- Filtrado por categoría
- Prevención de path traversal (CRÍTICO para seguridad)

Principio: El agente NUNCA puede leer archivos fuera del directorio permitido.
"""

import os
import re
from pathlib import Path
from typing import Optional, Any

from src.config import get_settings


# =============================================================================
# SEGURIDAD: VALIDACIÓN DE PATHS
# =============================================================================

def is_safe_path(base_path: Path, requested_path: Path) -> bool:
    """
    Verifica que un path esté dentro del directorio permitido.
    
    CRÍTICO: Previene ataques de path traversal como:
    - ../../../etc/passwd
    - ..\\..\\windows\\system32
    
    Args:
        base_path: Directorio base permitido
        requested_path: Path solicitado
        
    Returns:
        True si el path es seguro, False si no
    """
    try:
        # Resolver paths a absolutos (elimina ../, ./, etc.)
        base_resolved = base_path.resolve()
        requested_resolved = requested_path.resolve()
        
        # Verificar que el path resuelto empieza con el base
        return str(requested_resolved).startswith(str(base_resolved))
    except (OSError, ValueError):
        return False


def sanitize_search_query(query: str) -> str:
    """
    Sanitiza query de búsqueda.
    
    Args:
        query: Términos de búsqueda
        
    Returns:
        Query sanitizada
    """
    if not isinstance(query, str):
        return ""
    
    # Eliminar caracteres peligrosos
    sanitized = re.sub(r'[<>"\'\\/;`]', '', query)
    
    # Eliminar secuencias de path traversal
    sanitized = re.sub(r'\.\.+[/\\]?', '', sanitized)
    
    # Limitar longitud
    return sanitized[:200].strip()


# =============================================================================
# CATEGORÍAS DE CONOCIMIENTO
# =============================================================================

CATEGORIES = {
    "faq": {
        "path": "faq",
        "description": "Preguntas frecuentes",
    },
    "policies": {
        "path": "policies",
        "description": "Políticas de la empresa",
    },
    "products": {
        "path": "products",
        "description": "Información de productos y servicios",
    },
    "procedures": {
        "path": "procedures",
        "description": "Procedimientos internos",
    },
}


# =============================================================================
# FUNCIÓN PRINCIPAL DE BÚSQUEDA
# =============================================================================

def knowledge_search(
    query: str,
    category: str = "all",
    max_results: int = 3,
) -> dict[str, Any]:
    """
    Busca en la base de conocimiento corporativa.
    
    Esta es la función que el agente ejecuta. Busca términos
    en el contenido y títulos de los archivos Markdown.
    
    Args:
        query: Términos de búsqueda
        category: Categoría donde buscar ("faq", "policies", "products", "procedures", "all")
        max_results: Máximo número de resultados (1-10)
        
    Returns:
        Diccionario con resultados o error
        
    Example:
        >>> result = knowledge_search("política devoluciones")
        >>> for doc in result["results"]:
        ...     print(doc["title"], "-", doc["snippet"])
    """
    # ─────────────────────────────────────────────────────────────────────────
    # VALIDACIÓN DE INPUTS
    # ─────────────────────────────────────────────────────────────────────────
    query = sanitize_search_query(query)
    
    if not query:
        return {
            "success": False,
            "error": "Query de búsqueda vacía o inválida",
            "results": [],
        }
    
    if category not in ["all"] + list(CATEGORIES.keys()):
        return {
            "success": False,
            "error": f"Categoría inválida: {category}. Opciones: all, {', '.join(CATEGORIES.keys())}",
            "results": [],
        }
    
    max_results = max(1, min(10, max_results))  # Clamp entre 1 y 10
    
    # ─────────────────────────────────────────────────────────────────────────
    # OBTENER BASE PATH
    # ─────────────────────────────────────────────────────────────────────────
    settings = get_settings()
    base_path = settings.knowledge_base_path
    
    if not base_path.exists():
        return {
            "success": False,
            "error": f"Base de conocimiento no encontrada: {base_path}. Ejecuta 'python data/setup_data.py'",
            "results": [],
        }
    
    # ─────────────────────────────────────────────────────────────────────────
    # DETERMINAR DIRECTORIOS A BUSCAR
    # ─────────────────────────────────────────────────────────────────────────
    if category == "all":
        search_dirs = [base_path / cat_info["path"] for cat_info in CATEGORIES.values()]
        search_dirs.append(base_path)  # También buscar en raíz
    else:
        search_dirs = [base_path / CATEGORIES[category]["path"]]
    
    # ─────────────────────────────────────────────────────────────────────────
    # BUSCAR EN ARCHIVOS
    # ─────────────────────────────────────────────────────────────────────────
    results = []
    query_lower = query.lower()
    query_terms = query_lower.split()
    
    try:
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            
            # Buscar archivos .md en el directorio
            for file_path in search_dir.glob("**/*.md"):
                # SEGURIDAD: Verificar que el archivo está dentro del path permitido
                if not is_safe_path(base_path, file_path):
                    continue  # Path traversal detectado, ignorar
                
                try:
                    content = file_path.read_text(encoding="utf-8")
                    content_lower = content.lower()
                    
                    # Calcular relevancia (número de términos encontrados)
                    relevance = sum(
                        1 for term in query_terms 
                        if term in content_lower or term in file_path.stem.lower()
                    )
                    
                    if relevance > 0:
                        # Extraer snippet relevante
                        snippet = _extract_snippet(content, query_terms)
                        
                        # Extraer título del contenido o usar nombre de archivo
                        title = _extract_title(content, file_path)
                        
                        # Determinar categoría del archivo
                        file_category = _get_file_category(file_path, base_path)
                        
                        results.append({
                            "title": title,
                            "category": file_category,
                            "snippet": snippet,
                            "relevance": relevance,
                            "file": file_path.name,
                        })
                
                except (IOError, UnicodeDecodeError):
                    continue  # Ignorar archivos que no se pueden leer
        
        # Ordenar por relevancia y limitar resultados
        results.sort(key=lambda x: x["relevance"], reverse=True)
        results = results[:max_results]
        
        # Eliminar campo de relevancia del output (es interno)
        for r in results:
            del r["relevance"]
        
        return {
            "success": True,
            "query": query,
            "category": category,
            "results": results,
            "count": len(results),
            "message": f"Se encontraron {len(results)} resultado(s) para '{query}'",
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": f"Error en búsqueda: {type(e).__name__}: {str(e)}",
            "results": [],
        }


# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

def _extract_snippet(content: str, query_terms: list[str], snippet_length: int = 200) -> str:
    """
    Extrae un snippet relevante del contenido.
    
    Busca la primera ocurrencia de algún término de búsqueda
    y devuelve el contexto alrededor.
    """
    content_lower = content.lower()
    
    # Encontrar la posición del primer término
    best_pos = len(content)
    for term in query_terms:
        pos = content_lower.find(term)
        if pos != -1 and pos < best_pos:
            best_pos = pos
    
    if best_pos == len(content):
        # No se encontró ningún término, devolver inicio
        best_pos = 0
    
    # Calcular inicio y fin del snippet
    start = max(0, best_pos - 50)
    end = min(len(content), start + snippet_length)
    
    # Ajustar para no cortar palabras
    if start > 0:
        # Buscar el inicio de la palabra
        while start > 0 and content[start] not in ' \n':
            start -= 1
        start += 1
    
    if end < len(content):
        # Buscar el fin de la palabra
        while end < len(content) and content[end] not in ' \n':
            end += 1
    
    snippet = content[start:end].strip()
    
    # Añadir elipsis si es necesario
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."
    
    # Limpiar saltos de línea excesivos
    snippet = re.sub(r'\n{2,}', '\n', snippet)
    
    return snippet


def _extract_title(content: str, file_path: Path) -> str:
    """
    Extrae el título del documento.
    
    Busca un encabezado H1 (# Título) o usa el nombre del archivo.
    """
    # Buscar # al inicio de línea
    match = re.search(r'^#\s+(.+)\s*$'
    , content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    
    # Usar nombre de archivo sin extensión, humanizado
    name = file_path.stem
    name = name.replace("_", " ").replace("-", " ")
    return name.title()


def _get_file_category(file_path: Path, base_path: Path) -> str:
    """
    Determina la categoría de un archivo basándose en su ubicación.
    """
    try:
        relative = file_path.relative_to(base_path)
        parts = relative.parts
        
        if len(parts) > 1:
            potential_category = parts[0]
            if potential_category in CATEGORIES:
                return potential_category
        
        return "general"
    except ValueError:
        return "unknown"


def list_categories() -> dict[str, str]:
    """
    Lista las categorías disponibles.
    
    Returns:
        Diccionario {nombre: descripción}
    """
    return {name: info["description"] for name, info in CATEGORIES.items()}


def get_document(filename: str, category: str = "all") -> dict[str, Any]:
    """
    Obtiene el contenido completo de un documento específico.
    
    SEGURIDAD: Valida que el archivo esté dentro de la base de conocimiento.
    
    Args:
        filename: Nombre del archivo (ej: "politica_devoluciones.md")
        category: Categoría del documento
        
    Returns:
        Contenido del documento o error
    """
    settings = get_settings()
    base_path = settings.knowledge_base_path
    
    # Sanitizar filename
    filename = re.sub(r'[<>"\'\\/;`]', '', filename)
    filename = re.sub(r'\.\.+', '', filename)
    
    # Construir path
    if category != "all" and category in CATEGORIES:
        file_path = base_path / CATEGORIES[category]["path"] / filename
    else:
        # Buscar en todas las categorías
        file_path = None
        for cat_info in CATEGORIES.values():
            potential_path = base_path / cat_info["path"] / filename
            if potential_path.exists():
                file_path = potential_path
                break
        
        # También buscar en raíz
        if file_path is None:
            file_path = base_path / filename
    
    # SEGURIDAD: Verificar path
    if not is_safe_path(base_path, file_path):
        return {
            "success": False,
            "error": "Acceso denegado: path fuera del directorio permitido",
            "content": None,
        }
    
    if not file_path.exists():
        return {
            "success": False,
            "error": f"Documento no encontrado: {filename}",
            "content": None,
        }
    
    try:
        content = file_path.read_text(encoding="utf-8")
        return {
            "success": True,
            "filename": filename,
            "category": _get_file_category(file_path, base_path),
            "title": _extract_title(content, file_path),
            "content": content,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error leyendo documento: {str(e)}",
            "content": None,
        }