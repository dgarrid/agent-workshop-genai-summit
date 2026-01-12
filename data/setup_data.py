"""
Script de inicialización de datos simulados para el agente

Ejecutar antes del primer uso:
    python data/setup_data.py

Crea:
- Base de datos SQLite con CRM simulado (clientes + pedidos)
- Base de conocimiento con archivos Markdown (FAQs, políticas, productos)
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import random


# =============================================================================
# PATHS
# =============================================================================

DATA_DIR = Path(__file__).parent
CRM_DB_PATH = DATA_DIR / "crm.db"
KNOWLEDGE_BASE_PATH = DATA_DIR / "knowledge"


# =============================================================================
# DATOS DE EJEMPLO: CLIENTES
# =============================================================================

CUSTOMERS = [
    {
        "customer_id": "CUST-001",
        "name": "María García López",
        "email": "maria.garcia@empresa.com",
        "phone": "+34 612 345 678",
        "company": "Tech Solutions SL",
        "is_vip": True,
        "notes": "Cliente desde 2020. Prefiere comunicación por email.",
    },
    {
        "customer_id": "CUST-002",
        "name": "Carlos Rodríguez Martín",
        "email": "carlos.rodriguez@gmail.com",
        "phone": "+34 623 456 789",
        "company": None,
        "is_vip": False,
        "notes": "Usuario particular. Interesado en plan familiar.",
    },
    {
        "customer_id": "CUST-003",
        "name": "Ana Fernández Ruiz",
        "email": "ana.fernandez@innovatech.es",
        "phone": "+34 634 567 890",
        "company": "InnovaTech",
        "is_vip": True,
        "notes": "Directora de IT. Gestiona 50 licencias enterprise.",
    },
    {
        "customer_id": "CUST-004",
        "name": "Pedro Sánchez Gómez",
        "email": "pedro.sanchez@outlook.com",
        "phone": "+34 645 678 901",
        "company": None,
        "is_vip": False,
        "notes": "Nuevo cliente. Primera compra en diciembre 2025.",
    },
    {
        "customer_id": "CUST-005",
        "name": "Laura Martínez Díaz",
        "email": "laura@startupvalencia.com",
        "phone": "+34 656 789 012",
        "company": "Startup Valencia",
        "is_vip": True,
        "notes": "Embajadora de marca. Participa en eventos.",
    },
    {
        "customer_id": "CUST-006",
        "name": "Javier López Torres",
        "email": "javier.lopez@corporacion.es",
        "phone": "+34 667 890 123",
        "company": "Corporación Nacional",
        "is_vip": True,
        "notes": "Cuenta corporativa. Facturación trimestral.",
    },
    {
        "customer_id": "CUST-007",
        "name": "Elena Ruiz Castro",
        "email": "elena.ruiz@gmail.com",
        "phone": "+34 678 901 234",
        "company": None,
        "is_vip": False,
        "notes": "Plan básico. Posible upgrade a premium.",
    },
    {
        "customer_id": "CUST-008",
        "name": "Miguel Ángel Navarro",
        "email": "miguel@agenciadigital.com",
        "phone": "+34 689 012 345",
        "company": "Agencia Digital 360",
        "is_vip": False,
        "notes": "Agencia con múltiples clientes. Interesado en programa partners.",
    },
]

# =============================================================================
# DATOS DE EJEMPLO: PEDIDOS
# =============================================================================

ORDER_STATUSES = ["pending", "processing", "shipped", "delivered", "cancelled"]
PRODUCTS = [
    ("Plan Básico Mensual", 9.99),
    ("Plan Premium Mensual", 29.99),
    ("Plan Enterprise Mensual", 99.99),
    ("Plan Básico Anual", 99.99),
    ("Plan Premium Anual", 299.99),
    ("Addon: Storage Extra 100GB", 4.99),
    ("Addon: Soporte Prioritario", 19.99),
    ("Formación Online", 149.99),
]


def generate_orders(customer_db_id: int, customer_is_vip: bool) -> list[dict]:
    """Genera pedidos aleatorios para un cliente."""
    num_orders = random.randint(1, 5) if not customer_is_vip else random.randint(3, 10)
    orders = []
    
    for i in range(num_orders):
        product_name, base_price = random.choice(PRODUCTS)
        quantity = random.randint(1, 3) if "Addon" in product_name else 1
        total = round(base_price * quantity, 2)
        
        # Fecha aleatoria en los últimos 365 días
        days_ago = random.randint(1, 365)
        order_date = datetime.now() - timedelta(days=days_ago)
        
        # Estado basado en antigüedad
        if days_ago < 3:
            status = random.choice(["pending", "processing"])
        elif days_ago < 14:
            status = random.choice(["processing", "shipped", "delivered"])
        else:
            status = random.choice(["delivered", "delivered", "delivered", "cancelled"])
        
        orders.append({
            "customer_id": customer_db_id,
            "order_id": f"ORD-{customer_db_id:03d}-{i+1:03d}",
            "product": product_name,
            "quantity": quantity,
            "total_amount": total,
            "status": status,
            "created_at": order_date.isoformat(),
        })
    
    return orders


# =============================================================================
# CONTENIDO DE KNOWLEDGE BASE
# =============================================================================

KNOWLEDGE_CONTENT = {
    "faq": {
        "como_resetear_password.md": """# ¿Cómo resetear mi contraseña?

