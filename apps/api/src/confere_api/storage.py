"""Armazenamento de arquivos: backend local (disco) e Supabase Storage (S3 + REST).

Todo `path` recebido é lógico (ex. `empresa_id/sha256.pdf`); o prefixo `S3_PREFIX`
(ex. `dev/`) é aplicado internamente por cada backend.
"""

import hashlib
import hmac
import time
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import quote

import boto3
import httpx
from botocore.config import Config
from botocore.exceptions import ClientError

from confere_api.settings import Settings, get_settings

if TYPE_CHECKING:
    from types_boto3_s3.client import S3Client

ROTA_LOCAL = "/arquivos-locais"
SEGREDO_LOCAL_PADRAO = b"confere-local-dev"  # só para dev/teste sem service role key
_CODIGOS_NAO_ENCONTRADO = {"404", "NoSuchKey", "NotFound"}


class Storage(Protocol):
    def put(self, path: str, data: bytes, content_type: str) -> None: ...

    def get(self, path: str) -> bytes: ...

    def exists(self, path: str) -> bool: ...

    def signed_url(self, path: str, expires_in: int = 300) -> str: ...

    def delete_prefix(self, prefix: str) -> int: ...


def validar_caminho(path: str, *, permitir_barra_final: bool = False) -> str:
    """Rejeita caminhos vazios, absolutos, com `..`, `\\` ou NUL."""
    if not path or "\x00" in path or "\\" in path:
        raise ValueError(f"caminho inválido: {path!r}")
    if path.startswith("/"):
        raise ValueError(f"caminho não pode começar com '/': {path!r}")
    partes = path.split("/")
    if permitir_barra_final and partes[-1] == "":
        partes = partes[:-1]
    if any(p in ("", ".", "..") for p in partes):
        raise ValueError(f"caminho inválido: {path!r}")
    return path


def _normalizar_prefixo(prefixo: str) -> str:
    if prefixo and not prefixo.endswith("/"):
        prefixo += "/"
    if prefixo:
        validar_caminho(prefixo, permitir_barra_final=True)
    return prefixo


def segredo_local(settings: Settings) -> bytes:
    """Chave HMAC das URLs locais, derivada da service role key (ou de um segredo local)."""
    chave = settings.supabase_service_role_key.get_secret_value()
    base = chave.encode() if chave else SEGREDO_LOCAL_PADRAO
    return hmac.new(base, b"confere-local-storage", hashlib.sha256).digest()


def _assinar(secret: bytes, path: str, exp: int) -> str:
    return hmac.new(secret, f"{path}\n{exp}".encode(), hashlib.sha256).hexdigest()


def verify_local_signature(
    path: str, exp: int, sig: str, *, secret: bytes, now: float | None = None
) -> bool:
    """Confere a assinatura e a validade de uma URL local (usada pela rota que a serve)."""
    try:
        validar_caminho(path)
    except ValueError:
        return False
    if (time.time() if now is None else now) > exp:
        return False
    return hmac.compare_digest(_assinar(secret, path, exp), sig)


class LocalStorage:
    def __init__(self, base_dir: str | Path, prefix: str = "", secret: bytes | None = None):
        self._base = Path(base_dir).resolve()
        self._prefix = _normalizar_prefixo(prefix)
        self._secret = secret or SEGREDO_LOCAL_PADRAO

    def _arquivo(self, path: str) -> Path:
        validar_caminho(path)
        destino = (self._base / (self._prefix + path)).resolve()
        if not destino.is_relative_to(self._base):
            raise ValueError(f"caminho fora do armazenamento: {path!r}")
        return destino

    def put(self, path: str, data: bytes, content_type: str) -> None:
        destino = self._arquivo(path)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(data)

    def get(self, path: str) -> bytes:
        return self._arquivo(path).read_bytes()

    def exists(self, path: str) -> bool:
        return self._arquivo(path).is_file()

    def signed_url(self, path: str, expires_in: int = 300) -> str:
        validar_caminho(path)
        exp = int(time.time()) + expires_in
        sig = _assinar(self._secret, path, exp)
        return f"{ROTA_LOCAL}/{quote(path, safe='/')}?exp={exp}&sig={sig}"

    def delete_prefix(self, prefix: str) -> int:
        validar_caminho(prefix, permitir_barra_final=True)
        raiz = (self._base / self._prefix).resolve()
        if not raiz.is_dir():
            return 0
        removidos = 0
        for arquivo in list(raiz.rglob("*")):
            if arquivo.is_file() and arquivo.relative_to(raiz).as_posix().startswith(prefix):
                arquivo.unlink()
                removidos += 1
        return removidos


