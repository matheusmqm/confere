"""Classificação por dicionário de sinônimos (CF-65): o caminho barato da E4, sem LLM.

Ordem: primeiro o sinônimo do **fornecedor** (confiança 1,0), depois o **global** (0,95). Se o
mesmo texto tem dois códigos no mesmo nível, há conflito: devolve None (a cobrança vai para o
LLM) e registra um aviso. Conflito no nível do fornecedor não cai para o global.
"""

from collections.abc import Iterable
from typing import Protocol

import structlog
from pydantic import BaseModel

from confere_core.costcode.catalogo import Catalogo
from confere_core.costcode.normalizar import normalizar_descricao
from confere_core.domain import ResultadoCodigo

CONFIANCA_FORNECEDOR = 1.0
CONFIANCA_GLOBAL = 0.95
log = structlog.get_logger()


class Sinonimo(BaseModel):
    texto_normalizado: str
    fornecedor_id: str | None  # None = global
    codigo: str
    origem: str  # ex. catalogo, treino, humano


class FonteSinonimos(Protocol):
    def buscar(self, texto_norm: str, fornecedor_id: str | None) -> list[Sinonimo]:
        """Sinônimos do texto: os do fornecedor e os globais."""
        ...

    def gravar(
        self, texto_norm: str, fornecedor_id: str | None, codigo: str, origem: str
    ) -> None:
        """Grava (upsert por fornecedor e texto): um código por texto em cada nível."""
        ...


def _decidir(
    candidatos: list[Sinonimo], texto_norm: str, nivel: str
) -> tuple[ResultadoCodigo | None, bool]:
    """(resultado, conflito) para os candidatos de um nível."""
    codigos = sorted({s.codigo for s in candidatos})
    if not codigos:
        return None, False
    if len(codigos) > 1:
        log.warning("sinonimo_em_conflito", texto=texto_norm, nivel=nivel, codigos=codigos)
        return None, True
    unico = candidatos[0]
    fornecedor = nivel == "fornecedor"
    return (
        ResultadoCodigo(
            codigo=unico.codigo,
            conf_codigo=CONFIANCA_FORNECEDOR if fornecedor else CONFIANCA_GLOBAL,
            metodo="dicionario_fornecedor" if fornecedor else "dicionario_global",
            detalhes={"texto_normalizado": texto_norm, "origem": unico.origem},
        ),
        False,
    )


def classificar_por_dicionario(
    texto_norm: str, fornecedor_id: str | None, fonte: FonteSinonimos
) -> ResultadoCodigo | None:
    encontrados = fonte.buscar(texto_norm, fornecedor_id)
    if fornecedor_id is not None:
        resultado, conflito = _decidir(
            [s for s in encontrados if s.fornecedor_id == fornecedor_id], texto_norm, "fornecedor"
        )
        if resultado is not None or conflito:
            return resultado
    resultado, _ = _decidir([s for s in encontrados if s.fornecedor_id is None], texto_norm, "global")
    return resultado


class FonteSinonimosMemoria:
    """Fonte em memória, para testes e para o eval (catálogo + treino)."""

    def __init__(self, sinonimos: Iterable[Sinonimo] = ()) -> None:
        self._itens: dict[tuple[str | None, str], list[Sinonimo]] = {}
        for s in sinonimos:
            self.adicionar(s)

    @classmethod
    def do_catalogo(cls, catalogo: Catalogo) -> "FonteSinonimosMemoria":
        """Sinônimos globais do catálogo, normalizados como as descrições."""
        fonte = cls()
        for item in catalogo.itens:
            for sinonimo in item.sinonimos:
                texto = normalizar_descricao(sinonimo)
                if texto:
                    fonte.adicionar(
                        Sinonimo(
                            texto_normalizado=texto,
                            fornecedor_id=None,
                            codigo=item.codigo,
                            origem="catalogo",
                        )
                    )
        return fonte

    def adicionar_treino(self, exemplos: Iterable[tuple[str, str, str]]) -> None:
        """`(descricao, fornecedor_id, codigo)` do conjunto de treino → sinônimos do fornecedor."""
        for descricao, fornecedor_id, codigo in exemplos:
            texto = normalizar_descricao(descricao)
            if texto:
                self.adicionar(
                    Sinonimo(
                        texto_normalizado=texto,
                        fornecedor_id=fornecedor_id,
                        codigo=codigo,
                        origem="treino",
                    )
                )

    def adicionar(self, sinonimo: Sinonimo) -> None:
        """Acrescenta sem apagar: dois códigos para o mesmo texto viram conflito."""
        lista = self._itens.setdefault((sinonimo.fornecedor_id, sinonimo.texto_normalizado), [])
        if all(s.codigo != sinonimo.codigo for s in lista):
            lista.append(sinonimo)

    def buscar(self, texto_norm: str, fornecedor_id: str | None) -> list[Sinonimo]:
        achados = list(self._itens.get((None, texto_norm), []))
        if fornecedor_id is not None:
            achados += self._itens.get((fornecedor_id, texto_norm), [])
        return achados

    def gravar(
        self, texto_norm: str, fornecedor_id: str | None, codigo: str, origem: str
    ) -> None:
        """Upsert: substitui o que havia para (fornecedor, texto)."""
        self._itens[(fornecedor_id, texto_norm)] = [
            Sinonimo(
                texto_normalizado=texto_norm,
                fornecedor_id=fornecedor_id,
                codigo=codigo,
                origem=origem,
            )
        ]
