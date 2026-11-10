"""Cliente LLM compartilhado: Gemini (SDK `google-genai`) e um fake determinístico para testes.

Regras do projeto: toda saída é presa a um schema Pydantic, temperatura 0, o prompt vai como
instrução de sistema e o conteúdo do documento vai à parte (é dado, nunca instrução). A chave
de cache (`chave_cache`) já é aceita; o cache em si entra na CF-53.
"""

import hashlib
import math
import time
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from confere_core.llm.cache import CacheAusenteOffline, CacheLLM
from confere_core.llm.custo import TabelaPrecos, calcular_custo_usd
from confere_core.llm.schema_gemini import para_schema_gemini

DIMENSAO_EMBEDDING = 768
PASTA_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"


class SaidaInvalidaLLM(Exception):  # noqa: N818  (nome definido pela tarefa)
    """O LLM não devolveu JSON válido para o schema, mesmo após uma nova tentativa."""


class RespostaLLM[T: BaseModel](BaseModel):
    dados: T
    modelo: str
    tokens_in: int
    tokens_out: int
    latencia_ms: int
    cache_hit: bool = False
    custo_usd: Decimal


class RegistroChamada(BaseModel):
    """O que o hook `on_chamada` recebe (a CF-54 grava como `llm_call`)."""

    etapa: str
    prompt_id: str
    prompt_versao: int
    modelo: str
    tokens_in: int
    tokens_out: int
    latencia_ms: int
    cache_hit: bool
    custo_usd: Decimal
    chave_cache: str | None
    tentativas: int
    sucesso: bool
    erro: str | None = None


HookChamada = Callable[[RegistroChamada], None]


class LLMClient(Protocol):
    def gerar_estruturado[T: BaseModel](
        self,
        *,
        etapa: str,
        prompt_id: str,
        prompt_versao: int,
        texto: str,
        imagens: list[bytes],
        schema: type[T],
        chave_cache: str | None = None,
    ) -> RespostaLLM[T]: ...

    def embed(self, textos: list[str]) -> list[list[float]]: ...


def carregar_prompt(prompt_id: str, versao: int) -> str:
    """Texto de `prompts/<prompt_id>_v<versao>.md` (a versão entra na chave de cache)."""
    return (PASTA_PROMPTS / f"{prompt_id}_v{versao}.md").read_text(encoding="utf-8")


def _resposta_do_cache[T: BaseModel](
    *,
    cache: CacheLLM | None,
    offline: bool,
    etapa: str,
    prompt_id: str,
    prompt_versao: int,
    modelo: str,
    chave_cache: str | None,
    schema: type[T],
    on_chamada: HookChamada | None,
) -> RespostaLLM[T] | None:
    """Devolve a resposta do cache (chamando o hook, mesmo no hit) ou None se não houver.

    Em modo offline, falta no cache levanta `CacheAusenteOffline`.
    """
    if chave_cache is None or cache is None:
        if offline:
            chave = (
                CacheLLM.calcular_chave(prompt_id, prompt_versao, modelo, chave_cache)
                if chave_cache is not None
                else "(sem chave_cache)"
            )
            raise CacheAusenteOffline(chave, prompt_id)
        return None
    inicio = time.perf_counter()
    registro = cache.obter(prompt_id, prompt_versao, modelo, chave_cache)
    dados: T | None = None
    if registro is not None:
        try:
            dados = schema.model_validate(registro["dados"])
        except (ValidationError, KeyError):
            dados = None  # registro antigo ou incompatível: trata como falta
    if dados is None or registro is None:
        if offline:
            chave = CacheLLM.calcular_chave(prompt_id, prompt_versao, modelo, chave_cache)
            raise CacheAusenteOffline(chave, prompt_id)
        return None
    latencia = round((time.perf_counter() - inicio) * 1000)
    tokens_in, tokens_out = int(registro["tokens_in"]), int(registro["tokens_out"])
    if on_chamada is not None:
        on_chamada(
            RegistroChamada(
                etapa=etapa, prompt_id=prompt_id, prompt_versao=prompt_versao, modelo=modelo,
                tokens_in=tokens_in, tokens_out=tokens_out, latencia_ms=latencia,
                cache_hit=True, custo_usd=Decimal(0), chave_cache=chave_cache,
                tentativas=0, sucesso=True,
            )
        )  # fmt: skip
    return RespostaLLM[T](
        dados=dados,
        modelo=modelo,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latencia_ms=latencia,
        cache_hit=True,
        custo_usd=Decimal(0),
    )


