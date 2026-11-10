"""Mundo sintético, parte 1: fornecedores e clientes fictícios.

Os 15 fornecedores são fixos (definidos aqui, não sorteados) para dar estabilidade ao
dataset; o `rng` só entra nos CNPJs fictícios. Nenhum nome corresponde a empresa real
conhecida (checado por busca na web em 2026-11-10; nomes vizinhos de empresas reais, como
"Atlantic Ocean Line" ou "Boreal Shipping", são apenas parecidos) e todos os e-mails
terminam em `.example` (RFC 2606).

CNPJs fictícios: dígitos verificadores corretos, mas a raiz sempre começa em `00.000.`
(ex. `00.000.123/0001-45`), o que torna óbvio que são falsos. A faixa 001 a 499 é dos
fornecedores e a 500 a 999 dos clientes, para nunca colidirem. A raiz `00.000.000` é evitada
porque pertence a uma instituição real.
"""

import json
import math
import random
import re
import unicodedata
import uuid
from collections.abc import Callable
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from functools import partial
from itertools import combinations
from pathlib import Path

from confere_core.costcode.catalogo import Catalogo
from confere_core.validators import iso6346
from confere_synth.custos import CAMINHO_PADRAO, CustosTipicos
from confere_synth.modelos import (
    Cliente,
    Fornecedor,
    Modal,
    Mundo,
    Processo,
    Provisao,
    Referencia,
    TipoFornecedor,
)

_PESOS_DV1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_DV2 = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_REGEX_CNPJ = re.compile(r"^(\d{2})\.(\d{3})\.(\d{3})/(\d{4})-(\d{2})$")

FAIXA_FORNECEDORES = range(1, 500)
FAIXA_CLIENTES = range(500, 1000)


def _dv(digitos: list[int], pesos: tuple[int, ...]) -> int:
    resto = sum(d * p for d, p in zip(digitos, pesos, strict=True)) % 11
    return 0 if resto < 2 else 11 - resto


def gerar_cnpj_ficticio(rng: random.Random, faixa: range = FAIXA_FORNECEDORES) -> str:
    """CNPJ com raiz `00.000.XXX`, filial 0001 e dígitos verificadores válidos."""
    sufixo_raiz = rng.choice(faixa)
    base = [0, 0, 0, 0, 0, *(int(c) for c in f"{sufixo_raiz:03d}"), 0, 0, 0, 1]
    base.append(_dv(base, _PESOS_DV1))
    base.append(_dv(base, _PESOS_DV2))
    s = "".join(str(d) for d in base)
    return f"{s[:2]}.{s[2:5]}.{s[5:8]}/{s[8:12]}-{s[12:]}"


def cnpj_valido(cnpj: str) -> bool:
    m = _REGEX_CNPJ.match(cnpj)
    if not m:
        return False
    digitos = [int(c) for c in "".join(m.groups())]
    if len(set(digitos)) == 1:
        return False
    return (
        _dv(digitos[:12], _PESOS_DV1) == digitos[12]
        and _dv(digitos[:13], _PESOS_DV2) == digitos[13]
    )


def _unico(rng: random.Random, faixa: range, usados: set[str]) -> str:
    while True:
        cnpj = gerar_cnpj_ficticio(rng, faixa)
        if cnpj not in usados:
            usados.add(cnpj)
            return cnpj


# id, nome, tipo, pais, idioma, moeda, dominio, estilo, aliases, taxas (codigo → nomes)
_Spec = tuple[str, str, TipoFornecedor, str, str, str, str, int, list[str], dict[str, list[str]]]

