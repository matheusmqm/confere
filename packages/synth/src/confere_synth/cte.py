"""CT-e 4.00 sintético (modelo 57) das transportadoras fictícias, e o DACTE em PDF.

Bibliotecas (versões inspecionadas na instalação do projeto):

- nfelib 3.3.0 (MIT, Akretion). Caminhos de import usados::

      from nfelib.cte.bindings.v4_0.cte_v4_00 import Cte                      # raiz <CTe>
      from nfelib.cte.bindings.v4_0 import cte_tipos_basico_v4_00 as T        # Tcte.InfCte.*
      from nfelib.cte.bindings.v4_0 import tipos_geral_cte_v4_00 as G         # Tuf, TcodUfIbge
      from nfelib.cte.bindings.v4_0.cte_modal_rodoviario_v4_00 import Rodo    # infModal/rodo

  API: ``Cte.to_xml()``, ``Cte.from_xml(xml)``, ``Cte.schema_validation(xml)`` e
  ``Cte._get_schema_path()`` (XSD ``cte_v4.00.xsd`` empacotado).
- brazilfiscalreport 1.4.0 (LGPL-3.0, Engenere): ``Dacte(xml=...).output(caminho)``.

**O XML NÃO É ASSINADO**: não há certificado, e é apenas para testes. O XSD exige o nó
``Signature``; por isso ``validar_xml`` valida contra o schema oficial e descarta somente os
erros que mencionam ``Signature``. Todo o resto (campos, padrões, enumerações) é validado.
Emitimos em ambiente de homologação (``tpAmb=2``), então o DACTE sai com "SEM VALOR FISCAL".

Cada CT-e cobre o trecho rodoviário de um processo: início no município do porto de destino
(nos processos só rodoviários, também o porto de destino) e fim na cidade fictícia do cliente.
Cada componente do frete (FRETE PESO, PEDAGIO, GRIS, AD VALOREM) vira uma linha do gabarito.
"""

import random
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from nfelib.cte.bindings.v4_0 import cte_tipos_basico_v4_00 as T  # noqa: N812
from nfelib.cte.bindings.v4_0 import evento_cte_tipos_basico_v4_00 as E  # noqa: N812
from nfelib.cte.bindings.v4_0 import tipos_geral_cte_v4_00 as G  # noqa: N812
from nfelib.cte.bindings.v4_0.cte_modal_rodoviario_v4_00 import Rodo
from nfelib.cte.bindings.v4_0.cte_v4_00 import Cte

from confere_synth.faturas import _valor_da_linha
from confere_synth.modelos import (
    Cliente,
    DocumentoSintetico,
    Emitente,
    Fornecedor,
    LinhaSintetica,
    Mundo,
    Processo,
    Provisao,
    Referencia,
)
from confere_synth.render import TOMADOR_PADRAO

VERSAO = "4.00"
SERIE = "1"
COMPONENTES = {
    "FRETE_RODO": "FRETE PESO",
    "PEDAGIO": "PEDAGIO",
    "GRIS": "GRIS",
    "AD_VALOREM_SEGURO": "AD VALOREM",
}
UF_CODIGO = {"CE": "23", "PE": "26", "SP": "35"}

# (código IBGE real, nome, UF). Os dados do CT-e são fictícios; os códigos de município, não.
MUNICIPIO_PORTO = {
    "BRFOR": ("2304400", "Fortaleza", "CE"),
    "BRPEC": ("2312403", "São Gonçalo do Amarante", "CE"),
    "BRSUA": ("2607752", "Ipojuca", "PE"),
    "BRSSZ": ("3548500", "Santos", "SP"),
}
CIDADES_CLIENTE = [
    ("2304400", "Fortaleza", "CE"),
    ("2307650", "Maracanaú", "CE"),
    ("2303709", "Caucaia", "CE"),
    ("2611606", "Recife", "PE"),
]
# Endereços FICTÍCIOS das transportadoras (cUF do CT-e = UF do emitente).
ENDERECO_TRANSPORTADORA = {
    "transportadora-mandacaru": {
        "xLgr": "Rua Fictícia", "nro": "40", "xBairro": "Centro",
        "cMun": "2304400", "xMun": "Fortaleza", "UF": "CE", "CEP": "60000000",
    },
    "rodoviario-ventania": {
        "xLgr": "Avenida Fictícia", "nro": "1200", "xBairro": "Boa Viagem",
        "cMun": "2611606", "xMun": "Recife", "UF": "PE", "CEP": "50000000",
    },
}  # fmt: skip


# ------------------------------------------------------------------- chaves


