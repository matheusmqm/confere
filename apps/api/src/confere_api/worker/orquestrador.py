"""Orquestrador do pipeline (CF-107, versão do MVP mínimo).

Cada etapa é `etapa_<nome>(ctx)`, roda com timeout, grava um `evento` e confirma a transação (o SSE
mostra o progresso etapa a etapa). Versões reduzidas, a trocar depois:

- E3: só referência EXATA (sem fuzzy nem Fellegi-Sunter);
- E4: só o dicionário de sinônimos (sem embeddings nem LLM); o que não achar vira `codigo_incerto`;
- E5: só BRL (moeda estrangeira vira `moeda_sem_cotacao`);
- E6: casamento guloso por código; E7: regras `duplicidade` e `tolerancia` do core + `sem_provisao`;
- E8: regra fixa (`decidir_documento`); E10: explicação por template.

XML (CT-e) não usa LLM. PDF e imagem usam o Gemini e exigem `GEMINI_API_KEY`.
"""

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal
from functools import partial
from typing import Any

import structlog
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from confere_api.controllers.base import RepositorioBase
from confere_api.controllers.documento import DocumentoController
from confere_api.controllers.evento import EventoController
from confere_api.controllers.fornecedor import FornecedorController
from confere_api.controllers.historico import HistoricoDocumentosSQL
from confere_api.controllers.processo import ProcessoController
from confere_api.controllers.provisao import ProvisaoController
from confere_api.controllers.sinonimos import FonteSinonimosSQL
from confere_api.models.casamento import Casamento
from confere_api.models.documento import Documento, Linha
from confere_api.models.empresa import Empresa
from confere_api.models.evento import LLMCall
from confere_api.models.excecao import Excecao
from confere_api.models.job import Job
from confere_api.models.processo import Processo
from confere_api.models.provisao import Provisao
from confere_api.settings import RAIZ, get_settings
from confere_api.storage import Storage, get_storage
from confere_api.tenant import Tenant
from confere_api.worker.runner import executar_com_timeout, handler, timeout_da_etapa
from confere_core.costcode.dicionario import classificar_por_dicionario
from confere_core.costcode.normalizar import normalizar_descricao
from confere_core.decide.regra_fixa import decidir_documento
from confere_core.domain import FaturaExtraida, ResultadoCasamento
from confere_core.explain.template import explicar
from confere_core.extract.cte import extrair_cte
from confere_core.extract.pdf import extrair_com_verificacao
from confere_core.extract.validacoes import ContextoValidacao, validar
from confere_core.ingest import classificar
from confere_core.ingest.classificar_xml import classificar_xml
from confere_core.ingest.render import renderizar
from confere_core.llm.cache import CacheLLM
from confere_core.llm.client import GeminiClient, LLMClient, RegistroChamada
from confere_core.match.guloso import LinhaParaCasar, ProvisaoParaCasar, casar_guloso
from confere_core.resolve.normalizar import normalizar_referencia
from confere_core.rules import ContextoRegras, aplicar_regras
from confere_core.rules.base import DocumentoRegras, LinhaRegras, Politica
from confere_core.rules.duplicidade import normalizar_numero

log = structlog.get_logger()
CENTAVO = Decimal("0.01")
TIPOS_DE_FATURA = {"fatura", "nota_debito", "extrato", "cte"}
ETAPA_PARA_TIMEOUT = {"lido": "classificar", "extraido": "extrair", "codigos": "codigos"}
TIPO_POR_ESTADO = {
    "acima_tolerancia": "acima_tolerancia",
    "duplicada": "duplicada",
    "cambio_divergente": "cambio_divergente",
}


class ErroPipeline(Exception):  # noqa: N818
    """Falha esperada do pipeline, com mensagem amigável (não é bug)."""


@dataclass
class Ctx:
    db: Session
    tenant: Tenant
    job: Job
    documento: Documento
    storage: Storage
    politica: Politica
    conteudo: bytes = b""
    fatura: FaturaExtraida | None = None
    fornecedor_id: uuid.UUID | None = None
    processo_id: uuid.UUID | None = None
    linhas: list[Linha] = field(default_factory=list)
    excecoes: list[Excecao] = field(default_factory=list)
    encerrar: bool = False  # pula direto para a decisão
    arquivado: bool = False  # documento sem cobrança: não há o que decidir