_ESPECIFICACOES: list[_Spec] = [
    # ------------------------------------------------ armadores / NVOCC (EN, USD)
    (
        "atlantida-ocean-lines",
        "Atlântida Ocean Lines",
        "armador",
        "SG",
        "en",
        "USD",
        "atlantida-ocean.example",
        1,
        [
            "Atlântida Ocean Lines Pte. Ltd.",
            "Atlantida Ocean Lines",
            "ATLANTIDA OCEAN LINES PTE LTD",
        ],
        {
            "FRETE_MAR": ["Ocean Freight", "O/F"],
            "BAF": ["Bunker Adjustment Factor", "BAF"],
            "CAF": ["Currency Adjustment Factor"],
            "THC_ORIG": ["Origin Terminal Handling Charge", "OTHC"],
            "BL_FEE": ["B/L Fee", "Bill of Lading Fee"],
            "DOC_FEE_ORIG": ["Documentation Fee"],
            "DEMURRAGE": ["Demurrage Charge"],
        },
    ),
    (
        "boreal-container-line",
        "Boreal Container Line",
        "armador",
        "NO",
        "en",
        "USD",
        "boreal-line.example",
        1,
        ["Boreal Container Line AS", "BOREAL CONTAINER LINE", "Boreal CL"],
        {
            "FRETE_MAR": ["Sea Freight", "Ocean Freight FCL"],
            "BAF": ["Bunker Surcharge", "BAF"],
            "PSS": ["Peak Season Surcharge", "PSS"],
            "THC_ORIG": ["THC Origin", "Terminal Handling - Origin"],
            "BL_FEE": ["BL Issuance Fee", "BL Fee"],
            "LIBERACAO_BL": ["Release Fee", "Telex Release"],
            "DETENTION": ["Detention", "Container Detention"],
            "CORRECAO_BL": ["BL Amendment Fee"],
        },
    ),
    (
        "tarquin-marine-lines",
        "Tarquin Marine Lines",
        "armador",
        "GB",
        "en",
        "USD",
        "tarquin-marine.example",
        1,
        ["Tarquin Marine Lines Ltd", "TARQUIN MARINE LINES LTD.", "Tarquin Marine"],
        {
            "FRETE_MAR": ["Freight", "Ocean Frt"],
            "BAF": ["Bunker Adj. Factor"],
            "CAF": ["CAF", "Currency Adj Factor"],
            "ISPS": ["ISPS Surcharge"],
            "BL_FEE": ["Bill of Lading Fee", "B/L Issuance"],
            "DOC_FEE_ORIG": ["Origin Documentation Fee", "Doc Fee"],
            "DEMURRAGE": ["Demurrage", "DEM"],
        },
    ),
    # NVOCC NACIONAL: cobra em BRL (PTAX da emissão) o que está previsto em USD. É o cenário do
    # erro "câmbio errado" (CF-36); fatura em PT, no estilo 3.
    (
        "consolidadora-aurora",
        "Consolidadora Marítima Aurora Ltda.",
        "armador",
        "BR",
        "pt",
        "BRL",
        "consolidadora-aurora.example",
        3,
        ["Consolidadora Aurora", "CONSOLIDADORA MARITIMA AURORA LTDA", "Aurora NVOCC"],
        {
            "FRETE_MAR": ["Frete Marítimo", "Frete Internacional"],
            "BAF": ["Ajuste de Combustível (BAF)", "BAF"],
            "THC_ORIG": ["THC Origem", "Terminal Handling Origem"],
            "BL_FEE": ["Emissão de BL", "Taxa de BL"],
            "DOC_FEE_ORIG": ["Taxa de Documentação"],
        },
    ),
    # ------------------------------------------------- agentes no exterior (EN)
    (
        "jade-river-logistics",
        "Jade River Logistics Co., Ltd.",
        "agente_exterior",
        "CN",
        "en",
        "CNY",
        "jaderiver-logistics.example",
        2,
        ["Jade River Logistics", "JADE RIVER LOGISTICS CO LTD", "Jade River Logistics (Shenzhen)"],
        {
            "FRETE_MAR": ["Ocean Freight", "Sea Freight"],
            "THC_ORIG": ["Origin THC", "OTHC"],
            "DOC_FEE_ORIG": ["Documentation Fee", "Doc Fee"],
            "HANDLING_AGENTE": ["Handling Fee", "Agent Handling"],
            "COURIER": ["Courier Charge", "Document Courier"],
            "BL_FEE": ["B/L Fee"],
        },
    ),
    (
        "nordhaven-freight",
        "Nordhaven Freight Partners GmbH",
        "agente_exterior",
        "DE",
        "en",
        "EUR",
        "nordhaven-freight.example",
        2,
        ["Nordhaven Freight Partners", "NORDHAVEN FREIGHT PARTNERS GMBH", "Nordhaven Freight"],
        {
            "FRETE_MAR": ["Ocean Freight", "Seefracht"],
            "THC_ORIG": ["Terminal Handling Origin", "Origin Terminal Charges"],
            "BL_FEE": ["Bill of Lading Fee", "BL Fee"],
            "HANDLING_AGENTE": ["Agent Handling Fee", "Handling"],
            "DOC_FEE_ORIG": ["Documentation Fee"],
            "CORRECAO_BL": ["BL Correction Fee", "Amendment Fee"],
            "COURIER": ["Courier"],
        },
    ),
    # ---------------------------------------------------------- terminais (PT)
    (
        "terminal-mar-azul",
        "Terminal Mar Azul S.A.",
        "terminal",
        "BR",
        "pt",
        "BRL",
        "terminalmarazul.example",
        3,
        ["Terminal Mar Azul", "TERMINAL MAR AZUL S/A", "TMA Mucuripe"],
        {
            "THC_DEST": ["Capatazia", "THC Destino", "Movimentação de Contêiner"],
            "ISPS": ["Taxa ISPS"],
            "SCANNER": ["Escaneamento de Contêiner", "Scanner"],
            "LEVANTE": ["Levante", "Taxa de Levante"],
            "POSICIONAMENTO": ["Posicionamento", "Posicionamento p/ Vistoria"],
            "ARMAZENAGEM": ["Armazenagem", "Armazenagem Período"],
        },
    ),
    (
        "terminal-cajueiro-pecem",
        "Terminal Portuário Cajueiro de Pecém Ltda.",
        "terminal",
        "BR",
        "pt",
        "BRL",
        "cajueiro-pecem.example",
        3,
        ["Terminal Cajueiro Pecém", "TERM. CAJUEIRO PECEM", "Cajueiro Pecém"],
        {
            "THC_DEST": ["DTHC", "Taxa de Movimentação Destino"],
            "ISPS": ["ISPS Code", "Proteção Portuária ISPS"],
            "LEVANTE": ["Levante de Contêiner"],
            "SCANNER": ["Taxa de Scanner"],
            "POSICIONAMENTO": ["Posic. de Contêiner", "Posicionamento"],
        },
    ),
    (
        "terminal-mare-alta-suape",
        "Terminal Maré Alta Suape S.A.",
        "terminal",
        "BR",
        "pt",
        "BRL",
        "marealta-suape.example",
        3,
        ["Terminal Maré Alta", "TERMINAL MARE ALTA SUAPE", "Maré Alta Suape"],
        {
            "THC_DEST": ["THC Dest", "Capatazia Importação"],
            "ISPS": ["ISPS"],
            "ARMAZENAGEM": ["Armazenagem Alfandegada", "Armaz. 1º Período"],
            "LEVANTE": ["Levante"],
            "LAVAGEM_CNTR": ["Lavagem de Contêiner"],
            "SCANNER": ["Escaneamento"],
        },
    ),
    # ------------------------------------------------ armazéns alfandegados (PT)
    (
        "armazens-gerais-carnauba",
        "Armazéns Gerais Carnaúba Ltda.",
        "armazem",
        "BR",
        "pt",
        "BRL",
        "armazens-carnauba.example",
        4,
        ["Armazéns Gerais Carnaúba", "ARMAZENS GERAIS CARNAUBA LTDA", "AG Carnaúba"],
        {
            "ARMAZENAGEM": ["Armazenagem Alfandegada", "Armazenagem"],
            "DESCONSOLIDACAO": ["Desconsolidaçao", "Desova de Carga"],
            "POSICIONAMENTO": ["Posicionamento"],
            "LEVANTE": ["Taxa de Levante"],
            "LAVAGEM_CNTR": ["Lavagem de Contêiner", "Lavagem"],
        },
    ),
    (
        "entreposto-barlavento",
        "Entreposto Alfandegado Barlavento S.A.",
        "armazem",
        "BR",
        "pt",
        "BRL",
        "entreposto-barlavento.example",
        4,
        ["Entreposto Barlavento", "ENTREPOSTO ALFANDEGADO BARLAVENTO", "EA Barlavento"],
        {
            "ARMAZENAGEM": ["Armazenagem Alfandegada - Período", "Armazenagem"],
            "DESCONSOLIDACAO": ["Desconsolidação", "Taxa de Desconsolidação"],
            "SCANNER": ["Scanner"],
            "POSICIONAMENTO": ["Posic. Contêiner"],
            "LEVANTE": ["Levante"],
        },
    ),
    # ----------------------------------------------- transportadoras rodoviárias
    (
        "transportadora-mandacaru",
        "Transportadora Mandacaru Ltda.",
        "transportadora",
        "BR",
        "pt",
        "BRL",
        "transp-mandacaru.example",
        3,
        ["Transportadora Mandacaru", "TRANSP MANDACARU LTDA", "Mandacaru Transportes"],
        {
            "FRETE_RODO": ["Frete Rodoviário", "Transporte Rodoviário"],
            "PEDAGIO": ["Pedágio", "Vale Pedágio"],
            "GRIS": ["GRIS", "Gerenc. de Risco"],
            "AD_VALOREM_SEGURO": ["Ad Valorem", "Seguro Carga"],
        },
    ),
    (
        "rodoviario-ventania",
        "Rodoviário Ventania Cargas Ltda.",
        "transportadora",
        "BR",
        "pt",
        "BRL",
        "rodoviario-ventania.example",
        3,
        ["Rodoviário Ventania", "RODOVIARIO VENTANIA CARGAS", "Ventania Cargas"],
        {
            "FRETE_RODO": ["Frete Terrestre", "Frete Peso/Valor"],
            "PEDAGIO": ["Pedagio", "Pedágio"],
            "GRIS": ["Taxa GRIS"],
            "AD_VALOREM_SEGURO": ["Ad Valorem", "Prêmio de Seguro"],
        },
    ),
    # ------------------------------------------------------------ despachantes
    (
        "despachos-farol",
        "Despachos Aduaneiros Farol Ltda.",
        "despachante",
        "BR",
        "pt",
        "BRL",
        "despachos-farol.example",
        5,
        ["Despachos Farol", "DESPACHOS ADUANEIROS FAROL LTDA", "Farol Despachos"],
        {
            "HONORARIO_DESPACHO": ["Honorários de Despacho", "Honorarios Despachante"],
            "SDA": ["SDA", "Taxa Sindical"],
            "EMISSAO_LI": ["Emissão de LI", "Licença de Importação"],
            "SISCOMEX": ["Taxa Siscomex", "Siscomex"],
            "COURIER": ["Courier", "Malote"],
            "AFRMM": ["AFRMM"],
        },
    ),
    (
        "lagoa-azul-assessoria",
        "Lagoa Azul Assessoria Aduaneira Ltda.",
        "despachante",
        "BR",
        "pt",
        "BRL",
        "lagoaazul-aduaneira.example",
        5,
        ["Lagoa Azul Assessoria", "LAGOA AZUL ASSESSORIA ADUANEIRA", "Lagoa Azul Aduaneira"],
        {
            "HONORARIO_DESPACHO": ["Honorário Despacho Aduaneiro", "Comissão de Despacho"],
            "SDA": ["Sindicato dos Despachantes", "Taxa SDA"],
            "SISCOMEX": ["Taxa de Utilização Siscomex"],
            "EMISSAO_LI": ["Taxa de LI"],
            "AFRMM": ["Adic. Frete Renov. Marinha Mercante", "AFRMM"],
        },
    ),
]

