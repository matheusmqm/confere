"""Settings: defaults seguros, validação do modo demo e ausência de vazamento de segredos."""

import pytest
from pydantic import ValidationError

from confere_api.settings import Settings

SEGREDOS = {
    "DATABASE_URL": "postgresql+psycopg://u:segredo-db-api@h:6543/d",
    "DATABASE_URL_WORKER": "postgresql+psycopg://u:segredo-db-worker@h:5432/d",
    "S3_ACCESS_KEY_ID": "segredo-s3-id",
    "S3_SECRET_ACCESS_KEY": "segredo-s3-chave",
    "SUPABASE_SERVICE_ROLE_KEY": "segredo-supabase",
    "GEMINI_API_KEY": "segredo-gemini",
}
DEMO = {
    "ENV": "demo",
    "S3_ENDPOINT_URL": "https://exemplo.supabase.co/storage/v1/s3",
    "S3_REGION": "us-east-2",
}


@pytest.fixture(autouse=True)
def ambiente_limpo(monkeypatch: pytest.MonkeyPatch) -> None:
    for nome in Settings.model_fields:
        monkeypatch.delenv(nome.upper(), raising=False)


def carregar() -> Settings:
    return Settings(_env_file=None)


def test_env_minimo_usa_defaults_seguros(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "test")
    s = carregar()
    assert s.env == "test"
    assert s.storage_backend == "local"
    assert s.llm_offline is False
    assert s.demo_mode is False
    assert "localhost" in s.database_url.get_secret_value()


def test_defaults_sem_nenhuma_variavel() -> None:
    s = carregar()
    assert s.env == "local"
    assert s.storage_backend == "local"
    assert s.s3_bucket == "documentos"


def test_demo_sem_chaves_lista_as_faltantes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "demo")
    with pytest.raises(ValidationError) as erro:
        carregar()
    mensagem = str(erro.value)
    for nome in (
        "SUPABASE_SERVICE_ROLE_KEY",
        "S3_ENDPOINT_URL",
        "S3_REGION",
        "S3_ACCESS_KEY_ID",
        "S3_SECRET_ACCESS_KEY",
        "GEMINI_API_KEY",
    ):
        assert nome in mensagem


def test_demo_lista_so_o_que_falta(monkeypatch: pytest.MonkeyPatch) -> None:
    for nome, valor in {**DEMO, **SEGREDOS}.items():
        monkeypatch.setenv(nome, valor)
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with pytest.raises(ValidationError) as erro:
        carregar()
    mensagem = str(erro.value)
    assert "GEMINI_API_KEY" in mensagem
    assert "SUPABASE_SERVICE_ROLE_KEY" not in mensagem


def test_demo_completo_carrega(monkeypatch: pytest.MonkeyPatch) -> None:
    for nome, valor in {**DEMO, **SEGREDOS}.items():
        monkeypatch.setenv(nome, valor)
    assert carregar().env == "demo"


def test_repr_nao_vaza_segredos(monkeypatch: pytest.MonkeyPatch) -> None:
    for nome, valor in {**DEMO, **SEGREDOS}.items():
        monkeypatch.setenv(nome, valor)
    s = carregar()
    texto = repr(s) + str(s)
    for valor in SEGREDOS.values():
        assert valor not in texto
    assert "segredo-db" not in texto
