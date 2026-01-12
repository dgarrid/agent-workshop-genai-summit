"""
Herramienta CRM para el agente.

Esta herramienta proporciona acceso READ-ONLY a la base de datos
del CRM simulado. Implementa:
- Búsqueda por ID, email, o texto libre
- Sanitización de inputs (prevención SQL injection)
- Límite de resultados

Principio: Las herramientas del agente NUNCA modifican datos.
"""

import sqlite3
from pathlib import Path
from typing import Optional, Any
import re

from src.config import get_settings


# =============================================================================
# FUNCIONES DE SANITIZACIÓN
# =============================================================================

def sanitize_input(value: str) -> str:
    """
    Sanitiza input para prevenir SQL injection.
    
    Args:
        value: Valor a sanitizar
        
    Returns:
        Valor sanitizado
    """
    if not isinstance(value, str):
        return str(value)
    
    # Eliminar caracteres peligrosos para SQL
    # Permitimos letras, números, espacios, guiones, puntos, @, y algunos más
    sanitized = re.sub(r"[;'\"\\\x00]", "", value)
    
    # Limitar longitud
    return sanitized[:200]


def validate_customer_id(customer_id: str) -> bool:
    """
    Valida formato de customer_id.
    
    Formato esperado: CUST-XXX donde XXX son dígitos
    """
    return bool(re.match(r'^CUST-\d{3,6}$', customer_id))


# =============================================================================
# CONEXIÓN A BASE DE DATOS
# =============================================================================

def get_db_connection() -> sqlite3.Connection:
    """
    Obtiene conexión READ-ONLY a la base de datos CRM.
    
    Returns:
        Conexión SQLite en modo solo lectura
    """
    settings = get_settings()
    db_path = settings.crm_database_path
    
    if not db_path.exists():
        raise FileNotFoundError(
            f"Base de datos CRM no encontrada: {db_path}. "
            f"Ejecuta 'python data/setup_data.py' para crearla."
        )
    
    # Conexión en modo solo lectura (uri=true permite el parámetro mode)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row  # Para acceder por nombre de columna
    
    return conn


# =============================================================================
# FUNCIÓN PRINCIPAL DE BÚSQUEDA
# =============================================================================