_NOMES_CLIENTES = [
    "Importadora Jangada Ltda.",
    "Comercial Xique-Xique S.A.",
    "Indústria Têxtil Bem-te-vi Ltda.",
    "Distribuidora Caatinga Norte Ltda.",
    "Calçados Ipê Roxo S.A.",
    "Móveis Pau-Brasil do Nordeste Ltda.",
    "Agroinsumos Vale do Jaguaribe Ltda.",
    "Eletro Brisa Mar Comércio Ltda.",
    "Alimentos Cajueiro Dourado S.A.",
    "Plásticos Mandarová Ltda.",
    "Autopeças Estrela do Norte Ltda.",
    "Brinquedos Pipa Colorida Ltda.",
]


def gerar_fornecedores(rng: random.Random, catalogo: Catalogo) -> list[Fornecedor]:
    """15 fornecedores fixos em 6 tipos; o `rng` só define os CNPJs dos nacionais."""
    conhecidos = set(catalogo.codigos())
    usados: set[str] = set()
    fornecedores: list[Fornecedor] = []
    for id_, nome, tipo, pais, idioma, moeda, dominio, estilo, aliases, taxas in _ESPECIFICACOES:
        desconhecidos = sorted(set(taxas) - conhecidos)
        if desconhecidos:
            raise ValueError(f"{id_}: códigos fora do catálogo: {desconhecidos}")
        fornecedores.append(
            Fornecedor(
                id=id_,
                nome=nome,
                tipo=tipo,
                pais=pais,
                idioma=idioma,
                moeda_padrao=moeda,
                dominio_email=dominio,
                estilo_id=estilo,
                aliases=aliases,
                nomes_taxa=taxas,
                codigos=list(taxas),
                cnpj_ficticio=_unico(rng, FAIXA_FORNECEDORES, usados) if pais == "BR" else None,
            )
        )
    return fornecedores