def _json(dados: dict[str, Any]) -> dict[str, Any]:
    resultado: dict[str, Any] = json.loads(json.dumps(dados, default=str))
    return resultado


def _evento(
    ctx: Ctx, etapa: str, mensagem: str, status: str = "ok", dados: dict[str, Any] | None = None
) -> None:
    EventoController(ctx.db, ctx.tenant).registrar(
        etapa,
        status,
        mensagem,
        documento_id=ctx.documento.id,
        job_id=ctx.job.id,
        dados=_json(dados) if dados else None,
    )


def _excecao(
    ctx: Ctx,
    tipo: str,
    severidade: str,
    risco: Decimal,
    dados: dict[str, Any],
    linha: Linha | None = None,
) -> None:
    texto, acao = explicar(tipo, dados)
    excecao = Excecao(
        documento_id=ctx.documento.id,
        linha_id=linha.id if linha else None,
        tipo=tipo,
        severidade=severidade,
        valor_brl_em_risco=risco.quantize(CENTAVO, rounding=ROUND_HALF_EVEN),
        explicacao=texto,
        explicacao_origem="template",
        acao_sugerida=acao,
        dados_json=_json(dados),
        status="aberta",
    )
    RepositorioBase(ctx.db, ctx.tenant).adicionar(excecao)
    ctx.excecoes.append(excecao)


def _cliente_llm(ctx: Ctx) -> LLMClient:
    settings = get_settings()
    chave = settings.gemini_api_key.get_secret_value()
    if not chave:
        raise ErroPipeline("Ler PDF e imagem exige GEMINI_API_KEY no .env (XML não exige).")

    def registrar(chamada: RegistroChamada) -> None:
        ctx.db.add(
            LLMCall(
                empresa_id=ctx.tenant.empresa_id,
                documento_id=ctx.documento.id,
                etapa=chamada.etapa,
                modelo=chamada.modelo,
                prompt_id=chamada.prompt_id,
                prompt_versao=chamada.prompt_versao,
                tokens_in=chamada.tokens_in,
                tokens_out=chamada.tokens_out,
                custo_usd=chamada.custo_usd,
                latencia_ms=chamada.latencia_ms,
                cache_hit=chamada.cache_hit,
            )
        )

    return GeminiClient(
        api_key=chave,
        model=settings.gemini_model,
        embed_model=settings.gemini_embed_model,
        cache=CacheLLM(RAIZ / settings.llm_cache_dir),
        offline=settings.llm_offline,
        on_chamada=registrar,
    )


def _limpar_resultados(ctx: Ctx) -> None:
    """Reprocessar do zero: apaga o que uma tentativa anterior deixou e devolve as provisões."""
    db, doc, empresa = ctx.db, ctx.documento, ctx.tenant.empresa_id
    casadas = select(Casamento.provisao_id).join(Linha, Linha.id == Casamento.linha_id)
    db.execute(
        update(Provisao)
        .where(
            Provisao.empresa_id == empresa,
            Provisao.id.in_(casadas.where(Linha.documento_id == doc.id)),
        )
        .values(status="aberta")
    )
    db.execute(delete(Excecao).where(Excecao.empresa_id == empresa, Excecao.documento_id == doc.id))
    db.execute(delete(Linha).where(Linha.empresa_id == empresa, Linha.documento_id == doc.id))
    db.flush()


# ---------------------------------------------------------------------------------- etapas


