"""Script infra/scripts/baixar_ptax.py: parâmetros, filtro de fechamento e CSV (sem rede)."""

import importlib.util
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import httpx
import pytest

CAMINHO = Path(__file__).resolve().parents[3] / "infra" / "scripts" / "baixar_ptax.py"


def carregar_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("baixar_ptax", CAMINHO)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo  # sem isso, quem inspeciona classes do módulo dá KeyError
    spec.loader.exec_module(modulo)
    return modulo


ptax = carregar_script()


def registro(dia: str, hora: str, boletim: str, compra: str, venda: str) -> dict[str, object]:
    return {
        "paridadeCompra": 1.0, "paridadeVenda": 1.0,
        "cotacaoCompra": float(compra), "cotacaoVenda": float(venda),
        "dataHoraCotacao": f"{dia} {hora}.123456", "tipoBoletim": boletim,
    }  # fmt: skip


JSON_USD = {
    "value": [
        registro("2026-11-06", "10:04:10", "Abertura", "5.4900", "5.4906"),
        registro("2026-11-06", "13:09:11", "Fechamento", "5.5000", "5.5006"),
        registro("2026-11-09", "10:04:10", "Abertura", "5.5100", "5.5106"),
        registro("2026-11-09", "11:05:00", "Intermediário", "5.5120", "5.5126"),
        registro("2026-11-09", "13:11:19", "Fechamento", "5.5140", "5.5146"),
    ]
}


def cliente_falso(respostas: dict[str, object], chamadas: list[str] | None = None) -> httpx.Client:
    def handler(req: httpx.Request) -> httpx.Response:
        if chamadas is not None:
            chamadas.append(str(req.url))
        moeda = req.url.query.decode().split("'")[1]
        return httpx.Response(200, text=json.dumps(respostas.get(moeda, {"value": []})))

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_url_segue_o_formato_da_api() -> None:
    u = ptax.url("USD", date(2026, 7, 15), date(2026, 11, 30))
    assert u.startswith(
        "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/CotacaoMoedaPeriodo("
    )
    assert "@moeda='USD'" in u and "@dataInicial='07-15-2026'" in u
    assert "@dataFinalCotacao='11-30-2026'" in u and u.endswith("$format=json")


def test_so_o_boletim_de_fechamento_entra() -> None:
    linhas = ptax.fechamentos(JSON_USD["value"], "USD")
    assert [(ln.data, str(ln.compra), str(ln.venda)) for ln in linhas] == [
        (date(2026, 11, 6), "5.5000", "5.5006"),
        (date(2026, 11, 9), "5.5140", "5.5146"),
    ]
    assert all(isinstance(ln.venda, Decimal) for ln in linhas)


def test_dois_fechamentos_no_mesmo_dia_e_erro() -> None:
    duplicado = [
        registro("2026-11-06", "13:09:11", "Fechamento", "5.5", "5.6"),
        registro("2026-11-06", "13:10:00", "Fechamento", "5.5", "5.6"),
    ]
    with pytest.raises(ValueError, match="mais de um fechamento"):
        ptax.fechamentos(duplicado, "USD")


def test_main_grava_csv_ordenado_com_4_casas(tmp_path: Path) -> None:
    eur = {"value": [registro("2026-11-09", "13:11:19", "Fechamento", "6.1729", "6.1741")]}
    saida = tmp_path / "ptax.csv"
    codigo = ptax.main(
        [
            "--inicio",
            "2026-11-06",
            "--fim",
            "2026-11-09",
            "--moedas",
            "USD",
            "EUR",
            "--saida",
            str(saida),
        ],
        cliente_falso({"USD": JSON_USD, "EUR": eur}),
    )
    assert codigo == 0
    assert saida.read_text(encoding="utf-8") == (
        "data,moeda,compra,venda,boletim\n"
        "2026-11-06,USD,5.5000,5.5006,Fechamento\n"
        "2026-11-09,EUR,6.1729,6.1741,Fechamento\n"
        "2026-11-09,USD,5.5140,5.5146,Fechamento\n"
    )


def test_moeda_sem_ptax_avisa_e_nao_inventa(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    saida = tmp_path / "ptax.csv"
    codigo = ptax.main(
        [
            "--inicio",
            "2026-11-06",
            "--fim",
            "2026-11-09",
            "--moedas",
            "USD",
            "CNY",
            "--saida",
            str(saida),
        ],
        cliente_falso({"USD": JSON_USD}),
    )
    assert codigo == 0
    assert "CNY" not in saida.read_text(encoding="utf-8")
    assert "não publica PTAX de fechamento para CNY" in capsys.readouterr().err


def test_avisa_quando_faltam_datas_ate_o_fim(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ptax.main(
        [
            "--inicio",
            "2026-11-06",
            "--fim",
            "2026-11-30",
            "--moedas",
            "USD",
            "--saida",
            str(tmp_path / "p.csv"),
        ],
        cliente_falso({"USD": JSON_USD}),
    )
    assert "só tem cotação até 2026-11-09" in capsys.readouterr().err


def test_sem_nenhuma_cotacao_nao_grava(tmp_path: Path) -> None:
    saida = tmp_path / "ptax.csv"
    assert ptax.main(["--moedas", "CNY", "--saida", str(saida)], cliente_falso({})) == 3
    assert not saida.exists()


def test_consulta_cada_moeda_uma_vez(tmp_path: Path) -> None:
    chamadas: list[str] = []
    ptax.main(
        ["--moedas", "USD", "EUR", "--saida", str(tmp_path / "p.csv")],
        cliente_falso({"USD": JSON_USD}, chamadas),
    )
    assert len(chamadas) == 2 and "@moeda='USD'" in chamadas[0] and "@moeda='EUR'" in chamadas[1]