def gerar_clientes(rng: random.Random, n: int = 12) -> list[Cliente]:
    """Importadores fictícios, marcados "(fictícia)" no nome."""
    if not 1 <= n <= len(_NOMES_CLIENTES):
        raise ValueError(f"n deve estar entre 1 e {len(_NOMES_CLIENTES)}: {n}")
    usados: set[str] = set()
    return [
        Cliente(
            id=f"cliente-{i:02d}",
            nome=f"{nome} (fictícia)",
            cnpj_ficticio=_unico(rng, FAIXA_CLIENTES, usados),
        )
        for i, nome in enumerate(_NOMES_CLIENTES[:n], start=1)
    ]


# ---------------------------------------------------------------- processos

# UN/LOCODE, nome e peso. Origens: ~65% China, ~35% Europa.
_ORIGENS: list[tuple[str, str, int]] = [
    ("CNSHA", "Shanghai", 25),
    ("CNNGB", "Ningbo", 20),
    ("CNSZX", "Shenzhen", 20),
    ("NLRTM", "Rotterdam", 10),
    ("DEHAM", "Hamburg", 10),
    ("BEANR", "Antwerp", 8),
    ("ESVLC", "Valencia", 7),
]
_DESTINOS: list[tuple[str, str, int]] = [
    ("BRFOR", "Fortaleza", 35),
    ("BRPEC", "Pecém", 25),
    ("BRSUA", "Suape", 25),
    ("BRSSZ", "Santos", 15),
]
# Terminal e armazém por porto de destino. Santos não tem terminal entre os 14 fornecedores
# fixos, então os processos de Santos ficam sem `terminal_id`.
_TERMINAL_POR_DESTINO = {
    "BRFOR": "terminal-mar-azul",
    "BRPEC": "terminal-cajueiro-pecem",
    "BRSUA": "terminal-mare-alta-suape",
}
_ARMAZEM_POR_DESTINO = {
    "BRFOR": "armazens-gerais-carnauba",
    "BRPEC": "armazens-gerais-carnauba",
    "BRSUA": "entreposto-barlavento",
    "BRSSZ": "entreposto-barlavento",
}
_PRIMEIRAS_PALAVRAS_NAVIO = [
    "Boreal", "Austral", "Horizonte", "Coral", "Tamoio", "Estrela", "Maré", "Jacarandá",
    "Pampa", "Aurora",
]  # fmt: skip
_SEGUNDAS_PALAVRAS_NAVIO = [
    "Aurora", "Voyager", "Star", "Spirit", "Grace", "Venture", "Pioneer", "Harmony",
]  # fmt: skip

