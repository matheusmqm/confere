"""Configuração da aplicação, lida de variáveis de ambiente e do `.env` da raiz."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ = Path(__file__).resolve().parents[4]
SEGREDO_SESSAO_PADRAO = "dev-somente-local-troque-em-producao"
URL_LOCAL = "postgresql+psycopg://confere:confere@localhost:5432/confere"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=RAIZ / ".env", extra="ignore")

    env: Literal["local", "test", "demo"] = "local"

    database_url: SecretStr = SecretStr(URL_LOCAL)
    database_url_worker: SecretStr = SecretStr(URL_LOCAL)

    storage_backend: Literal["local", "supabase"] = "local"
    storage_local_dir: str = ".storage"
    s3_endpoint_url: str = ""
    s3_region: str = ""
    s3_access_key_id: SecretStr = SecretStr("")
    s3_secret_access_key: SecretStr = SecretStr("")
    s3_bucket: str = "documentos"
    s3_prefix: str = "dev/"
    supabase_url: str = ""
    supabase_service_role_key: SecretStr = SecretStr("")

    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-flash-latest"
    gemini_embed_model: str = "gemini-embedding-001"
    llm_provider: Literal["gemini", "openrouter"] = "gemini"
    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_model: str = "nvidia/nemotron-3.5-super-vl:free"
    openrouter_model_fallback: str = "google/gemma-4-31b-it:free"
    llm_cache_dir: str = "data/llm_cache"
    llm_offline: bool = False

    session_secret: SecretStr = SecretStr(SEGREDO_SESSAO_PADRAO)
    demo_mode: bool = False
    ptax_offline: bool = False
    next_public_api_url: str = "http://localhost:8000"
    sentry_dsn: str = ""

    def _segredo_de_sessao_informado(self) -> str:
        """Em `demo` o segredo padrão de desenvolvimento não vale: exige um valor próprio."""
        valor = self.session_secret.get_secret_value()
        return "" if valor in ("", SEGREDO_SESSAO_PADRAO) else valor

    @model_validator(mode="after")
    def _exigir_chaves_na_demo(self) -> "Settings":
        if self.env != "demo":
            return self
        valores = {
            "SUPABASE_SERVICE_ROLE_KEY": self.supabase_service_role_key.get_secret_value(),
            "S3_ENDPOINT_URL": self.s3_endpoint_url,
            "S3_REGION": self.s3_region,
            "S3_ACCESS_KEY_ID": self.s3_access_key_id.get_secret_value(),
            "S3_SECRET_ACCESS_KEY": self.s3_secret_access_key.get_secret_value(),
            "SESSION_SECRET": self._segredo_de_sessao_informado(),
        }
        if self.llm_provider == "openrouter":
            valores["OPENROUTER_API_KEY"] = self.openrouter_api_key.get_secret_value()
        else:
            valores["GEMINI_API_KEY"] = self.gemini_api_key.get_secret_value()
        faltantes = [nome for nome, valor in valores.items() if not valor.strip()]
        if faltantes:
            raise ValueError("ENV=demo exige variáveis não definidas: " + ", ".join(faltantes))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