def dv_modulo11(digitos: str) -> int:
    """Dígito verificador (módulo 11, pesos 2 a 9 da direita para a esquerda)."""
    soma = 0
    peso = 2
    for d in reversed(digitos):
        soma += int(d) * peso
        peso = peso + 1 if peso < 9 else 2
    resto = soma % 11
    return 0 if resto in (0, 1) else 11 - resto


def chave_valida(chave: str) -> bool:
    return bool(re.fullmatch(r"\d{44}", chave)) and dv_modulo11(chave[:43]) == int(chave[43])


def _chave(cuf: str, emissao: date, cnpj: str, modelo: str, serie: str, n: int, codigo: int) -> str:
    base = f"{cuf}{emissao:%y%m}{cnpj}{modelo}{int(serie):03d}{n:09d}1{codigo:08d}"  # tpEmis=1
    return base + str(dv_modulo11(base))


def chave_cte(cuf: str, emissao: date, cnpj: str, n: int, codigo: int) -> str:
    return _chave(cuf, emissao, cnpj, "57", SERIE, n, codigo)


def chave_nfe_ficticia(rng: random.Random, cuf: str, emissao: date, cnpj: str) -> str:
    return _chave(cuf, emissao, cnpj, "55", SERIE, rng.randint(1, 999_999), rng.randrange(10**8))


# ------------------------------------------------------------------- montagem


def _digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto)


def _ende(cls: type, dados: dict[str, str], uf_cls: type) -> object:
    return cls(
        xLgr=dados["xLgr"],
        nro=dados["nro"],
        xBairro=dados["xBairro"],
        cMun=dados["cMun"],
        xMun=dados["xMun"],
        CEP=dados["CEP"],
        UF=uf_cls(dados["UF"]),
    )


def _endereco_municipio(municipio: tuple[str, str, str], logradouro: str) -> dict[str, str]:
    cod, nome, uf = municipio
    return {
        "xLgr": logradouro, "nro": "S/N", "xBairro": "Centro",
        "cMun": cod, "xMun": nome, "UF": uf, "CEP": "00000000",
    }  # fmt: skip


def _valor(v: Decimal) -> str:
    return f"{v:.2f}"


@dataclass(frozen=True)
class CteGerado:
    documento: DocumentoSintetico
    xml: str
    chave: str


def _referencia_citada(proc: Processo) -> Referencia | None:
    for tipo in ("bl_house", "ref_cliente", "bl_master"):
        for r in proc.referencias:
            if r.tipo == tipo:
                return r
    return None