ETD_INICIO = date(2026, 8, 1)
ETD_FIM = date(2026, 10, 15)
PCT_RODOVIARIO = 0.15
PCT_MARITIMO_COM_TRECHO_RODOVIARIO = 0.30


def _escolher(rng: random.Random, opcoes: list[tuple[str, str, int]]) -> tuple[str, str]:
    codigo, nome, _ = rng.choices(opcoes, weights=[o[2] for o in opcoes])[0]
    return codigo, nome


def _prefixo_bl(armador: Fornecedor) -> str:
    """`ATLX`, `BORX`, `TARX`: 3 primeiras letras do nome (sem acento) + X."""
    primeira = armador.nome.split()[0]
    letras = unicodedata.normalize("NFKD", primeira).encode("ascii", "ignore").decode()
    return letras[:3].upper() + "X"


def _digitos(rng: random.Random, n: int) -> str:
    return f"{rng.randrange(10**n):0{n}d}"


def _bl_master(rng: random.Random, prefixo: str) -> str:
    return prefixo + _digitos(rng, 9)


def _bl_house(rng: random.Random, cidade: str) -> str:
    return f"HBL-{cidade}-" + _digitos(rng, 6)


def _pedido(rng: random.Random, usa_po: bool) -> str:
    return f"PO-{_digitos(rng, 5)}" if usa_po else f"PEDIDO {_digitos(rng, 5)}"


def _novo(usados: set[str], gerar: Callable[[], str]) -> str:
    """Gera até achar um valor ainda não usado (regera em colisão)."""
    while True:
        valor = gerar()
        if valor not in usados:
            usados.add(valor)
            return valor


