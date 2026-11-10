"""Storage: validação de caminho, backend local, backend Supabase (com fakes) e seleção."""

import io
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from botocore.exceptions import ClientError
from pydantic import SecretStr

from confere_api.settings import Settings
from confere_api.storage import (
    LocalStorage,
    SupabaseStorage,
    build_storage,
    segredo_local,
    validar_caminho,
    verify_local_signature,
)

SEGREDO = b"segredo-de-teste"
ASSINADA = "/object/sign/documentos/dev/emp/a.pdf?token=abc"


@pytest.mark.parametrize(
    "path", ["", "/abs.pdf", "a/../b", "..", "a//b", "a/./b", "a\\b", "a\x00b"]
)
def test_caminho_invalido(path: str) -> None:
    with pytest.raises(ValueError):
        validar_caminho(path)


@pytest.mark.parametrize("path", ["a.pdf", "empresa/abc123.pdf", "a/b/c.txt"])
def test_caminho_valido(path: str) -> None:
    assert validar_caminho(path) == path


def test_prefixo_aceita_barra_final() -> None:
    assert validar_caminho("empresa/", permitir_barra_final=True) == "empresa/"
    with pytest.raises(ValueError):
        validar_caminho("empresa/")


# ---------------------------------------------------------------- local


@pytest.fixture
def local(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path, prefix="dev/", secret=SEGREDO)


def test_local_put_get_exists_com_prefixo(local: LocalStorage, tmp_path: Path) -> None:
    assert not local.exists("emp/a.pdf")
    local.put("emp/a.pdf", b"conteudo", "application/pdf")
    assert local.exists("emp/a.pdf")
    assert local.get("emp/a.pdf") == b"conteudo"
    assert (tmp_path / "dev" / "emp" / "a.pdf").read_bytes() == b"conteudo"


def test_local_get_inexistente(local: LocalStorage) -> None:
    with pytest.raises(FileNotFoundError):
        local.get("nao/existe.pdf")


@pytest.mark.parametrize("metodo", ["put", "get", "exists", "signed_url"])
def test_local_rejeita_caminho_perigoso(local: LocalStorage, metodo: str) -> None:
    args: tuple[Any, ...] = ("../fora.pdf", b"x", "text/plain") if metodo == "put" else ("../x",)
    with pytest.raises(ValueError):
        getattr(local, metodo)(*args)


def test_local_delete_prefix(local: LocalStorage) -> None:
    for p in ("emp1/a.pdf", "emp1/b.pdf", "emp2/c.pdf"):
        local.put(p, b"x", "application/pdf")
    assert local.delete_prefix("emp1/") == 2
    assert not local.exists("emp1/a.pdf")
    assert local.exists("emp2/c.pdf")
    assert local.delete_prefix("emp1/") == 0


def test_local_url_assinada_valida(local: LocalStorage) -> None:
    url = local.signed_url("emp/a b.pdf", expires_in=60)
    partes = urlparse(url)
    assert partes.path == "/arquivos-locais/emp/a%20b.pdf"
    q = parse_qs(partes.query)
    exp, sig = int(q["exp"][0]), q["sig"][0]
    assert verify_local_signature("emp/a b.pdf", exp, sig, secret=SEGREDO)


def test_local_assinatura_adulterada_ou_expirada(local: LocalStorage) -> None:
    q = parse_qs(urlparse(local.signed_url("emp/a.pdf", expires_in=60)).query)
    exp, sig = int(q["exp"][0]), q["sig"][0]
    assert not verify_local_signature("emp/outro.pdf", exp, sig, secret=SEGREDO)
    assert not verify_local_signature("emp/a.pdf", exp + 1, sig, secret=SEGREDO)
    assert not verify_local_signature("emp/a.pdf", exp, sig, secret=b"outro")
    assert not verify_local_signature("emp/a.pdf", exp, sig, secret=SEGREDO, now=exp + 1)
    assert not verify_local_signature("../a.pdf", exp, sig, secret=SEGREDO)


# ------------------------------------------------------------- supabase


def _erro(codigo: str) -> ClientError:
    return ClientError({"Error": {"Code": codigo, "Message": "x"}}, "Op")