def etapa_lido(ctx: Ctx) -> None:
    doc = ctx.documento
    if not doc.arquivo_path or doc.tipo_arquivo is None:
        raise ErroPipeline("O documento não tem arquivo armazenado.")
    ctx.conteudo = ctx.storage.get(doc.arquivo_path)
    if doc.tipo_arquivo == "xml":
        classificacao = classificar_xml(ctx.conteudo)
    else:
        classificacao = classificar(
            ctx.conteudo,
            doc.tipo_arquivo,  # type: ignore[arg-type]
            _cliente_llm(ctx),
            doc.remetente,
        )
    doc.tipo = classificacao.tipo
    if classificacao.tipo not in TIPOS_DE_FATURA:
        doc.status = "arquivado"
        ctx.arquivado = True
        _evento(
            ctx,
            "lido",
            f"Documento do tipo “{classificacao.tipo}”: arquivado, sem cobrança para conferir.",
            "aviso",
            {"tipo": classificacao.tipo, "motivo": classificacao.motivo},
        )
        return
    _evento(
        ctx,
        "lido",
        f"Lido como {classificacao.tipo}.",
        dados={"tipo": classificacao.tipo, "metodo": classificacao.metodo},
    )


def etapa_extraido(ctx: Ctx) -> None:
    doc = ctx.documento
    contexto = ContextoValidacao.padrao()
    if doc.tipo_arquivo == "xml":
        fatura = extrair_cte(ctx.conteudo)
        validacao = validar(fatura, contexto)
    else:
        paginas = renderizar(ctx.conteudo, doc.tipo_arquivo)  # type: ignore[arg-type]
        extracao = extrair_com_verificacao(
            paginas, _cliente_llm(ctx), doc.remetente, doc.sha256, contexto
        )
        validacao = extracao.validacao
    fatura = validacao.fatura
    ctx.fatura = fatura
    cab = fatura.cabecalho

    doc.numero = cab.numero_documento
    doc.numero_normalizado = normalizar_numero(cab.numero_documento)
    doc.emissao = cab.data_emissao
    doc.vencimento = cab.data_vencimento
    doc.moeda = cab.moeda
    doc.total = cab.total
    doc.confianca = Decimal(str(validacao.confianca)).quantize(Decimal("0.0001"))
    doc.extracao_json = _json(fatura.model_dump(mode="json"))
    doc.avisos = [*(doc.avisos or []), *validacao.avisos] or None

    for linha in fatura.linhas:
        registro = Linha(
            documento_id=doc.id,
            ordem=linha.ordem,
            descricao=linha.descricao,
            qtd=linha.quantidade,
            valor_unit=linha.valor_unitario,
            valor=linha.valor,
            moeda=linha.moeda,
            refs_json=_json(linha.referencias.model_dump(mode="json")),
            conf_extracao=Decimal(str(linha.confianca)).quantize(Decimal("0.0001")),
            bbox_json=linha.bbox.model_dump() if linha.bbox else None,
            estado="pendente",
        )
        RepositorioBase(ctx.db, ctx.tenant).adicionar(registro)
        ctx.linhas.append(registro)
    ctx.db.flush()

    ctx.fornecedor_id = FornecedorController(ctx.db, ctx.tenant).resolver_por_nome(
        cab.fornecedor_nome
    )
    doc.fornecedor_id = ctx.fornecedor_id
    if ctx.fornecedor_id is None:
        _excecao(
            ctx,
            "extracao_inconsistente",
            "revisar",
            Decimal(0),
            {"motivo": f"Fornecedor “{cab.fornecedor_nome}” não está cadastrado."},
        )
        ctx.encerrar = True
    if validacao.inconsistente:
        falhas = [f.mensagem for f in validacao.falhas if f.grave]
        _excecao(
            ctx,
            "extracao_inconsistente",
            "revisar",
            Decimal(0),
            {"motivo": "Os dados extraídos não fecham: " + "; ".join(falhas) + "."},
        )
        ctx.encerrar = True
    _evento(
        ctx,
        "extraido",
        f"{len(fatura.linhas)} linha(s) extraída(s), total {cab.moeda} {cab.total}.",
        "aviso" if validacao.falhas else "ok",
        {
            "linhas": len(fatura.linhas),
            "fornecedor": cab.fornecedor_nome,
            "fornecedor_encontrado": ctx.fornecedor_id is not None,
            "falhas": [f.codigo for f in validacao.falhas],
        },
    )