def gerar_processos(
    rng: random.Random,
    clientes: list[Cliente],
    fornecedores: list[Fornecedor],
    n: int = 50,
) -> list[Processo]:
    """`n` processos de importação. Proporções por cota (não por sorteio): 15% só
    rodoviários e, dos marítimos, 30% com trecho rodoviário posterior (transportadora + CT-e).

    Processos só rodoviários não têm armador, agente, terminal, navio nem `bl_master`; o
    trânsito deles dura 2 a 7 dias. Nenhum valor de referência se repete entre processos.
    """
    por_tipo: dict[str, list[Fornecedor]] = {}
    for f in fornecedores:
        por_tipo.setdefault(f.tipo, []).append(f)
    for tipo in ("armador", "agente_exterior", "despachante", "transportadora"):
        if not por_tipo.get(tipo):
            raise ValueError(f"sem fornecedor do tipo {tipo}")

    n_rodoviarios = round(n * PCT_RODOVIARIO)
    n_maritimos = n - n_rodoviarios
    n_com_trecho = round(n_maritimos * PCT_MARITIMO_COM_TRECHO_RODOVIARIO)
    perfis: list[tuple[Modal, bool]] = []
    perfis += [("rodoviario", True)] * n_rodoviarios
    perfis += [("maritimo", True)] * n_com_trecho
    perfis += [("maritimo", False)] * (n_maritimos - n_com_trecho)
    rng.shuffle(perfis)

    usados: set[str] = set()
    dias = (ETD_FIM - ETD_INICIO).days
    processos: list[Processo] = []

    for i, (modal, com_transportadora) in enumerate(perfis, start=1):
        pid = uuid.UUID(int=rng.getrandbits(128), version=4)
        cliente = rng.choice(clientes)
        etd = ETD_INICIO + timedelta(days=rng.randint(0, dias))
        despachante = rng.choice(por_tipo["despachante"])
        transportadora = rng.choice(por_tipo["transportadora"]) if com_transportadora else None
        refs: list[Referencia] = []

        armador_id: str | None = None
        agente_id: str | None = None
        terminal_id: str | None = None
        navio: str | None = None
        viagem: str | None = None

        if modal == "maritimo":
            o_loc, o_nome = _escolher(rng, _ORIGENS)
            d_loc, d_nome = _escolher(rng, _DESTINOS)
            armador = rng.choice(por_tipo["armador"])
            pais_agente = "CN" if o_loc.startswith("CN") else "DE"
            agentes = [a for a in por_tipo["agente_exterior"] if a.pais == pais_agente]
            agente = rng.choice(agentes or por_tipo["agente_exterior"])
            armador_id, agente_id = armador.id, agente.id
            terminal_id = _TERMINAL_POR_DESTINO.get(d_loc)
            navio = (
                f"MV {rng.choice(_PRIMEIRAS_PALAVRAS_NAVIO)} {rng.choice(_SEGUNDAS_PALAVRAS_NAVIO)}"
            )
            viagem = f"{rng.randint(1, 199):03d}{rng.choice('WE')}"
            eta = etd + timedelta(days=rng.randint(25, 45))
            prefixo = _prefixo_bl(armador)
            bl_master = _novo(usados, partial(_bl_master, rng, prefixo))
            refs.append(Referencia(tipo="bl_master", valor=bl_master))
        else:
            # trecho nacional puro, entre portos brasileiros distintos
            o_loc, o_nome = _escolher(rng, _DESTINOS)
            d_loc, d_nome = _escolher(rng, [d for d in _DESTINOS if d[0] != o_loc])
            eta = etd + timedelta(days=rng.randint(2, 7))

        cidade = d_loc[2:]
        for _ in range(rng.randint(1, 2)):
            hbl = _novo(usados, partial(_bl_house, rng, cidade))
            refs.append(Referencia(tipo="bl_house", valor=hbl))
        for _ in range(rng.randint(1, 4)):
            refs.append(
                Referencia(tipo="conteiner", valor=_novo(usados, lambda: iso6346.gerar(rng)))
            )
        usa_po = rng.random() < 0.5
        pedido = _novo(usados, partial(_pedido, rng, usa_po))
        refs.append(Referencia(tipo="ref_cliente", valor=pedido))
        if modal == "maritimo" and rng.random() < 0.4:
            ref = _novo(usados, lambda: f"AGT-2026-{_digitos(rng, 5)}")
            refs.append(Referencia(tipo="ref_agente", valor=ref))

        processos.append(
            Processo(
                id=pid,
                codigo=f"IMP-2026-{i:04d}",
                cliente_id=cliente.id,
                modal=modal,
                origem=o_nome,
                origem_locode=o_loc,
                destino=d_nome,
                destino_locode=d_loc,
                navio=navio,
                viagem=viagem,
                etd=etd,
                eta=eta,
                armador_id=armador_id,
                agente_exterior_id=agente_id,
                terminal_id=terminal_id,
                armazem_id=_ARMAZEM_POR_DESTINO[d_loc],
                despachante_id=despachante.id,
                transportadora_id=transportadora.id if transportadora else None,
                referencias=refs,
            )
        )
    return processos


# ---------------------------------------------------------------- provisões

FAIXA_PROVISOES_MARITIMO = (8, 15)
FAIXA_PROVISOES_RODOVIARIO = (6, 8)
PCT_PROCESSOS_PAR_PROXIMO = 0.25  # meta; o requisito mínimo é 20%
TOLERANCIA_PAR_PROXIMO = Decimal("0.12")  # maior/menor <= 1 + tolerância
_CENTAVO = Decimal("0.01")


def _arredondar(valor: Decimal) -> Decimal:
    """2 casas (ROUND_HALF_EVEN) e sempre positivo."""
    return max(valor.quantize(_CENTAVO, rounding=ROUND_HALF_EVEN), _CENTAVO)


def _fator_ruido(rng: random.Random, ruido_rel: float) -> Decimal:
    fator = max(1 + rng.gauss(0, ruido_rel), 0.2)
    return Decimal(str(round(fator, 6)))


def _converter(valor: Decimal, de: str, para: str, cambio: dict[str, Decimal]) -> Decimal:
    return valor * cambio[de] / cambio[para]


def _ligados(proc: Processo, por_id: dict[str, Fornecedor]) -> list[Fornecedor]:
    ids = (
        proc.armador_id,
        proc.agente_exterior_id,
        proc.terminal_id,
        proc.armazem_id,
        proc.despachante_id,
        proc.transportadora_id,
    )
    ausentes = [i for i in ids if i and i not in por_id]
    if ausentes:
        raise ValueError(f"{proc.codigo}: fornecedor ausente: {ausentes}")
    return [por_id[i] for i in ids if i]


