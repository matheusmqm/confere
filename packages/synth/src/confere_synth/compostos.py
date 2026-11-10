"""PDFs compostos: fatura + BL de 1 página no mesmo arquivo (CF-46).

Servem para testar a separação (`confere_core.ingest.separar`). Cada composto repete uma fatura
de armador (que já existe como PDF avulso) com o BL do mesmo processo anexado, e registra no
manifest os `cortes_esperados`. O composto SUBSTITUI a fatura avulsa no lote: o manifest traz
`substitui_arquivo`, e quem monta o lote (CF-114) deve excluir a avulsa para não duplicar a fatura.
"""

import hashlib
import random
import tempfile
import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pymupdf
from pydantic import BaseModel

from confere_synth import faturas
from confere_synth.modelos import DocumentoSintetico, Fornecedor, Mundo, Processo
from confere_synth.render import TOMADOR_PADRAO, DocInfo, ambiente

EMBARCADORES = [
    "Shenzhen Meridian Exports Co., Ltd. (fictitious)",
    "Ningbo Harbor Trading Co., Ltd. (fictitious)",
    "Hamburg Beispiel Ausfuhr GmbH (fictitious)",
]
MERCADORIAS = [
    "GENERAL CARGO - HOUSEHOLD GOODS",
    "AUTO PARTS",
    "TEXTILE ARTICLES",
    "ELECTRONIC COMPONENTS",
]


class ConteinerBL(BaseModel):
    numero: str
    lacre: str
    volumes: int
    peso_kg: str


class ContextoBL(BaseModel):
    embarcador: str
    consignatario: str
    notificar: str
    armador: str
    frete: str
    navio: str
    viagem: str
    porto_embarque: str
    porto_descarga: str
    embarque: Any  # date
    mercadoria: str
    conteineres: list[ConteinerBL]


@dataclass(frozen=True)
class PlanoComposto:
    id: uuid.UUID
    fatura: DocumentoSintetico
    numero_bl: str
    emissao_bl: Any  # date
    bl: ContextoBL


def _bl_master(proc: Processo) -> str:
    for r in proc.referencias:
        if r.tipo == "bl_master":
            return r.valor
    raise ValueError(f"processo {proc.codigo} sem bl_master")


def _contexto_bl(
    rng: random.Random, proc: Processo, armador: Fornecedor, cliente_nome: str
) -> ContextoBL:
    return ContextoBL(
        embarcador=rng.choice(EMBARCADORES),
        consignatario=cliente_nome,
        notificar=TOMADOR_PADRAO.nome,
        armador=armador.nome,
        frete=rng.choice(["PREPAID", "COLLECT"]),
        navio=proc.navio or "-",
        viagem=proc.viagem or "-",
        porto_embarque=proc.origem,
        porto_descarga=proc.destino,
        embarque=proc.etd,
        mercadoria=rng.choice(MERCADORIAS),
        conteineres=[
            ConteinerBL(
                numero=r.valor,
                lacre=f"SL{rng.randrange(10**6):06d}",
                volumes=rng.randint(80, 900),
                peso_kg=f"{rng.randint(8_000, 26_000):,}",
            )
            for r in proc.referencias
            if r.tipo == "conteiner"
        ],
    )


def gerar_compostos(
    rng: random.Random, mundo: Mundo, documentos: list[DocumentoSintetico], n: int = 3
) -> list[PlanoComposto]:
    """Escolhe `n` faturas de armador (processos distintos, armadores variados) e monta o BL."""
    forn = {f.id: f for f in mundo.fornecedores}
    proc = {p.id: p for p in mundo.processos}
    cli = {c.id: c for c in mundo.clientes}
    candidatos = [
        d
        for d in documentos
        if d.tipo == "fatura"
        and d.processo_id is not None
        and d.arquivo is not None
        and forn[d.fornecedor_id].tipo == "armador"
        and proc[d.processo_id].modal == "maritimo"
    ]
    embaralhados = rng.sample(candidatos, len(candidatos))
    escolhidos: list[DocumentoSintetico] = []
    for d in embaralhados:  # primeiro um por armador, para variar
        if len(escolhidos) < n and d.fornecedor_id not in {e.fornecedor_id for e in escolhidos}:
            escolhidos.append(d)
    for d in embaralhados:  # se faltar, completa com outros processos
        if len(escolhidos) < n and d not in escolhidos:
            escolhidos.append(d)

    planos: list[PlanoComposto] = []
    for d in escolhidos:
        p = proc[d.processo_id or uuid.UUID(int=0)]
        planos.append(
            PlanoComposto(
                id=uuid.UUID(int=rng.getrandbits(128), version=4),
                fatura=d,
                numero_bl=_bl_master(p),
                emissao_bl=p.etd + timedelta(days=rng.randint(0, 2)),
                bl=_contexto_bl(rng, p, forn[d.fornecedor_id], cli[p.cliente_id].nome),
            )
        )
    return planos


def renderizar_bl_html(plano: PlanoComposto) -> str:
    doc = DocInfo(numero=plano.numero_bl, emissao=plano.emissao_bl, moeda="USD", total=Decimal(0))
    return ambiente().get_template("bl.html.j2").render(doc=doc, bl=plano.bl)


def gravar_composto(plano: PlanoComposto, saida_dir: str | Path) -> dict[str, Any]:
    """Fatura avulsa + BL de 1 página → `documentos/<id>.pdf`. Devolve a entrada do manifest."""
    saida = Path(saida_dir)
    avulsa = saida / (plano.fatura.arquivo or "")
    if not avulsa.exists():
        raise FileNotFoundError(f"{avulsa} não existe: rode `faturas` antes de `compostos`")

    with tempfile.TemporaryDirectory() as tmp:
        bl_pdf = Path(tmp) / "bl.pdf"
        faturas._escrever_pdf(renderizar_bl_html(plano), bl_pdf)
        destino = saida / "documentos" / f"{plano.id}.pdf"
        destino.parent.mkdir(parents=True, exist_ok=True)
        with (
            pymupdf.open(avulsa) as fatura,
            pymupdf.open(bl_pdf) as bl,
            pymupdf.open() as saida_pdf,
        ):
            n_fatura = fatura.page_count
            saida_pdf.insert_pdf(fatura)
            saida_pdf.insert_pdf(bl, from_page=0, to_page=0)  # BL de 1 página
            saida_pdf.set_metadata({})
            saida_pdf.save(destino, garbage=3, deflate=True, no_new_id=True)

    return {
        "arquivo": destino.relative_to(saida).as_posix(),
        "sha256": hashlib.sha256(destino.read_bytes()).hexdigest(),
        "id": str(plano.id),
        "tipo": "composto",
        "documento_id": str(plano.fatura.id),
        "fornecedor_id": plano.fatura.fornecedor_id,
        "numero_fatura": plano.fatura.numero,
        "numero_bl": plano.numero_bl,
        "substitui_arquivo": plano.fatura.arquivo,
        "cortes_esperados": [
            {"inicio": 1, "fim": n_fatura, "tipo": plano.fatura.tipo},
            {"inicio": n_fatura + 1, "fim": n_fatura + 1, "tipo": "bl"},
        ],
    }