## Proceso de recuperación de contraseña

Si has olvidado tu contraseña, sigue estos pasos:

1. Ve a la página de inicio de sesión
2. Haz clic en "¿Olvidaste tu contraseña?"
3. Introduce tu email registrado
4. Recibirás un enlace de recuperación (válido por 24 horas)
5. Haz clic en el enlace y crea una nueva contraseña

### Requisitos de la nueva contraseña
- Mínimo 8 caracteres
- Al menos una mayúscula
- Al menos un número
- Al menos un carácter especial (!@#$%^&*)

### ¿No recibes el email?
- Revisa tu carpeta de spam
- Verifica que el email sea correcto
- Contacta a soporte si el problema persiste
""",
        "como_cancelar_suscripcion.md": """# ¿Cómo cancelar mi suscripción?

## Proceso de cancelación

Puedes cancelar tu suscripción en cualquier momento:

1. Inicia sesión en tu cuenta
2. Ve a Configuración > Suscripción
3. Haz clic en "Cancelar suscripción"
4. Selecciona el motivo (opcional pero nos ayuda a mejorar)
5. Confirma la cancelación

### Importante
- La cancelación se hace efectiva al final del período de facturación actual
- No hay reembolsos por períodos parciales
- Tus datos se conservan 30 días por si cambias de opinión
- Puedes reactivar tu cuenta dentro de esos 30 días

### ¿Necesitas ayuda?
Contacta con nuestro equipo de soporte si tienes problemas.
""",
        "metodos_de_pago.md": """# Métodos de pago aceptados

## Tarjetas de crédito/débito
- Visa
- Mastercard
- American Express

## Otros métodos
- PayPal
- Transferencia bancaria (solo planes anuales Enterprise)
- Domiciliación SEPA (Europa)

## Facturación
- Mensual: cargo automático el día de contratación
- Anual: cargo único con 2 meses gratis

## Cambiar método de pago
1. Ve a Configuración > Facturación
2. Haz clic en "Actualizar método de pago"
3. Introduce los nuevos datos
4. El cambio se aplica en el siguiente ciclo

## Facturas
Todas las facturas están disponibles en PDF en tu panel de control.
""",
    },
    "policies": {
        "politica_devoluciones.md": """# Política de Devoluciones

## Garantía de satisfacción

Ofrecemos garantía de devolución de 30 días para todos los planes nuevos.

### Condiciones
- Aplicable solo a nuevos clientes
- Debe solicitarse dentro de los primeros 30 días
- El reembolso se procesa en 5-7 días hábiles
- Se reembolsa al método de pago original

### Excepciones
- Planes anuales ya usados más de 30 días
- Addons consumibles (como storage ya utilizado)
- Servicios de formación ya impartidos

### Cómo solicitar devolución
1. Contacta a soporte@empresa.com
2. Indica tu ID de cliente y motivo
3. Recibirás confirmación en 24-48 horas
4. El reembolso se procesa automáticamente

## Cancelaciones vs Devoluciones
- **Cancelación**: dejas de pagar, pero no hay reembolso
- **Devolución**: recuperas el dinero (solo primeros 30 días)
""",
        "politica_privacidad.md": """# Política de Privacidad

## Datos que recopilamos

### Datos de cuenta
- Nombre y apellidos
- Email
- Teléfono (opcional)
- Empresa (opcional)

### Datos de uso
- Acciones en la plataforma
- Preferencias de configuración
- Dispositivos utilizados

### Datos de pago
- Procesados por Stripe (PCI DSS compliant)
- No almacenamos números de tarjeta completos

## Cómo usamos tus datos
- Proporcionar el servicio contratado
- Enviar comunicaciones importantes
- Mejorar nuestros productos
- Cumplir obligaciones legales

## Tus derechos (RGPD)
- Acceso a tus datos
- Rectificación
- Supresión ("derecho al olvido")
- Portabilidad
- Oposición al tratamiento

## Contacto DPO
dpo@empresa.com
""",
        "terminos_servicio.md": """# Términos de Servicio

## 1. Aceptación
Al usar nuestro servicio, aceptas estos términos.

## 2. Descripción del servicio
Proporcionamos una plataforma SaaS para gestión empresarial.

## 3. Cuentas de usuario
- Debes proporcionar información veraz
- Eres responsable de tu contraseña
- Una cuenta por persona/empresa

## 4. Uso aceptable
### Prohibido:
- Compartir credenciales
- Uso para actividades ilegales
- Intentar acceder a datos de otros usuarios
- Realizar ingeniería inversa

## 5. Propiedad intelectual
Todo el contenido y código es propiedad de la empresa.

## 6. Limitación de responsabilidad
El servicio se proporciona "tal cual". No garantizamos disponibilidad 100%.

## 7. Modificaciones
Nos reservamos el derecho de modificar estos términos con aviso de 30 días.

## 8. Ley aplicable
Estos términos se rigen por la legislación española.
""",
    },
    "products": {
        "planes_y_precios.md": """# Planes y Precios

## Plan Básico
**€9.99/mes** o **€99.99/año** (2 meses gratis)

### Incluye:
- 5 usuarios
- 10 GB almacenamiento
- Soporte por email
- Funcionalidades básicas

---

## Plan Premium
**€29.99/mes** o **€299.99/año** (2 meses gratis)

### Incluye:
- 25 usuarios
- 100 GB almacenamiento
- Soporte prioritario (chat + email)
- Todas las funcionalidades
- Integraciones avanzadas
- Informes personalizados

---

## Plan Enterprise
**€99.99/mes** (contactar para precio anual)

### Incluye:
- Usuarios ilimitados
- 1 TB almacenamiento
- Soporte dedicado 24/7
- Account manager personal
- SLA 99.9%
- Onboarding personalizado
- API acceso completo

---

## Addons disponibles
- Storage Extra 100GB: €4.99/mes
- Soporte Prioritario: €19.99/mes
- Formación Online: €149.99 (pago único)

## Descuentos
- ONGs: 50% descuento
- Startups (<2 años): 30% primer año
- Educación: 40% descuento
""",
        "funcionalidades.md": """# Funcionalidades por Plan

## Comparativa de funcionalidades

| Funcionalidad | Básico | Premium | Enterprise |
|---------------|--------|---------|------------|
| Gestión de proyectos | ✓ | ✓ | ✓ |
| Calendario compartido | ✓ | ✓ | ✓ |
| Chat interno | - | ✓ | ✓ |
| Videoconferencia | - | ✓ | ✓ |
| Integraciones | 3 | 15 | Ilimitadas |
| API acceso | - | Lectura | Completo |
| SSO/SAML | - | - | ✓ |
| Auditoría avanzada | - | - | ✓ |
| Backup personalizado | - | - | ✓ |

## Integraciones disponibles
- Google Workspace
- Microsoft 365
- Slack
- Salesforce
- HubSpot
- Zapier
- Y más de 100 integraciones...

## Próximamente
- Integración con IA generativa
- App móvil nativa
- Modo offline
""",
    },
    "procedures": {
        "escalado_soporte.md": """# Procedimiento de Escalado de Soporte

## Niveles de soporte

### Nivel 1 - Soporte básico
- Consultas generales
- Problemas de acceso
- Guías de uso
- **Tiempo respuesta**: 24-48 horas

### Nivel 2 - Soporte técnico
- Problemas de configuración
- Errores de la plataforma
- Integraciones
- **Tiempo respuesta**: 4-8 horas

### Nivel 3 - Ingeniería
- Bugs críticos
- Problemas de rendimiento
- Incidencias de seguridad
- **Tiempo respuesta**: 1-2 horas

## Cuándo escalar

Escalar a Nivel 2 si:
- El problema no se resuelve con documentación
- Requiere acceso a configuración avanzada
- El cliente es VIP

Escalar a Nivel 3 si:
- Afecta a múltiples usuarios
- Implica pérdida de datos
- Es un problema de seguridad

## Proceso de escalado
1. Documentar el problema completamente
2. Recopilar logs relevantes
3. Notificar al siguiente nivel
4. Mantener al cliente informado
""",
        "onboarding_clientes.md": """# Procedimiento de Onboarding

## Nuevos clientes - Plan Básico/Premium

### Día 1: Bienvenida
- Email automático con credenciales
- Guía de inicio rápido (PDF)
- Enlace a videotutoriales

### Semana 1: Seguimiento
- Email de seguimiento automático
- Oferta de demo personalizada (Premium)

### Día 30: Check-in
- Encuesta de satisfacción
- Revisión de uso
- Recomendaciones personalizadas

---

## Nuevos clientes - Plan Enterprise

### Pre-onboarding
- Llamada de kick-off con Account Manager
- Definición de objetivos
- Planificación de migración

### Semana 1-2: Configuración
- Setup de SSO/SAML
- Configuración de integraciones
- Importación de datos

### Semana 3-4: Formación
- Sesiones de formación (hasta 3)
- Documentación personalizada
- Q&A con equipo técnico

### Mes 2-3: Adopción
- Seguimiento semanal
- Métricas de adopción
- Ajustes según feedback

### Ongoing
- Revisiones trimestrales
- Roadmap de producto
- Acceso a beta features
""",
    },
}


# =============================================================================
# FUNCIONES DE SETUP
# =============================================================================

def setup_crm_database():
    """Crea la base de datos CRM con datos de ejemplo."""
    print("📦 Creando base de datos CRM...")
    
    # Eliminar DB existente
    if CRM_DB_PATH.exists():
        CRM_DB_PATH.unlink()
    
    conn = sqlite3.connect(CRM_DB_PATH)
    cursor = conn.cursor()
    
    # Crear tablas
    cursor.execute("""
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT,
            company TEXT,
            is_vip BOOLEAN DEFAULT 0,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            order_id TEXT UNIQUE NOT NULL,
            product TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            total_amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
    """)
    
    # Crear índices
    cursor.execute("CREATE INDEX idx_customers_email ON customers(email)")
    cursor.execute("CREATE INDEX idx_customers_customer_id ON customers(customer_id)")
    cursor.execute("CREATE INDEX idx_orders_customer_id ON orders(customer_id)")
    
    # Insertar clientes
    for customer in CUSTOMERS:
        cursor.execute("""
            INSERT INTO customers (customer_id, name, email, phone, company, is_vip, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            customer["customer_id"],
            customer["name"],
            customer["email"],
            customer["phone"],
            customer["company"],
            customer["is_vip"],
            customer["notes"],
        ))
        
        customer_db_id = cursor.lastrowid
        
        # Generar y insertar pedidos
        orders = generate_orders(customer_db_id, customer["is_vip"])
        for order in orders:
            cursor.execute("""
                INSERT INTO orders (customer_id, order_id, product, quantity, total_amount, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                order["customer_id"],
                order["order_id"],
                order["product"],
                order["quantity"],
                order["total_amount"],
                order["status"],
                order["created_at"],
            ))
    
    conn.commit()
    conn.close()
    
    print(f"   ✅ CRM creado: {len(CUSTOMERS)} clientes")
    print(f"   📁 Ubicación: {CRM_DB_PATH}")


def setup_knowledge_base():
    """Crea la base de conocimiento con archivos Markdown."""
    print("\n📚 Creando base de conocimiento...")
    
    # Crear estructura de directorios
    for category in KNOWLEDGE_CONTENT.keys():
        category_path = KNOWLEDGE_BASE_PATH / category
        category_path.mkdir(parents=True, exist_ok=True)
    
    # Crear archivos
    total_files = 0
    for category, files in KNOWLEDGE_CONTENT.items():
        for filename, content in files.items():
            file_path = KNOWLEDGE_BASE_PATH / category / filename
            file_path.write_text(content, encoding="utf-8")
            total_files += 1
    
    print(f"   ✅ Knowledge base creada: {total_files} documentos")
    print(f"   📁 Ubicación: {KNOWLEDGE_BASE_PATH}")
    
    # Listar categorías
    print("   📂 Categorías:")
    for category in KNOWLEDGE_CONTENT.keys():
        num_files = len(KNOWLEDGE_CONTENT[category])
        print(f"      - {category}: {num_files} archivos")


def main():
    """Ejecuta el setup completo."""
    print("=" * 60)
    print("AGENTE IA - Setup de Datos de Simulación")
    print("=" * 60)
    
    # Crear directorio data si no existe
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Setup CRM
    setup_crm_database()
    
    # Setup Knowledge Base
    setup_knowledge_base()
    
    print("\n" + "=" * 60)
    print("✅ Setup completado exitosamente!")
    print("=" * 60)
    print("\nPróximos pasos:")
    print("  1. Configura tu .env con ANTHROPIC_API_KEY")
    print("  2. Ejecuta: python -m src.cli")
    print("  3. O inicia el servidor: uvicorn src.main:app --reload")


if __name__ == "__main__":
    main()