def _selecionar(
    rng: random.Random,
    proc: Processo,
    candidatos: dict[str, list[Fornecedor]],
    custos: CustosTipicos,
    ordem: dict[str, int],
) -> list[str]:
    """Sorteia os códigos do processo por `prob` e ajusta à faixa do modal."""
    minimo, maximo = (
        FAIXA_PROVISOES_MARITIMO if proc.modal == "maritimo" else FAIXA_PROVISOES_RODOVIARIO
    )
    if len(candidatos) < minimo:
        raise ValueError(f"{proc.codigo}: só {len(candidatos)} códigos possíveis, mínimo {minimo}")
    sel = {c for c in candidatos if rng.random() < custos.codigos[c].prob}
    while len(sel) > maximo:  # tira opcionais (prob < 1), os menos prováveis primeiro
        opcionais = sorted((c for c in sel if custos.codigos[c].prob < 1.0), key=ordem.__getitem__)
        if not opcionais:
            raise ValueError(f"{proc.codigo}: obrigatórios demais para o máximo {maximo}")
        sel.discard(rng.choices(opcionais, [1 - custos.codigos[c].prob for c in opcionais])[0])
    while len(sel) < minimo:  # acrescenta opcionais, os mais prováveis primeiro
        faltantes = sorted((c for c in candidatos if c not in sel), key=ordem.__getitem__)
        sel.add(rng.choices(faltantes, [max(custos.codigos[c].prob, 0.05) for c in faltantes])[0])
    return sorted(sel, key=ordem.__getitem__)


def _provisoes_do_processo(
    rng: random.Random,
    proc: Processo,
    por_id: dict[str, Fornecedor],
    custos: CustosTipicos,
    ordem: dict[str, int],
) -> list[Provisao]:
    n_conteineres = sum(r.tipo == "conteiner" for r in proc.referencias)
    n_bls = sum(r.tipo == "bl_house" for r in proc.referencias)
    cif_min, cif_max = custos.cif_por_conteiner_brl
    cif = Decimal(str(round(rng.uniform(float(cif_min), float(cif_max)), 2))) * n_conteineres

    ligados = _ligados(proc, por_id)
    candidatos: dict[str, list[Fornecedor]] = {}
    for codigo in sorted(ordem, key=ordem.__getitem__):
        cfg = custos.codigos[codigo]
        fs = [f for f in ligados if codigo in f.codigos and f.tipo in cfg.tipo_fornecedor]
        if fs:
            candidatos[codigo] = fs
    for codigo in list(candidatos):  # percentual de outro código exige o código-base
        base = custos.codigos[codigo].percentual_de
        if base not in (None, "cif") and base not in candidatos:
            del candidatos[codigo]

    escolhidos = _selecionar(rng, proc, candidatos, custos, ordem)
    valores: dict[str, Decimal] = {}
    donos: dict[str, Fornecedor] = {}
    for dependente in (False, True):  # códigos-base primeiro, depois os percentuais deles
        for codigo in escolhidos:
            cfg = custos.codigos[codigo]
            if (cfg.percentual_de not in (None, "cif")) != dependente:
                continue
            donos[codigo] = rng.choice(candidatos[codigo])
            if cfg.percentual_de is None:
                quantidade = {
                    "por_conteiner": n_conteineres,
                    "por_bl": n_bls,
                    "por_processo": 1,
                    "por_dia": n_conteineres * rng.randint(*(cfg.dias or (1, 1))),
                }[cfg.unidade]
                bruto = cfg.base * quantidade
            else:
                if cfg.percentual_de == "cif":
                    referencia = _converter(cif, "BRL", cfg.moeda, custos.cambio_referencia)
                else:
                    origem = custos.codigos[cfg.percentual_de].moeda
                    referencia = _converter(
                        valores[cfg.percentual_de], origem, cfg.moeda, custos.cambio_referencia
                    )
                bruto = max(referencia * cfg.base / 100, cfg.minimo or Decimal(0))
            valores[codigo] = _arredondar(bruto * _fator_ruido(rng, cfg.ruido_rel))

    return [
        Provisao(
            id=uuid.UUID(int=rng.getrandbits(128), version=4),
            processo_id=proc.id,
            fornecedor_id=donos[codigo].id,
            codigo_custo=codigo,
            moeda=custos.codigos[codigo].moeda,
            valor=valores[codigo],
        )
        for codigo in escolhidos
    ]


def _razao(a: Decimal, b: Decimal) -> Decimal:
    return max(a, b) / min(a, b)


def _tem_par_proximo(provisoes: list[Provisao]) -> bool:
    """Duas provisões do mesmo fornecedor e moeda, em códigos diferentes, com valores até
    12% distantes (maior/menor <= 1,12)."""
    return any(
        a.fornecedor_id == b.fornecedor_id
        and a.moeda == b.moeda
        and a.codigo_custo != b.codigo_custo
        and _razao(a.valor, b.valor) <= 1 + TOLERANCIA_PAR_PROXIMO
        for a, b in combinations(provisoes, 2)
    )