def _gravar_no_cache(
    cache: CacheLLM | None,
    chave_cache: str | None,
    prompt_id: str,
    prompt_versao: int,
    modelo: str,
    dados: BaseModel,
    tokens_in: int,
    tokens_out: int,
) -> None:
    if cache is not None and chave_cache is not None:
        cache.gravar(
            prompt_id, prompt_versao, modelo, chave_cache,
            dados.model_dump(mode="json"), tokens_in, tokens_out,
        )  # fmt: skip


def _uso(resposta: Any) -> tuple[int, int]:
    uso = getattr(resposta, "usage_metadata", None)
    if uso is None:
        return 0, 0
    entrada = getattr(uso, "prompt_token_count", None) or 0
    saida = (getattr(uso, "candidates_token_count", None) or 0) + (
        getattr(uso, "thoughts_token_count", None) or 0
    )
    return int(entrada), int(saida)


class GeminiClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        embed_model: str,
        precos: TabelaPrecos | None = None,
        on_chamada: HookChamada | None = None,
        client: Any | None = None,
        cache: CacheLLM | None = None,
        offline: bool = False,
    ) -> None:
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self._client: Any = client
        self._model = model
        self._embed_model = embed_model
        self._precos = precos or TabelaPrecos.carregar()
        self._on_chamada = on_chamada
        self._cache = cache
        self._offline = offline

    def gerar_estruturado[T: BaseModel](
        self,
        *,
        etapa: str,
        prompt_id: str,
        prompt_versao: int,
        texto: str,
        imagens: list[bytes],
        schema: type[T],
        chave_cache: str | None = None,
    ) -> RespostaLLM[T]:
        em_cache = _resposta_do_cache(
            cache=self._cache, offline=self._offline, etapa=etapa, prompt_id=prompt_id,
            prompt_versao=prompt_versao, modelo=self._model, chave_cache=chave_cache,
            schema=schema, on_chamada=self._on_chamada,
        )  # fmt: skip
        if em_cache is not None:
            return em_cache
        from google.genai import types

        sistema = carregar_prompt(prompt_id, prompt_versao)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=para_schema_gemini(schema),
            temperature=0,
            system_instruction=sistema,
        )
        partes = [types.Part.from_bytes(data=img, mime_type="image/png") for img in imagens]

        inicio = time.perf_counter()
        tokens_in = tokens_out = 0
        erro = ""
        dados: T | None = None
        tentativas = 0
        for tentativas in (1, 2):
            pedido = texto if tentativas == 1 else (
                f"{texto}\n\n[CORREÇÃO] Sua resposta anterior não respeitou o schema: {erro}. "
                "Responda de novo, somente com JSON válido para o schema."
            )  # fmt: skip
            contents: list[Any] = [pedido, *partes]
            resposta = self._client.models.generate_content(
                model=self._model, contents=contents, config=config
            )
            t_in, t_out = _uso(resposta)
            tokens_in, tokens_out = tokens_in + t_in, tokens_out + t_out
            try:
                dados = schema.model_validate_json(resposta.text or "")
                break
            except (ValidationError, ValueError) as e:
                erro = str(e)[:500]
        latencia = round((time.perf_counter() - inicio) * 1000)
        custo = calcular_custo_usd(self._precos, self._model, tokens_in, tokens_out)

        if self._on_chamada is not None:
            self._on_chamada(
                RegistroChamada(
                    etapa=etapa, prompt_id=prompt_id, prompt_versao=prompt_versao,
                    modelo=self._model, tokens_in=tokens_in, tokens_out=tokens_out,
                    latencia_ms=latencia, cache_hit=False, custo_usd=custo,
                    chave_cache=chave_cache, tentativas=tentativas,
                    sucesso=dados is not None, erro=None if dados is not None else erro,
                )
            )  # fmt: skip
        if dados is None:
            raise SaidaInvalidaLLM(f"{prompt_id} v{prompt_versao}: saída inválida: {erro}")
        _gravar_no_cache(
            self._cache, chave_cache, prompt_id, prompt_versao, self._model, dados,
            tokens_in, tokens_out,
        )  # fmt: skip
        return RespostaLLM[T](
            dados=dados,
            modelo=self._model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latencia_ms=latencia,
            cache_hit=False,
            custo_usd=custo,
        )

    def embed(self, textos: list[str]) -> list[list[float]]:
        from google.genai import types

        resposta = self._client.models.embed_content(
            model=self._embed_model,
            contents=textos,
            config=types.EmbedContentConfig(output_dimensionality=DIMENSAO_EMBEDDING),
        )
        vetores = [list(e.values) for e in resposta.embeddings]
        if len(vetores) != len(textos) or any(len(v) != DIMENSAO_EMBEDDING for v in vetores):
            raise ValueError(f"embeddings devem ter dimensão {DIMENSAO_EMBEDDING}")
        return vetores


