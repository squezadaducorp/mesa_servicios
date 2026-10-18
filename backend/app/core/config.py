"""Configuración por variables de entorno (ver .env.example)."""
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Aplicación
    APP_NAME: str = "Mesa de Servicios ADUCORP"
    APP_ENV: str = "development"            # development | production
    APP_URL: str = "http://localhost:8080"  # URL pública del frontend (enlaces en correos)
    API_PREFIX: str = "/api/v1"
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://localhost:8080"])
    LOG_LEVEL: str = "INFO"
    DOCS_ENABLED: bool = True               # Swagger/ReDoc; puede apagarse en producción
    # Solo se confía en X-Forwarded-For / X-Real-IP cuando la conexión viene de estos proxies (Nginx)
    TRUSTED_PROXIES: list[str] = Field(default_factory=lambda: ["127.0.0.1/32", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"])

    # Base de datos
    DATABASE_URL: str = "sqlite:///./aducorp_dev.db"
    DB_POOL_SIZE: int = 10
    DB_ECHO: bool = False

    # Seguridad
    JWT_SECRET: str = "cambie-esta-clave-en-produccion-con-64-caracteres-aleatorios!!"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = 15
    REFRESH_TOKEN_DAYS: int = 7
    MAX_LOGIN_INTENTOS: int = 5
    BLOQUEO_MINUTOS: int = 15
    CLAVE_MIN_LONGITUD: int = 10
    LOGIN_MAX_POR_MINUTO: int = 10          # intentos de login por IP y minuto (por proceso; Nginx aplica otro límite)

    # Autenticación: local | ldap  (Active Directory)
    AUTH_PROVIDER: str = "local"
    LDAP_URL: str = ""                      # ldaps://dc01.aducorp.local:636
    LDAP_DOMINIO: str = ""                  # ADUCORP  (para bind DOMINIO\\usuario)
    LDAP_BASE_DN: str = ""                  # DC=aducorp,DC=local
    LDAP_USUARIO_SERVICIO: str = ""
    LDAP_CLAVE_SERVICIO: str = ""
    LDAP_CREAR_USUARIOS: bool = True        # alta automática con rol Cliente interno
    LDAP_GRUPO_ROLES: dict[str, str] = Field(default_factory=dict)   # {"CN=Mesa-Admin,...": "ADMIN_MESA"}

    # Correo
    EMAIL_ENABLED: bool = False             # False = los correos quedan en cola marcados como simulados
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_STARTTLS: bool = True
    SMTP_FROM: str = "Mesa de Servicios ADUCORP <mesa.servicios@aducorp.com.ec>"

    # Adjuntos
    STORAGE_PATH: str = "./data/adjuntos"
    ADJUNTOS_MAX_MB: int = 20
    ADJUNTOS_EXTENSIONES: str = "pdf,doc,docx,xls,xlsx,csv,jpg,jpeg,png,txt,xml,zip,msg,eml"

    # IA: local | llm
    AI_PROVIDER: str = "local"
    ANTHROPIC_API_KEY: str = ""
    AI_MODEL: str = "claude-opus-5-5"

    # Worker
    WORKER_INTERVALO_SEG: int = 60
    ZONA_HORARIA: str = "America/Guayaquil"

    @model_validator(mode="after")
    def _validar_produccion(self):
        if self.APP_ENV == "production":
            if len(self.JWT_SECRET) < 32 or self.JWT_SECRET.startswith("cambie-esta-clave"):
                raise ValueError("JWT_SECRET debe definirse con al menos 32 caracteres aleatorios en producción")
            if self.DATABASE_URL.startswith("sqlite"):
                raise ValueError("En producción DATABASE_URL debe apuntar a SQL Server")
        return self

    @property
    def es_produccion(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