def _forcar_par_proximo(
    rng: random.Random,
    provisoes: list[Provisao],
    custos: CustosTipicos,
    codigos_base: set[str],
) -> list[Provisao] | None:
    """Aproxima (±1% a ±10%) o par de mesmo fornecedor e moeda que já está mais perto.

    Só mexe em provisões com ruído, que não sejam percentuais nem código-base de percentual,
    para não quebrar relações como AFRMM = 8% do frete.
    """
    melhor: tuple[Decimal, int, int] | None = None
    for i, a in enumerate(provisoes):
        for j, b in enumerate(provisoes):
            cfg = custos.codigos[b.codigo_custo]
            if (
                i == j
                or a.fornecedor_id != b.fornecedor_id
                or a.moeda != b.moeda
                or cfg.percentual_de is not None
                or cfg.ruido_rel == 0
                or b.codigo_custo in codigos_base
            ):
                continue
            distancia = _razao(a.valor, b.valor)
            if melhor is None or distancia < melhor[0]:
                melhor = (distancia, i, j)
    if melhor is None:
        return None
    _, i, j = melhor
    delta = Decimal(str(round(rng.uniform(0.01, 0.10), 4))) * rng.choice((-1, 1))
    resultado = list(provisoes)
    resultado[j] = provisoes[j].model_copy(
        update={"valor": _arredondar(provisoes[i].valor * (1 + delta))}
    )
    return resultado


def gerar_provisoes(
    rng: random.Random,
    processos: list[Processo],
    fornecedores: list[Fornecedor],
    catalogo: Catalogo,
    custos: CustosTipicos | None = None,
) -> list[Provisao]:
    """Provisões (custo previsto) de cada processo, todas `aberta`.

    Só entram fornecedores ligados ao processo e códigos que eles cobram; cada código aparece
    no máximo uma vez por processo. Valor = base x quantidade x (1 + N(0, ruido_rel)), em
    `Decimal` com 2 casas. Marítimo tem 8 a 15 provisões e rodoviário puro 6 a 8. Em pelo
    menos 25% dos processos (requisito: 20%) há duas provisões do mesmo fornecedor e moeda
    com valores até 12% distantes, em códigos diferentes: o caso em que o casamento ótimo
    (E6) vence o guloso.
    """
    custos = custos or CustosTipicos.carregar(CAMINHO_PADRAO, catalogo)
    custos.validar(catalogo)
    por_id = {f.id: f for f in fornecedores}
    ordem = {codigo: i for i, codigo in enumerate(catalogo.codigos())}
    por_processo = [_provisoes_do_processo(rng, p, por_id, custos, ordem) for p in processos]

    codigos_base = {
        cfg.percentual_de
        for cfg in custos.codigos.values()
        if cfg.percentual_de not in (None, "cif")
    } - {None}
    meta = math.ceil(PCT_PROCESSOS_PAR_PROXIMO * len(processos))
    ja_tem = {i for i, provs in enumerate(por_processo) if _tem_par_proximo(provs)}
    faltam = meta - len(ja_tem)
    if faltam > 0:
        sem_par = [i for i in range(len(por_processo)) if i not in ja_tem]
        rng.shuffle(sem_par)
        for i in sem_par:
            if faltam <= 0:
                break
            ajustado = _forcar_par_proximo(rng, por_processo[i], custos, codigos_base)
            if ajustado is not None:
                por_processo[i] = ajustado
                faltam -= 1
    return [p for provs in por_processo for p in provs]


# -------------------------------------------------------------------- mundo


def _catalogo_padrao() -> Catalogo:
    raiz = Path(__file__).resolve().parents[4]
    return Catalogo.carregar(raiz / "config" / "codigos_custo.yaml")


def gerar_mundo(seed: int, catalogo: Catalogo | None = None) -> Mundo:
    """Mundo completo (fornecedores, clientes, processos e provisões), determinístico no `seed`."""
    rng = random.Random(seed)
    catalogo = catalogo or _catalogo_padrao()
    fornecedores = gerar_fornecedores(rng, catalogo)
    clientes = gerar_clientes(rng)
    processos = gerar_processos(rng, clientes, fornecedores)
    provisoes = gerar_provisoes(rng, processos, fornecedores, catalogo)
    return Mundo(
        seed=seed,
        fornecedores=fornecedores,
        clientes=clientes,
        processos=processos,
        provisoes=provisoes,
    )


def salvar_mundo(mundo: Mundo, saida: str | Path) -> Path:
    """Grava `mundo.json` (chaves ordenadas, indentação 2) em `saida`; devolve o caminho."""
    pasta = Path(saida)
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / "mundo.json"
    texto = json.dumps(mundo.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False)
    arquivo.write_text(texto + "\n", encoding="utf-8", newline="\n")
    return arquivo