def _referencias_do_documento(fatura: FaturaExtraida) -> set[str]:
    conjuntos = [fatura.cabecalho.referencias, *(ln.referencias for ln in fatura.linhas)]
    normalizadas: set[str] = set()
    for refs in conjuntos:
        normalizadas |= {normalizar_referencia("bl_master", v) for v in refs.bls}
        normalizadas |= {normalizar_referencia("conteiner", v) for v in refs.conteineres}
        normalizadas |= {normalizar_referencia("ref_cliente", v) for v in refs.ref_cliente}
    return {n for n in normalizadas if n}


def etapa_processo(ctx: Ctx) -> None:
    assert ctx.fatura is not None
    if ctx.encerrar:
        _evento(ctx, "processo", "Etapa pulada: extração com pendências.", "aviso")
        return
    achados = ProcessoController(ctx.db, ctx.tenant).por_referencias(
        _referencias_do_documento(ctx.fatura)
    )
    total = sum((ln.valor for ln in ctx.linhas if ln.moeda == "BRL"), Decimal(0))
    if not achados:
        _excecao(ctx, "sem_processo", "revisar", total, {})
        ctx.encerrar = True
        _evento(ctx, "processo", "Nenhuma referência bate com um processo.", "aviso")
        return
    melhor = max(len(v) for v in achados.values())
    empatados = [p for p, v in achados.items() if len(v) == melhor]
    if len(empatados) > 1:
        _excecao(
            ctx,
            "confirmar_processo",
            "revisar",
            Decimal(0),
            {"motivo": f"As referências batem com {len(empatados)} processos diferentes."},
        )
        ctx.encerrar = True
        _evento(ctx, "processo", "Mais de um processo possível: confirmar.", "aviso")
        return

    processo_id = empatados[0]
    processo = ProcessoController(ctx.db, ctx.tenant).obter(Processo, processo_id)
    confianca = Decimal("1.0000")
    if ctx.fornecedor_id and not ProvisaoController(ctx.db, ctx.tenant).do_processo(
        processo_id, ctx.fornecedor_id
    ):
        confianca = Decimal("0.6000")
        _excecao(
            ctx,
            "confirmar_processo",
            "revisar",
            Decimal(0),
            {"motivo": f"O fornecedor não tem custo previsto no processo {processo.codigo}."},
        )
    ctx.processo_id = processo_id
    for linha in ctx.linhas:
        linha.processo_id = processo_id
        linha.conf_processo = confianca
    _evento(
        ctx,
        "processo",
        f"Processo {processo.codigo}.",
        "ok" if confianca == 1 else "aviso",
        {"processo": processo.codigo, "referencias": sorted(achados[processo_id])},
    )


def etapa_codigos(ctx: Ctx) -> None:
    fonte = FonteSinonimosSQL(ctx.db, ctx.tenant)
    fornecedor = str(ctx.fornecedor_id) if ctx.fornecedor_id else None
    incertos = 0
    moedas_sem_cotacao: set[str] = set()
    for linha in ctx.linhas:
        texto = normalizar_descricao(linha.descricao)
        linha.descricao_normalizada = texto
        resultado = classificar_por_dicionario(texto, fornecedor, fonte)
        if resultado is None:
            incertos += 1
        else:
            linha.codigo_custo = resultado.codigo
            linha.conf_codigo = Decimal(str(resultado.conf_codigo)).quantize(Decimal("0.0001"))
            linha.metodo_codigo = resultado.metodo
        if linha.moeda == "BRL":
            linha.valor_brl = linha.valor
        else:
            linha.valor_brl = None
            moedas_sem_cotacao.add(linha.moeda)
        if resultado is None:
            _excecao(
                ctx,
                "codigo_incerto",
                "revisar",
                linha.valor_brl or Decimal(0),
                {"descricao": linha.descricao},
                linha,
            )
    for moeda in sorted(moedas_sem_cotacao):
        _excecao(ctx, "moeda_sem_cotacao", "revisar", Decimal(0), {"moeda": moeda})
    _evento(
        ctx,
        "codigos",
        f"{len(ctx.linhas) - incertos} de {len(ctx.linhas)} código(s) identificado(s).",
        "aviso" if incertos or moedas_sem_cotacao else "ok",
        {"identificados": len(ctx.linhas) - incertos, "incertos": incertos},
    )


