"""
Gestión de configuración y secretos para Nexus Agent.

Este módulo centraliza:
- Carga segura de variables de entorno
- Precios de modelos Anthropic (para estimación de costes)
- Validación de configuración al arrancar
"""

from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


# =============================================================================
# PRECIOS DE MODELOS ANTHROPIC
# =============================================================================
# Fuente: https://docs.anthropic.com/en/docs/about-claude/pricing
# Última actualización: Enero 2026
#
# NOTA: Anthropic no ofrece API para obtener precios programáticamente.
# Estos valores son para ESTIMACIÓN del budget limiter.
# El coste real se calcula desde usage.input_tokens/output_tokens en cada respuesta.
# =============================================================================

MODEL_PRICING_USD_PER_MTOK = {
    # Claude 4.5 Series (Noviembre 2025)
    "claude-opus-4-5-20251101": {"input": 5.00, "output": 25.00},
    "claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    
    # Claude 4 Series (Legacy - mantener para compatibilidad)
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    
    # Aliases (para facilitar uso)
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "claude-opus-4-5": {"input": 5.00, "output": 25.00},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.00},
}

# Modelo por defecto si no se especifica
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"


# =============================================================================
# CONFIGURACIÓN PRINCIPAL
# =============================================================================

class Settings(BaseSettings):
    """
    Configuración centralizada del agente.
    
    Carga automáticamente desde:
    1. Variables de entorno
    2. Archivo .env (si existe)
    
    Valida tipos y rangos al instanciar.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # -------------------------------------------------------------------------
    # Anthropic API
    # -------------------------------------------------------------------------
    anthropic_api_key: str = Field(
        ...,  # Requerido
        description="API key de Anthropic (empieza con sk-ant-)",
        min_length=10,
    )
    
    anthropic_model: str = Field(
        default=DEFAULT_MODEL,
        description="Modelo de Claude a utilizar",
    )
    
    # -------------------------------------------------------------------------
    # Gobernanza Financiera
    # -------------------------------------------------------------------------
    budget_limit_eur: float = Field(
        default=5.00,
        ge=0.01,
        le=1000.00,
        description="Presupuesto máximo por sesión en EUR",
    )
    
    eur_usd_rate: float = Field(
        default=1.08,
        ge=0.50,
        le=2.00,
        description="Tipo de cambio EUR/USD para conversión",
    )
    
    # -------------------------------------------------------------------------
    # Límites del Agente
    # -------------------------------------------------------------------------
    max_iterations: int = Field(
        default=25,
        ge=1,
        le=100,
        description="Máximo de iteraciones del bucle agente",
    )
    
    api_timeout_seconds: int = Field(
        default=120,
        ge=10,
        le=600,
        description="Timeout por llamada API en segundos",
    )
    
    # -------------------------------------------------------------------------
    # Paths
    # -------------------------------------------------------------------------
    crm_database_path: Path = Field(
        default=Path("data/crm.db"),
        description="Ruta a la base de datos CRM",
    )
    
    knowledge_base_path: Path = Field(
        default=Path("data/knowledge"),
        description="Ruta a la base de conocimiento",
    )
    
    audit_log_path: Path = Field(
        default=Path("logs/audit"),
        description="Directorio para logs de auditoría",
    )
    
    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------
    log_level: str = Field(
        default="INFO",
        pattern="^(DEBUG|INFO|WARNING|ERROR)$",
        description="Nivel de logging",
    )
    
    # -------------------------------------------------------------------------
    # Validadores
    # -------------------------------------------------------------------------
    @field_validator("anthropic_api_key")
    @classmethod
    def validate_api_key_format(cls, v: str) -> str:
        """Valida que la API key tenga formato correcto."""
        if not v.startswith("sk-ant-"):
            raise ValueError(
                "La API key de Anthropic debe empezar con 'sk-ant-'. "
                "Obtén tu key en https://console.anthropic.com/"
            )
        return v
    
    @field_validator("anthropic_model")
    @classmethod
    def validate_model_has_pricing(cls, v: str) -> str:
        """Valida que tengamos precios para el modelo seleccionado."""
        if v not in MODEL_PRICING_USD_PER_MTOK:
            available = ", ".join(MODEL_PRICING_USD_PER_MTOK.keys())
            raise ValueError(
                f"Modelo '{v}' no tiene precios configurados. "
                f"Modelos disponibles: {available}"
            )
        return v
    
    # -------------------------------------------------------------------------
    # Propiedades calculadas
    # -------------------------------------------------------------------------
    @property
    def budget_limit_usd(self) -> float:
        """Presupuesto en USD (para cálculos internos)."""
        return self.budget_limit_eur * self.eur_usd_rate
    
    @property
    def model_pricing(self) -> dict[str, float]:
        """Precios del modelo actual (input/output por MTok)."""
        return MODEL_PRICING_USD_PER_MTOK[self.anthropic_model]
    
    def estimate_cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        """
        Estima el coste en USD para un número de tokens.
        
        Args:
            input_tokens: Tokens de entrada (prompt)
            output_tokens: Tokens de salida (respuesta)
            
        Returns:
            Coste estimado en USD
        """
        pricing = self.model_pricing
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost
    
    def estimate_cost_eur(self, input_tokens: int, output_tokens: int) -> float:
        """Estima el coste en EUR para un número de tokens."""
        return self.estimate_cost_usd(input_tokens, output_tokens) / self.eur_usd_rate


@lru_cache
def get_settings() -> Settings:
    """
    Obtiene la configuración (singleton cacheado).
    
    Uso:
        from src.config import get_settings
        settings = get_settings()
        print(settings.anthropic_model)
    """
    return Settings()


# =============================================================================
# VALIDACIÓN AL IMPORTAR
# =============================================================================

def validate_environment() -> None:
    """
    Valida que el entorno esté correctamente configurado.
    
    Lanza excepción con mensaje descriptivo si falta algo.
    Llamar al arrancar la aplicación.
    """
    try:
        settings = get_settings()
        
        # Verificar que los paths existan o se puedan crear
        settings.audit_log_path.mkdir(parents=True, exist_ok=True)
        
        # Log de configuración cargada (sin exponer secretos)
        masked_key = settings.anthropic_api_key[:12] + "..." + settings.anthropic_api_key[-4:]
        
        return {
            "status": "ok",
            "model": settings.anthropic_model,
            "budget_eur": settings.budget_limit_eur,
            "max_iterations": settings.max_iterations,
            "api_key_masked": masked_key,
        }
        
    except Exception as e:
        raise EnvironmentError(
            f"Error de configuración: {e}\n"
            f"Asegúrate de copiar .env.example a .env y configurar las variables."
        ) from e