def _montar(
    rng: random.Random,
    proc: Processo,
    forn: Fornecedor,
    cliente: Cliente,
    componentes: list[tuple[str, Decimal]],
    emissao: date,
    n_cte: int,
    citacao: str,
) -> tuple[Cte, str]:
    end_emit = ENDERECO_TRANSPORTADORA[forn.id]
    uf_emit = end_emit["UF"]
    cuf = UF_CODIGO[uf_emit]
    cnpj_emit = _digitos(forn.cnpj_ficticio or "")
    cnpj_cliente = _digitos(cliente.cnpj_ficticio)
    cnpj_tomador = _digitos(TOMADOR_PADRAO.cnpj or "")

    inicio = MUNICIPIO_PORTO[proc.destino_locode]
    fim = CIDADES_CLIENTE[int(cliente.id[-2:]) % len(CIDADES_CLIENTE)]
    codigo = rng.randrange(10**8)
    chave = chave_cte(cuf, emissao, cnpj_emit, n_cte, codigo)

    total = sum((v for _, v in componentes), Decimal(0))
    hora = f"{rng.randint(7, 19):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"
    I = T.Tcte.InfCte  # noqa: E741, N806  (nome curto do tipo gerado)

    ide = I.Ide(
        cUF=G.TcodUfIbge(cuf),
        cCT=f"{codigo:08d}",
        CFOP="5353" if inicio[2] == fim[2] else "6353",
        natOp="Prestação de serviço de transporte",
        mod=G.TmodCt("57"),
        serie=SERIE,
        nCT=str(n_cte),
        dhEmi=f"{emissao.isoformat()}T{hora}-03:00",
        tpImp=T.IdeTpImp("1"),
        tpEmis=T.IdeTpEmis2("1"),
        cDV=chave[-1],
        tpAmb=G.Tamb("2"),  # homologação: o DACTE sai "SEM VALOR FISCAL"
        tpCTe=T.TfinCte("0"),
        procEmi=T.TprocEmiCte("0"),
        verProc="SYNTH-1.0",
        cMunEnv=end_emit["cMun"],
        xMunEnv=end_emit["xMun"],
        UFEnv=G.Tuf(uf_emit),
        modal=E.TmodTransp("01"),  # rodoviário
        tpServ=T.IdeTpServ3("0"),  # normal
        cMunIni=inicio[0],
        xMunIni=inicio[1],
        UFIni=G.Tuf(inicio[2]),
        cMunFim=fim[0],
        xMunFim=fim[1],
        UFFim=G.Tuf(fim[2]),
        retira=T.IdeRetira("1"),  # não
        indIEToma=T.IdeIndIetoma("9"),  # não contribuinte
        toma4=I.Ide.Toma4(
            toma=T.Toma4Toma1("4"),  # outros: o agente de carga
            CNPJ=cnpj_tomador,
            xNome=TOMADOR_PADRAO.nome,
            enderToma=_ende(
                T.Tendereco,
                {
                    "xLgr": "Rua Fictícia", "nro": "100", "xBairro": "Centro",
                    "cMun": "2304400", "xMun": "Fortaleza", "UF": "CE", "CEP": "60000000",
                },
                G.Tuf,
            ),
        ),
    )  # fmt: skip

    infcte = I(
        versao=VERSAO,
        Id=f"CTe{chave}",
        ide=ide,
        compl=I.Compl(xObs=citacao),
        emit=I.Emit(
            CNPJ=cnpj_emit,
            IE=f"{rng.randrange(10**9):09d}",
            xNome=forn.nome,
            enderEmit=_ende(T.TendeEmi, end_emit, G.TufSemEx),
            CRT=T.Tcrt("3"),
        ),
        rem=I.Rem(
            CNPJ=cnpj_cliente,
            IE="ISENTO",
            xNome=cliente.nome,
            enderReme=_ende(
                T.Tendereco, _endereco_municipio(inicio, "Terminal Portuário (fictício)"), G.Tuf
            ),
        ),
        dest=I.Dest(
            CNPJ=cnpj_cliente,
            IE="ISENTO",
            xNome=cliente.nome,
            enderDest=_ende(
                T.Tendereco, _endereco_municipio(fim, "Rua do Cliente (fictícia)"), G.Tuf
            ),
        ),
        vPrest=I.VPrest(
            vTPrest=_valor(total),
            vRec=_valor(total),
            comp=[I.VPrest.Comp(xNome=nome, vComp=_valor(v)) for nome, v in componentes],
        ),
        imp=I.Imp(
            ICMS=T.Timp(ICMSSN=T.Timp.Icmssn(CST=T.IcmssnCst("90"), indSN=T.IcmssnIndSn("1")))
        ),
        infCTeNorm=I.InfCteNorm(
            infCarga=I.InfCteNorm.InfCarga(
                vCarga=_valor(Decimal(rng.randint(150_000, 400_000))),
                proPred="MERCADORIAS EM GERAL",
                infQ=[
                    I.InfCteNorm.InfCarga.InfQ(
                        cUnid=T.InfQCUnid("01"),
                        tpMed="PESO BRUTO",
                        qCarga=f"{rng.randint(8000, 26000)}.0000",
                    )
                ],
            ),
            infDoc=I.InfCteNorm.InfDoc(
                infNFe=[
                    I.InfCteNorm.InfDoc.InfNfe(
                        chave=chave_nfe_ficticia(rng, cuf, emissao, cnpj_cliente)
                    )
                    for _ in range(rng.randint(1, 3))
                ]
            ),
            infModal=I.InfCteNorm.InfModal(
                versaoModal=VERSAO, any_element=Rodo(RNTRC=f"{rng.randrange(10**8):08d}")
            ),
        ),
    )
    return Cte(infCte=infcte), chave