def _casar(ctx: Ctx) -> ResultadoCasamento:
    assert ctx.processo_id is not None and ctx.fornecedor_id is not None
    provisoes = ProvisaoController(ctx.db, ctx.tenant).abertas(ctx.processo_id, ctx.fornecedor_id)
    resultado = casar_guloso(
        [
            LinhaParaCasar(id=ln.id, codigo_custo=ln.codigo_custo, valor=ln.valor, moeda=ln.moeda)
            for ln in ctx.linhas
        ],
        [
            ProvisaoParaCasar(id=p.id, codigo_custo=p.codigo_custo, valor=p.valor, moeda=p.moeda)
            for p in provisoes
        ],
    )
    por_id = {p.id: p for p in provisoes}
    linhas = {ln.id: ln for ln in ctx.linhas}
    for c in resultado.casamentos:
        if c.provisao_id is None or c.cobrado is None or c.previsto is None:
            continue
        ptax = c.ptax or Decimal(1)
        dif = (c.cobrado - c.previsto).quantize(CENTAVO)
        RepositorioBase(ctx.db, ctx.tenant).adicionar(
            Casamento(
                linha_id=c.linha_id,
                provisao_id=c.provisao_id,
                custo=(abs(dif) / c.previsto).quantize(Decimal("0.000001")),
                diferenca=dif,
                moeda_comparacao=c.moeda,
                diferenca_brl=(dif * ptax).quantize(CENTAVO),
                ptax=c.ptax,
                ptax_data=c.ptax_data,
                solver="guloso",
            )
        )
        por_id[c.provisao_id].status = "casada"
        linhas[c.linha_id].estado = "ok"
    return resultado


def etapa_casado(ctx: Ctx) -> None:
    assert ctx.fatura is not None
    if ctx.encerrar or ctx.processo_id is None or ctx.fornecedor_id is None:
        _evento(ctx, "casado", "Etapa pulada: sem processo ou fornecedor.", "aviso")
        return
    casamento = _casar(ctx)
    doc = ctx.documento
    linhas_regras = [
        LinhaRegras(
            id=ln.id,
            ordem=ln.ordem,
            descricao=ln.descricao,
            codigo_custo=ln.codigo_custo,
            processo_id=ln.processo_id,
            valor=ln.valor,
            moeda=ln.moeda,
            valor_brl=ln.valor_brl or Decimal(0),
        )
        for ln in ctx.linhas
    ]
    avaliacao = aplicar_regras(
        ContextoRegras(
            politica=ctx.politica,
            documento=DocumentoRegras(
                id=doc.id,
                empresa_id=ctx.tenant.empresa_id,
                fornecedor_id=str(ctx.fornecedor_id),
                numero=doc.numero or "",
                sha256=doc.sha256,
                cabecalho=ctx.fatura.cabecalho,
                total_brl=sum((ln.valor_brl for ln in linhas_regras), Decimal(0)),
            ),
            casamento=casamento,
            linhas=linhas_regras,
            historico=HistoricoDocumentosSQL(ctx.db, ctx.tenant),
        )
    )
    sem_par = {c.linha_id for c in casamento.casamentos if c.provisao_id is None}
    sem_provisao = 0
    for linha in ctx.linhas:
        vencedor = avaliacao.estados_linha.get(str(linha.id))
        if linha.codigo_custo is None and (vencedor is None or vencedor.estado == "ok"):
            linha.estado = "pendente"  # código incerto: nada a conferir ainda
            continue
        dados = {"descricao": linha.descricao, "valor_brl": linha.valor_brl or Decimal(0)}
        sem_par_e_ok = linha.id in sem_par and vencedor is not None and vencedor.estado == "ok"
        if sem_par_e_ok:  # nenhuma regra mais grave: falta a provisão
            linha.estado = "sem_provisao"
            sem_provisao += 1
            _excecao(ctx, "sem_provisao", "revisar", linha.valor_brl or Decimal(0), dados, linha)
            continue
        if vencedor is None:
            continue
        linha.estado = vencedor.estado if vencedor.estado != "sem_fatura" else "pendente"
        tipo = TIPO_POR_ESTADO.get(vencedor.estado)
        if tipo and vencedor.severidade != "info":
            _excecao(
                ctx,
                tipo,
                vencedor.severidade,
                vencedor.valor_brl_em_risco,
                {**vencedor.dados, **dados},
                linha,
            )
    _evento(
        ctx,
        "casado",
        f"{len(casamento.casamentos) - len(sem_par)} linha(s) casada(s) com a provisão.",
        "aviso" if avaliacao.regras_violadas or sem_provisao else "ok",
        {
            "casadas": len(casamento.casamentos) - len(sem_par),
            "sem_provisao": sem_provisao,
            "regras_violadas": avaliacao.regras_violadas,
            "em_risco_brl": avaliacao.total_em_risco,
        },
    )