# ---------------------------------------------------------------------- fake


class ChamadaFake(BaseModel):
    etapa: str
    prompt_id: str
    prompt_versao: int
    texto: str
    n_imagens: int


class FakeLLMClient:
    """Respostas determinísticas para testes: `prompt_id → função(texto, imagens) → dict`."""

    def __init__(
        self,
        respostas: dict[str, Callable[[str, list[bytes]], dict[str, Any]]],
        *,
        modelo: str = "fake",
        on_chamada: HookChamada | None = None,
        cache: CacheLLM | None = None,
        offline: bool = False,
    ) -> None:
        self._cache = cache
        self._offline = offline
        self._respostas = respostas
        self._modelo = modelo
        self._on_chamada = on_chamada
        self.chamadas: list[ChamadaFake] = []
        self.imagens_recebidas: list[list[bytes]] = []

    def gerar_estruturado[T: BaseModel](
        self,
        *,
        etapa: str,
        prompt_id: str,
        prompt_versao: int,
        texto: str,
        imagens: list[bytes],
        schema: type[T],
        chave_cache: str | None = None,
    ) -> RespostaLLM[T]:
        em_cache = _resposta_do_cache(
            cache=self._cache, offline=self._offline, etapa=etapa, prompt_id=prompt_id,
            prompt_versao=prompt_versao, modelo=self._modelo, chave_cache=chave_cache,
            schema=schema, on_chamada=self._on_chamada,
        )  # fmt: skip
        if em_cache is not None:
            return em_cache
        if prompt_id not in self._respostas:
            raise KeyError(f"FakeLLMClient sem resposta para o prompt {prompt_id!r}")
        self.chamadas.append(
            ChamadaFake(
                etapa=etapa, prompt_id=prompt_id, prompt_versao=prompt_versao,
                texto=texto, n_imagens=len(imagens),
            )
        )  # fmt: skip
        self.imagens_recebidas.append(list(imagens))
        bruto = self._respostas[prompt_id](texto, imagens)
        try:
            dados = schema.model_validate(bruto)
        except ValidationError as erro:
            raise SaidaInvalidaLLM(f"{prompt_id}: {erro}") from erro
        tokens_in, tokens_out = math.ceil(len(texto) / 4), math.ceil(len(str(bruto)) / 4)
        _gravar_no_cache(
            self._cache, chave_cache, prompt_id, prompt_versao, self._modelo, dados,
            tokens_in, tokens_out,
        )  # fmt: skip
        if self._on_chamada is not None:
            self._on_chamada(
                RegistroChamada(
                    etapa=etapa, prompt_id=prompt_id, prompt_versao=prompt_versao,
                    modelo=self._modelo, tokens_in=tokens_in, tokens_out=tokens_out,
                    latencia_ms=0, cache_hit=False, custo_usd=Decimal(0),
                    chave_cache=chave_cache, tentativas=1, sucesso=True,
                )
            )  # fmt: skip
        return RespostaLLM[T](
            dados=dados,
            modelo=self._modelo,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latencia_ms=0,
            cache_hit=False,
            custo_usd=Decimal(0),
        )

    def embed(self, textos: list[str]) -> list[list[float]]:
        """Vetores de 768 dimensões, unitários e determinísticos por texto."""
        return [self._vetor(t) for t in textos]

    @staticmethod
    def _vetor(texto: str) -> list[float]:
        bruto: list[float] = []
        bloco = 0
        while len(bruto) < DIMENSAO_EMBEDDING:
            h = hashlib.sha256(f"{bloco}:{texto}".encode()).digest()
            bruto += [(b - 127.5) / 127.5 for b in h]
            bloco += 1
        bruto = bruto[:DIMENSAO_EMBEDDING]
        norma = math.sqrt(sum(x * x for x in bruto)) or 1.0
        return [x / norma for x in bruto]