class SupabaseStorage:
    def __init__(
        self,
        settings: Settings,
        *,
        client: "S3Client | None" = None,
        http: httpx.Client | None = None,
    ):
        self._prefix = _normalizar_prefixo(settings.s3_prefix)
        self._bucket = settings.s3_bucket
        self._supabase_url = settings.supabase_url.rstrip("/")
        self._service_role = settings.supabase_service_role_key.get_secret_value()
        self._s3: Any = client or boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id.get_secret_value(),
            aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
            config=Config(s3={"addressing_style": "path"}),
        )
        self._http = http or httpx.Client(timeout=10.0)

    def _chave(self, path: str) -> str:
        return self._prefix + validar_caminho(path)

    def put(self, path: str, data: bytes, content_type: str) -> None:
        self._s3.put_object(
            Bucket=self._bucket, Key=self._chave(path), Body=data, ContentType=content_type
        )

    def get(self, path: str) -> bytes:
        try:
            resposta = self._s3.get_object(Bucket=self._bucket, Key=self._chave(path))
        except ClientError as erro:
            if erro.response.get("Error", {}).get("Code") in _CODIGOS_NAO_ENCONTRADO:
                raise FileNotFoundError(path) from erro
            raise
        corpo: bytes = resposta["Body"].read()
        return corpo

    def exists(self, path: str) -> bool:
        try:
            self._s3.head_object(Bucket=self._bucket, Key=self._chave(path))
        except ClientError as erro:
            if erro.response.get("Error", {}).get("Code") in _CODIGOS_NAO_ENCONTRADO:
                return False
            raise
        return True

    def signed_url(self, path: str, expires_in: int = 300) -> str:
        chave = quote(self._chave(path), safe="/")
        resposta = self._http.post(
            f"{self._supabase_url}/storage/v1/object/sign/{self._bucket}/{chave}",
            headers={"Authorization": f"Bearer {self._service_role}"},
            json={"expiresIn": expires_in},
        )
        resposta.raise_for_status()
        return f"{self._supabase_url}/storage/v1{resposta.json()['signedURL']}"

    def _chaves(self, prefixo_completo: str) -> Iterator[str]:
        paginas = self._s3.get_paginator("list_objects_v2").paginate(
            Bucket=self._bucket, Prefix=prefixo_completo
        )
        for pagina in paginas:
            for objeto in pagina.get("Contents", []):
                yield objeto["Key"]

    def delete_prefix(self, prefix: str) -> int:
        validar_caminho(prefix, permitir_barra_final=True)
        chaves = list(self._chaves(self._prefix + prefix))
        for i in range(0, len(chaves), 1000):
            lote = [{"Key": k} for k in chaves[i : i + 1000]]
            self._s3.delete_objects(Bucket=self._bucket, Delete={"Objects": lote})
        return len(chaves)


def build_storage(settings: Settings) -> Storage:
    if settings.storage_backend == "supabase":
        return SupabaseStorage(settings)
    return LocalStorage(
        settings.storage_local_dir, prefix=settings.s3_prefix, secret=segredo_local(settings)
    )


@lru_cache
def get_storage() -> Storage:
    """Dependência FastAPI: escolhe o backend por STORAGE_BACKEND."""
    return build_storage(get_settings())