def gerar_ctes(rng: random.Random, mundo: Mundo) -> list[CteGerado]:
    """Um CT-e por processo com trecho rodoviário; cada componente do frete é uma linha."""
    forn = {f.id: f for f in mundo.fornecedores}
    cli = {c.id: c for c in mundo.clientes}
    provs: dict[uuid.UUID, list[Provisao]] = {}
    for p in mundo.provisoes:
        if forn[p.fornecedor_id].tipo == "transportadora":
            provs.setdefault(p.processo_id, []).append(p)

    pendentes: list[tuple[Processo, Fornecedor, date]] = []
    for proc in mundo.processos:
        if proc.transportadora_id and proc.id in provs:
            pendentes.append(
                (proc, forn[proc.transportadora_id], proc.eta + timedelta(days=rng.randint(0, 10)))
            )
    ordem = {f.id: i for i, f in enumerate(mundo.fornecedores)}
    pendentes.sort(key=lambda x: (ordem[x[1].id], x[2], x[0].codigo))

    contador: dict[str, int] = {}
    gerados: list[CteGerado] = []
    for proc, transp, emissao in pendentes:
        atual = contador.get(transp.id)
        contador[transp.id] = rng.randint(100, 900) if atual is None else atual + rng.randint(1, 20)
        n_cte = contador[transp.id]

        ordem_codigo = list(COMPONENTES)
        meus = sorted(
            (
                p
                for p in provs[proc.id]
                if p.fornecedor_id == transp.id and p.codigo_custo in COMPONENTES
            ),
            key=lambda p: ordem_codigo.index(p.codigo_custo),
        )
        valores = [_valor_da_linha(rng, p.valor) for p in meus]
        componentes = [(COMPONENTES[p.codigo_custo], v) for p, v in zip(meus, valores, strict=True)]

        ref = _referencia_citada(proc)
        conteineres = [r for r in proc.referencias if r.tipo == "conteiner"]
        citacao = (
            f"REF: {ref.valor if ref else '-'} / CNTR: {', '.join(r.valor for r in conteineres)}"
        )

        cte, chave = _montar(
            rng, proc, transp, cli[proc.cliente_id], componentes, emissao, n_cte, citacao
        )
        doc_id = uuid.UUID(int=rng.getrandbits(128), version=4)
        linhas = [
            LinhaSintetica(
                descricao=nome,
                valor_unit=v,
                valor=v,
                moeda="BRL",
                codigo_custo=p.codigo_custo,
                processo_id=proc.id,
                provisao_id=p.id,
            )
            for p, (nome, v) in zip(meus, componentes, strict=True)
        ]
        doc = DocumentoSintetico(
            id=doc_id,
            tipo="cte",
            fornecedor_id=transp.id,
            emitente=Emitente(
                nome=transp.nome,
                endereco=f"{ENDERECO_TRANSPORTADORA[transp.id]['xLgr']}, "
                f"{ENDERECO_TRANSPORTADORA[transp.id]['nro']}, "
                f"{ENDERECO_TRANSPORTADORA[transp.id]['xMun']}/{ENDERECO_TRANSPORTADORA[transp.id]['UF']}"
                " (endereço fictício)",
                cnpj=transp.cnpj_ficticio,
                email=f"faturamento@{transp.dominio_email}",
            ),
            processo_id=proc.id,
            numero=f"{SERIE}-{n_cte:06d}",
            emissao=emissao,
            vencimento=emissao + timedelta(days=rng.choice((15, 30))),
            moeda="BRL",
            linhas=linhas,
            total=sum((linha.valor for linha in linhas), Decimal(0)),
            formato="xml",
            estilo_id=transp.estilo_id,
            arquivo=f"documentos/{doc_id}.xml",
            chave_acesso=chave,
            referencias=([Referencia(tipo=ref.tipo, valor=ref.valor)] if ref else []) + conteineres,
        )
        gerados.append(CteGerado(documento=doc, xml=cte.to_xml(), chave=chave))
    return gerados


# ---------------------------------------------------------- XML e validação


def validar_xml(xml: str) -> list[str]:
    """Valida contra o XSD 4.00 da nfelib, ignorando só a ausência da assinatura."""
    return [e for e in Cte.schema_validation(xml) if "Signature" not in e]


def ler_xml(xml: str) -> Cte:
    return Cte.from_xml(xml)


def gravar_xml(cte: CteGerado, saida_dir: str | Path) -> Path:
    """Grava o XML (UTF-8, com declaração) em `saida_dir / documento.arquivo`."""
    arquivo = cte.documento.arquivo
    if arquivo is None:
        raise ValueError(f"CT-e {cte.documento.numero} sem `arquivo`")
    destino = Path(saida_dir) / arquivo
    destino.parent.mkdir(parents=True, exist_ok=True)
    corpo = (
        cte.xml
        if cte.xml.lstrip().startswith("<?xml")
        else '<?xml version="1.0" encoding="UTF-8"?>\n' + cte.xml
    )
    destino.write_text(corpo, encoding="utf-8", newline="\n")
    return destino


# --------------------------------------------------------------------- DACTE


def gerar_dacte(xml_path: str | Path, saida_pdf: str | Path) -> Path:
    """DACTE em PDF a partir do XML do CT-e (brazilfiscalreport). Sem valor fiscal.

    A data de criação do PDF é a de emissão do CT-e (`dhEmi`), então o arquivo sai idêntico a
    cada execução (o `/ID` do fpdf2 é um hash do conteúdo).
    """
    from brazilfiscalreport.dacte import Dacte

    destino = Path(saida_pdf)
    destino.parent.mkdir(parents=True, exist_ok=True)
    texto = Path(xml_path).read_text(encoding="utf-8")
    if texto.lstrip().startswith("<?xml"):  # o parser do DACTE não aceita a declaração de encoding
        texto = texto.split("?>", 1)[1]
    dacte = Dacte(xml=texto)
    emissao = re.search(r"<dhEmi>([^<]+)</dhEmi>", texto)
    if emissao:
        dacte.set_creation_date(datetime.fromisoformat(emissao.group(1)))
    dacte.output(str(destino))
    return destino
