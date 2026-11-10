"""Cache em disco das respostas do LLM (CF-53), commitado em `data/llm_cache/` para a demo offline.

Chave = sha256 de `"<prompt_id>:v<versao>:<modelo>:<chave_cache>"` (mudou o prompt, o modelo ou o
documento, a chave muda). Arquivo `<dir>/<chave[:2]>/<chave>.json`, escrito de forma atômica
(arquivo temporário + `os.replace`). Com `LLM_OFFLINE=true`, falta no cache é um erro claro
(`CacheAusenteOffline`): o plano B da final depende disso.

Chaves de cache usadas pelo pipeline (o `chave_cache` de cada etapa):

- classificação e extração: o `sha256` do arquivo (`chave_arquivo`);
- código de custo: `chave_codigo_custo` (descrições normalizadas + fornecedor + versão do catálogo);
- explicação: `chave_explicacao` (JSON canônico da exceção).
"""

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class CacheAusenteOffline(Exception):  # noqa: N818  (nome definido pela tarefa)
    """`LLM_OFFLINE=true` e a resposta não está no cache."""

    def __init__(self, chave: str, prompt_id: str) -> None:
        super().__init__(
            f"LLM offline: resposta ausente do cache (prompt {prompt_id!r}, chave {chave})"
        )
        self.chave = chave
        self.prompt_id = prompt_id


def _json_canonico(objeto: Any) -> str:
    return json.dumps(
        objeto, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    )


def _sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def chave_arquivo(sha256_arquivo: str) -> str:
    """Classificação e extração: o próprio sha256 do arquivo."""
    return sha256_arquivo


def chave_codigo_custo(
    descricoes_normalizadas: list[str], fornecedor_id: str, versao_catalogo: int | str
) -> str:
    """Código de custo: sha256 do JSON das descrições + fornecedor + versão do catálogo."""
    return _sha256(
        _json_canonico(
            {
                "descricoes": descricoes_normalizadas,
                "fornecedor_id": fornecedor_id,
                "versao_catalogo": versao_catalogo,
            }
        )
    )


def chave_explicacao(excecao: Mapping[str, Any]) -> str:
    """Explicação: sha256 do JSON canônico da exceção."""
    return _sha256(_json_canonico(excecao))


class CacheLLM:
    def __init__(self, dir: Path, agora: Callable[[], datetime] | None = None) -> None:
        self.dir = Path(dir)
        self._agora = agora or (lambda: datetime.now(UTC))

    @staticmethod
    def calcular_chave(prompt_id: str, versao: int, modelo: str, chave_cache: str) -> str:
        return _sha256(f"{prompt_id}:v{versao}:{modelo}:{chave_cache}")

    def caminho(self, chave: str) -> Path:
        return self.dir / chave[:2] / f"{chave}.json"

    def obter(
        self, prompt_id: str, versao: int, modelo: str, chave_cache: str
    ) -> dict[str, Any] | None:
        """O registro salvo (`dados`, `tokens_in`, ...) ou None. Arquivo ilegível conta como falta."""
        caminho = self.caminho(self.calcular_chave(prompt_id, versao, modelo, chave_cache))
        try:
            registro: dict[str, Any] = json.loads(caminho.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        return registro

    def gravar(
        self,
        prompt_id: str,
        versao: int,
        modelo: str,
        chave_cache: str,
        dados: dict[str, Any],
        tokens_in: int,
        tokens_out: int,
    ) -> Path:
        """Escrita atômica: arquivo temporário na mesma pasta e `os.replace`."""
        chave = self.calcular_chave(prompt_id, versao, modelo, chave_cache)
        destino = self.caminho(chave)
        destino.parent.mkdir(parents=True, exist_ok=True)
        registro = {
            "prompt_id": prompt_id,
            "versao": versao,
            "modelo": modelo,
            "criado_em": self._agora().isoformat(),
            "dados": dados,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }
        descritor, temporario = tempfile.mkstemp(dir=destino.parent, suffix=".tmp")
        try:
            with os.fdopen(descritor, "w", encoding="utf-8", newline="\n") as arquivo:
                json.dump(registro, arquivo, ensure_ascii=False, indent=2, sort_keys=True)
                arquivo.write("\n")
            os.replace(temporario, destino)
        except BaseException:
            Path(temporario).unlink(missing_ok=True)
            raise
        return destino

    def estatisticas(self) -> tuple[int, int]:
        """(número de arquivos .json, tamanho total em bytes)."""
        arquivos = [p for p in self.dir.rglob("*.json") if p.is_file()] if self.dir.exists() else []
        return len(arquivos), sum(p.stat().st_size for p in arquivos)
