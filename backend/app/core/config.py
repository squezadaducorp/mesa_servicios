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

    # Microsoft 365 · aplicación registrada en Entra ID (una sola app para SSO, Graph y el bot de Teams)
    M365_TENANT_ID: str = ""                # GUID del inquilino de Aducorp
    M365_CLIENT_ID: str = ""                # Id. de aplicación (cliente)
    M365_CLIENT_SECRET: str = ""            # secreto de cliente
    M365_AUTHORITY: str = "https://login.microsoftonline.com"
    GRAPH_URL: str = "https://graph.microsoft.com/v1.0"

    # Entra ID (AUTH_PROVIDER=entra): SSO OIDC; el MFA lo exige el Acceso Condicional de Entra
    ENTRA_REDIRECT_URI: str = ""            # vacío = {APP_URL}/api/v1/auth/entra/callback
    ENTRA_GRUPO_ROLES: dict[str, str] = Field(default_factory=dict)   # {"<id del grupo>": "ADMIN_MESA"}
    ENTRA_ROL_DEFECTO: str = "CLIENTE"      # rol si el usuario no está en ningún grupo mapeado ("" = denegar acceso)
    ENTRA_EXIGIR_MFA: bool = False          # rechaza tokens sin "mfa" en el claim amr (además del Acceso Condicional)
    ENTRA_CUENTAS_EMERGENCIA: list[str] = Field(default_factory=list)  # cuentas locales permitidas con AUTH_PROVIDER=entra
    ENTRA_SYNC_MINUTOS: int = 60            # sincronización de grupos por Graph (0 = solo al iniciar sesión)

    # Exchange Online: buzón compartido leído y enviado por Microsoft Graph
    BUZON_ENABLED: bool = False
    BUZON_CORREO: str = "soporte@aducorp.com.ec"
    BUZON_DOMINIOS_INTERNOS: list[str] = Field(default_factory=lambda: ["aducorp.com.ec"])
    BUZON_LOTE: int = 25
    EMAIL_TRANSPORTE: str = "smtp"          # smtp | graph (envía desde BUZON_CORREO)

    # Microsoft Teams: bot de Azure Bot Service (mismo Id. de aplicación)
    TEAMS_ENABLED: bool = False
    TEAMS_BOT_ID: str = ""                  # vacío = M365_CLIENT_ID
    TEAMS_EVENTOS: list[str] = Field(default_factory=lambda: [
        "TICKET_CREADO", "TICKET_ASIGNADO", "TICKET_ESCALADO", "SLA_75", "SLA_90", "SLA_VENCIDO", "TICKET_CERRADO"])

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

    @property
    def m365_configurado(self) -> bool:
        return bool(self.M365_TENANT_ID and self.M365_CLIENT_ID and self.M365_CLIENT_SECRET)

    @property
    def entra_activo(self) -> bool:
        return self.AUTH_PROVIDER == "entra" and self.m365_configurado

    @property
    def entra_redirect_uri(self) -> str:
        return self.ENTRA_REDIRECT_URI or f"{self.APP_URL.rstrip('/')}{self.API_PREFIX}/auth/entra/callback"

    @property
    def teams_bot_id(self) -> str:
        return self.TEAMS_BOT_ID or self.M365_CLIENT_ID


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