def etapa_decidido(ctx: Ctx) -> None:
    abertas = [e for e in ctx.excecoes if e.status == "aberta"]
    status = decidir_documento(e.severidade for e in abertas)
    ctx.documento.status = status
    ctx.documento.score_decisao = None  # sem score calibrado no MVP mínimo
    ctx.documento.tau = None
    em_risco = sum((e.valor_brl_em_risco for e in abertas if e.severidade != "info"), Decimal(0))
    frases = {
        "aprovado_auto": "Aprovada sozinha: nada divergiu.",
        "em_revisao": "Enviada para revisão.",
        "bloqueado": "Bloqueada.",
    }
    _evento(
        ctx,
        "decidido",
        frases[status],
        "ok" if status == "aprovado_auto" else "aviso",
        {
            "status_final": status,
            "vazamento_brl": em_risco,
            "motivos": sorted({e.tipo for e in abertas}),
        },
    )


ETAPAS: list[tuple[str, Callable[[Ctx], None]]] = [
    ("lido", etapa_lido),
    ("extraido", etapa_extraido),
    ("processo", etapa_processo),
    ("codigos", etapa_codigos),
    ("casado", etapa_casado),
    ("decidido", etapa_decidido),
]


def _marcar_falha_final(ctx: Ctx, erro: Exception) -> None:
    """Última tentativa esgotada: o documento não fica preso, vai para a revisão."""
    ctx.documento.status = "em_revisao"
    _excecao(
        ctx,
        "extracao_inconsistente",
        "revisar",
        Decimal(0),
        {"motivo": f"Falha ao processar: {erro}"[:300]},
    )
    ctx.db.commit()


@handler("processar")
def processar(session: Session, job: Job) -> None:
    tenant = Tenant(job.empresa_id, None, "gestor")
    documento = DocumentoController(session, tenant).obter_documento(
        uuid.UUID(str(job.payload_json["documento_id"]))
    )
    empresa = session.get(Empresa, tenant.empresa_id)  # a empresa É o tenant
    politica = Politica(**(empresa.politica_json if empresa else {}))
    ctx = Ctx(session, tenant, job, documento, get_storage(), politica)
    documento.status = "processando"
    _limpar_resultados(ctx)
    session.commit()
    try:
        for nome, etapa in ETAPAS:
            executar_com_timeout(
                partial(etapa, ctx), timeout_da_etapa(ETAPA_PARA_TIMEOUT.get(nome, "padrao"))
            )
            session.commit()
            if ctx.arquivado:
                break
    except Exception as erro:
        session.rollback()
        log.error("pipeline_falhou", documento_id=str(documento.id), erro=repr(erro))
        if job.tentativas >= job.max_tentativas:
            _marcar_falha_final(ctx, erro)
        raise


@handler("reprocessar")
def reprocessar(session: Session, job: Job) -> None:
    """MVP mínimo: reprocessa do zero (a extração é refeita; XML não gasta LLM)."""
    processar(session, job)