def crm_lookup(
    customer_id: Optional[str] = None,
    email: Optional[str] = None,
    query: Optional[str] = None,
) -> dict[str, Any]:
    """
    Busca información de clientes en el CRM.
    
    Esta es la función que el agente ejecuta. Soporta tres modos:
    1. Búsqueda por ID exacto (customer_id)
    2. Búsqueda por email exacto (email)
    3. Búsqueda general por texto (query)
    
    Args:
        customer_id: ID único del cliente (ej: "CUST-001")
        email: Email del cliente
        query: Búsqueda de texto libre
        
    Returns:
        Diccionario con resultados o error
        
    Example:
        >>> result = crm_lookup(customer_id="CUST-001")
        >>> print(result["customer"]["name"])
        "María García"
    """
    # Validar que al menos un parámetro está presente
    if not any([customer_id, email, query]):
        return {
            "success": False,
            "error": "Debe proporcionar al menos customer_id, email, o query",
            "customers": [],
        }
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # ─────────────────────────────────────────────────────────────────────
        # MODO 1: Búsqueda por customer_id (exacta)
        # ─────────────────────────────────────────────────────────────────────
        if customer_id:
            customer_id = sanitize_input(customer_id)
            
            if not validate_customer_id(customer_id):
                return {
                    "success": False,
                    "error": f"Formato de customer_id inválido: {customer_id}. Formato esperado: CUST-XXX",
                    "customers": [],
                }
            
            cursor.execute("""
                SELECT 
                    c.id, c.customer_id, c.name, c.email, c.phone,
                    c.company, c.is_vip, c.created_at, c.notes,
                    COUNT(o.id) as total_orders,
                    COALESCE(SUM(o.total_amount), 0) as total_spent
                FROM customers c
                LEFT JOIN orders o ON c.id = o.customer_id
                WHERE c.customer_id = ?
                GROUP BY c.id
            """, (customer_id,))
            
            row = cursor.fetchone()
            
            if row:
                customer = _row_to_customer_dict(row)
                
                # Obtener últimos pedidos
                cursor.execute("""
                    SELECT order_id, status, total_amount, created_at
                    FROM orders
                    WHERE customer_id = ?
                    ORDER BY created_at DESC
                    LIMIT 5
                """, (row["id"],))
                
                customer["recent_orders"] = [
                    dict(order) for order in cursor.fetchall()
                ]
                
                conn.close()
                return {
                    "success": True,
                    "customer": customer,
                    "message": f"Cliente encontrado: {customer['name']}",
                }
            else:
                conn.close()
                return {
                    "success": True,
                    "customer": None,
                    "message": f"No se encontró cliente con ID: {customer_id}",
                }
        
        # ─────────────────────────────────────────────────────────────────────
        # MODO 2: Búsqueda por email (exacta)
        # ─────────────────────────────────────────────────────────────────────
        if email:
            email = sanitize_input(email).lower()
            
            cursor.execute("""
                SELECT 
                    c.id, c.customer_id, c.name, c.email, c.phone,
                    c.company, c.is_vip, c.created_at, c.notes,
                    COUNT(o.id) as total_orders,
                    COALESCE(SUM(o.total_amount), 0) as total_spent
                FROM customers c
                LEFT JOIN orders o ON c.id = o.customer_id
                WHERE LOWER(c.email) = ?
                GROUP BY c.id
            """, (email,))
            
            row = cursor.fetchone()
            
            if row:
                customer = _row_to_customer_dict(row)
                conn.close()
                return {
                    "success": True,
                    "customer": customer,
                    "message": f"Cliente encontrado: {customer['name']}",
                }
            else:
                conn.close()
                return {
                    "success": True,
                    "customer": None,
                    "message": f"No se encontró cliente con email: {email}",
                }
        
        # ─────────────────────────────────────────────────────────────────────
        # MODO 3: Búsqueda general (texto libre)
        # ─────────────────────────────────────────────────────────────────────
        if query:
            query = sanitize_input(query)
            search_term = f"%{query}%"
            
            cursor.execute("""
                SELECT 
                    c.id, c.customer_id, c.name, c.email, c.phone,
                    c.company, c.is_vip, c.created_at, c.notes,
                    COUNT(o.id) as total_orders,
                    COALESCE(SUM(o.total_amount), 0) as total_spent
                FROM customers c
                LEFT JOIN orders o ON c.id = o.customer_id
                WHERE 
                    c.name LIKE ? OR 
                    c.email LIKE ? OR 
                    c.company LIKE ? OR
                    c.customer_id LIKE ?
                GROUP BY c.id
                LIMIT 10
            """, (search_term, search_term, search_term, search_term))
            
            rows = cursor.fetchall()
            customers = [_row_to_customer_dict(row) for row in rows]
            
            conn.close()
            return {
                "success": True,
                "customers": customers,
                "count": len(customers),
                "message": f"Se encontraron {len(customers)} cliente(s) para '{query}'",
            }
        
        conn.close()
        return {
            "success": False,
            "error": "No se proporcionaron parámetros de búsqueda válidos",
            "customers": [],
        }
    
    except FileNotFoundError as e:
        return {
            "success": False,
            "error": str(e),
            "customers": [],
        }
    except sqlite3.Error as e:
        return {
            "success": False,
            "error": f"Error de base de datos: {str(e)}",
            "customers": [],
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error inesperado: {type(e).__name__}: {str(e)}",
            "customers": [],
        }


# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

def _row_to_customer_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convierte una fila de SQLite a diccionario de cliente."""
    return {
        "customer_id": row["customer_id"],
        "name": row["name"],
        "email": row["email"],
        "phone": row["phone"],
        "company": row["company"],
        "is_vip": bool(row["is_vip"]),
        "member_since": row["created_at"],
        "total_orders": row["total_orders"],
        "total_spent": round(row["total_spent"], 2),
        "notes": row["notes"],
    }


def get_vip_customers() -> list[dict[str, Any]]:
    """
    Obtiene lista de todos los clientes VIP.
    
    Returns:
        Lista de clientes con is_vip=True
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                c.id, c.customer_id, c.name, c.email, c.phone,
                c.company, c.is_vip, c.created_at, c.notes,
                COUNT(o.id) as total_orders,
                COALESCE(SUM(o.total_amount), 0) as total_spent
            FROM customers c
            LEFT JOIN orders o ON c.id = o.customer_id
            WHERE c.is_vip = 1
            GROUP BY c.id
            ORDER BY total_spent DESC
        """)
        
        rows = cursor.fetchall()
        customers = [_row_to_customer_dict(row) for row in rows]
        
        conn.close()
        return customers
    
    except Exception:
        return []