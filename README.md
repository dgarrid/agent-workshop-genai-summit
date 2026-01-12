# Creando un Agente con arquitectura de producción en 3 horas

![Python](https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker)
![MCP](https://img.shields.io/badge/Protocol-MCP-orange?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Production%20Grade-green?style=for-the-badge)

> **Workshop Oficial — GenAI Summit 2026**  
> *Arquitectura de Agentes Auditables en Producción*

---

## Propósito

La mayoría de los agentes de IA fallan en producción por tres razones:

| Problema | Descripción |
|----------|-------------|
| ❌ **Indeterminismo** | Respuestas impredecibles o alucinaciones |
| ❌ **Costes descontrolados** | Bucles infinitos que queman presupuesto |
| ❌ **Opacidad** | Cajas negras inauditables para negocio o legal |

La metoología presentada en este taller resuelve estos problemas mediante un enfoque de **Defensa en Profundidad**:

1. **Validación Estricta** — Uso de `Pydantic` para garantizar contratos de datos en entrada y salida
2. **Estándar de Herramientas** — Implementación del **Model Context Protocol (MCP)** para desacoplar la lógica del LLM de las integraciones
3. **Gobernanza Financiera** — Orquestador con presupuesto (€) en tiempo real y logs de auditoría estructurados
4. **Despliegue Inmutable** — Containerización con Docker para despliegue serverless

---

## Estructura del Proyecto

Arquitectura hexagonal simplificada para separar infraestructura, dominio e interfaces.

```
agente/
│
├── .devcontainer/          # Configuración para GitHub Codespaces
│
├── data/                   # SIMULACIÓN DEL ENTORNO CORPORATIVO
│   ├── crm.db              # SQLite simulando un CRM Enterprise
│   ├── setup_data.py       # Script para resetear la simulación
│   └── knowledge/          # Base de conocimiento (Markdown para RAG)
│
├── src/                    # CÓDIGO FUENTE
│   ├── core/               # EL CEREBRO (Gobernanza)
│   │   ├── agent.py        # BudgetedOrchestrator: bucle de ejecución controlado
│   │   └── audit.py        # AuditLogger: trazas y logs estructurados
│   │
│   ├── models/             # LOS CONTRATOS
│   │   ├── incoming.py     # Sanitización de inputs (Emails, Webhooks)
│   │   └── decision.py     # Estructura determinista de salida (NexusDecision)
│   │
│   ├── tools/              # LAS MANOS (MCP)
│   │   ├── crm.py          # Acceso a BBDD (Read-Only)
│   │   ├── knowledge.py    # Lectura de archivos segura
│   │   └── registry.py     # Definiciones JSON Schema para el LLM
│   │
│   ├── main.py             # LA PUERTA (API FastAPI)
│   └── config.py           # Gestión de Secretos (.env)
│
├── infra/                  # DESPLIEGUE
│   └── Dockerfile          # Definición inmutable del entorno
│
├── .env.example            # Plantilla de variables de entorno
├── requirements.txt        # Dependencias congeladas
└── README.md
```

---

## Stack Tecnológico

| Tecnología | Propósito |
|------------|-----------|
| **Python 3.11** | Runtime principal |
| **Pydantic V2** | Convierte el caos probabilístico del LLM en objetos Python validados |
| **Anthropic SDK** | Control a bajo nivel de Claude 3.5 Sonnet (sin abstracciones tipo LangChain) |
| **MCP** | Herramientas reutilizables con cualquier modelo o cliente |
| **FastAPI** | Microservicio asíncrono de alto rendimiento |
| **Rich** | Logs visuales para depurar latencia y costes en tiempo real |
| **Docker** | Despliegues serverless reproducibles |

---

## Inicio Rápido

### Requisitos Previos

- Docker Desktop instalado y corriendo
- Python 3.10+
- API Key de Anthropic (con créditos disponibles)

### Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/mentorenia/genAISummitWorkshop.git
cd genAISummitWorkshop

# 2. Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar entorno
cp .env.example .env
# Edita .env y añade tu ANTHROPIC_API_KEY
```

### Inicializar la Simulación

Antes de ejecutar el agente, crea el "Mundo Falso" (CRM y archivos):

```bash
python data/setup_data.py
```

```
✅ CRM Simulado creado...
✅ Base de Conocimiento creada...
```

---

## Uso

### Fase 1: CLI (Desarrollo)

Ver logs de costes y trazas en tiempo real:

```bash
python -m src.cli
```

### Fase 2: API (Producción)

Levantar el servidor FastAPI:

```bash
uvicorn src.main:app --reload
```

Documentación automática en: `http://localhost:8000/docs`

### Fase 3: Docker (Cloud)

```bash
# Construir imagen
docker build -t nexus-agent -f infra/Dockerfile .

# Ejecutar contenedor
docker run -p 8080:8080 -e ANTHROPIC_API_KEY=tu-key nexus-agent
```

---

## Escenarios de Prueba

Stress tests para validar la robustez del sistema:

| # | Escenario | Herramienta | Resultado Esperado |
|---|-----------|-------------|-------------------|
| 1 | Email solicitando información de soporte | Knowledge Base | ✅ Respuesta correcta |
| 2 | Email pidiendo estatus VIP de cliente | CRM | ✅ Consulta exitosa |
| 3 | **Ataque de inyección** (`../../etc/passwd`) | — | 🛡️ Bloqueado |
| 4 | Email pidiendo tarea infinita | — | 💰 BudgetLimiter mata el proceso |

---

## Roadmap del Taller (3 Horas)

| Tiempo | Módulo | Contenido |
|--------|--------|-----------|
| 00:00 - 01:00 | Arquitectura & Contratos | Diseño del sistema y validación con Pydantic |
| 01:00 - 02:00 | Manos a la Obra (MCP) | Implementación de tools (CRM/Docs) y servidor MCP |
| 02:00 - 03:00 | Control & Despliegue | Orquestador con presupuesto, logs de auditoría y containerización |

---

## Licencia

MIT © 2026 — GenAI Summit Workshop