class FakeS3:
    def __init__(self) -> None:
        self.objetos: dict[str, bytes] = {}
        self.tipos: dict[str, str] = {}
        self.bucket_usado: set[str] = set()

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        self.bucket_usado.add(Bucket)
        self.objetos[Key] = Body
        self.tipos[Key] = ContentType

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self.objetos:
            raise _erro("NoSuchKey")
        return {"Body": io.BytesIO(self.objetos[Key])}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self.objetos:
            raise _erro("404")
        return {}

    def get_paginator(self, nome: str) -> "FakeS3":
        assert nome == "list_objects_v2"
        return self

    def paginate(self, *, Bucket: str, Prefix: str) -> list[dict[str, Any]]:
        chaves = [k for k in self.objetos if k.startswith(Prefix)]
        return [
            {"Contents": [{"Key": k} for k in chaves[:1]]},
            {"Contents": [{"Key": k} for k in chaves[1:]]},
        ]

    def delete_objects(self, *, Bucket: str, Delete: dict[str, Any]) -> None:
        for o in Delete["Objects"]:
            del self.objetos[o["Key"]]


def _settings(**extra: Any) -> Settings:
    return Settings(
        _env_file=None,
        storage_backend="supabase",
        s3_prefix="dev/",
        s3_bucket="documentos",
        s3_endpoint_url="https://ref.supabase.co/storage/v1/s3",
        s3_region="us-east-2",
        s3_access_key_id=SecretStr("id"),
        s3_secret_access_key=SecretStr("chave"),
        supabase_url="https://ref.supabase.co/",
        supabase_service_role_key=SecretStr("service-role-teste"),
        **extra,
    )


def test_supabase_aplica_prefixo_e_roundtrip() -> None:
    s3 = FakeS3()
    st = SupabaseStorage(_settings(), client=s3)  # type: ignore[arg-type]
    st.put("emp/a.pdf", b"dados", "application/pdf")
    assert list(s3.objetos) == ["dev/emp/a.pdf"]
    assert s3.tipos["dev/emp/a.pdf"] == "application/pdf"
    assert st.exists("emp/a.pdf")
    assert not st.exists("emp/b.pdf")
    assert st.get("emp/a.pdf") == b"dados"
    with pytest.raises(FileNotFoundError):
        st.get("emp/b.pdf")


def test_supabase_erro_diferente_de_nao_encontrado_propaga() -> None:
    class Quebrado(FakeS3):
        def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
            raise _erro("AccessDenied")

    st = SupabaseStorage(_settings(), client=Quebrado())  # type: ignore[arg-type]
    with pytest.raises(ClientError):
        st.exists("emp/a.pdf")


def test_supabase_rejeita_caminho_perigoso() -> None:
    st = SupabaseStorage(_settings(), client=FakeS3())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        st.put("../x", b"", "text/plain")


def test_supabase_delete_prefix() -> None:
    s3 = FakeS3()
    st = SupabaseStorage(_settings(), client=s3)  # type: ignore[arg-type]
    for p in ("emp1/a.pdf", "emp1/b.pdf", "emp2/c.pdf"):
        st.put(p, b"x", "application/pdf")
    assert st.delete_prefix("emp1/") == 2
    assert list(s3.objetos) == ["dev/emp2/c.pdf"]


def test_supabase_url_assinada() -> None:
    visto: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        visto["url"] = str(req.url)
        visto["auth"] = req.headers["Authorization"]
        visto["corpo"] = json.loads(req.content)
        return httpx.Response(
            200, json={"signedURL": "/object/sign/documentos/dev/emp/a.pdf?token=abc"}
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    st = SupabaseStorage(_settings(), client=FakeS3(), http=http)  # type: ignore[arg-type]
    url = st.signed_url("emp/a.pdf", expires_in=120)
    assert visto["url"] == "https://ref.supabase.co/storage/v1/object/sign/documentos/dev/emp/a.pdf"
    assert visto["auth"] == "Bearer service-role-teste"
    assert visto["corpo"] == {"expiresIn": 120}
    assert (
        url == "https://ref.supabase.co/storage/v1/object/sign/documentos/dev/emp/a.pdf?token=abc"
    )


def test_supabase_url_assinada_erro_http() -> None:
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(400, json={})))
    st = SupabaseStorage(_settings(), client=FakeS3(), http=http)  # type: ignore[arg-type]
    with pytest.raises(httpx.HTTPStatusError):
        st.signed_url("emp/a.pdf")


# ------------------------------------------------------------ seleção


def test_build_storage_escolhe_pelo_backend(tmp_path: Path) -> None:
    local = build_storage(Settings(_env_file=None, storage_local_dir=str(tmp_path)))
    assert isinstance(local, LocalStorage)
    assert isinstance(build_storage(_settings()), SupabaseStorage)


def test_segredo_local_deriva_da_service_role() -> None:
    sem_chave = segredo_local(Settings(_env_file=None))
    com_chave = segredo_local(Settings(_env_file=None, supabase_service_role_key=SecretStr("k")))
    assert sem_chave != com_chave
    assert len(com_chave) == 32
