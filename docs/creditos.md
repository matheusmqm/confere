# Créditos e licenças de bibliotecas

Rascunho que será consolidado no README na CF-161. As versões são as instaladas no projeto
(`uv.lock`); as licenças foram lidas do metadado de cada pacote.

## Documentos fiscais sintéticos (CF-34 e CF-35)

| Biblioteca | Versão | Licença | Uso |
|---|---|---|---|
| [nfelib](https://github.com/akretion/nfelib) (Akretion, Raphaël Valyi) | 3.3.0 | MIT | Bindings do CT-e 4.00: monta, serializa (`to_xml`) e valida (XSD) o XML dos CT-e sintéticos. |
| [BrazilFiscalReport](https://github.com/Engenere/BrazilFiscalReport) (Engenere) | 1.4.0 | LGPL-3.0 | `Dacte`: gera o DACTE em PDF a partir do XML do CT-e. |
| [fpdf2](https://github.com/py-pdf/fpdf2) | 2.9.0 | LGPL-3.0 | Dependência do BrazilFiscalReport para desenhar o PDF. |

Os CT-e e DACTE são **fictícios, não assinados e sem valor fiscal** (ambiente de homologação,
`tpAmb=2`): servem apenas de dado de teste.

## Faturas em PDF e ruído de foto (CF-32, CF-33 e CF-37)

| Biblioteca | Versão | Licença | Uso |
|---|---|---|---|
| [WeasyPrint](https://weasyprint.org/) | 70.0 | BSD-3-Clause | HTML → PDF das faturas sintéticas. |
| [Jinja2](https://jinja.palletsprojects.com/) | 3.1.6 | BSD-3-Clause | Templates dos 6 estilos de fatura. |
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) (Artifex) | 2.1 | AGPL-3.0 ou licença comercial | Rasteriza os PDFs e remonta o PDF só de imagem do ruído. |
| [Pillow](https://python-pillow.org/) | 13.0.0 | MIT-CMU (HPND) | Rotação, perspectiva, desfoque, sombra e JPEG do ruído. |
| [NumPy](https://numpy.org/) | 2.5.4 | BSD-3-Clause (e outras permissivas) | Gradiente da sombra lateral. |

O PyMuPDF é AGPL-3.0: este repositório é público e de código aberto, e o uso é compatível com a
licença. Ao distribuir o projeto de outra forma, reveja essa condição.

## Ingestão, classificação e PTAX (CF-40, CF-43 a CF-46)

| Biblioteca ou fonte | Versão | Licença | Uso |
|---|---|---|---|
| [defusedxml](https://github.com/tiran/defusedxml) | 0.7.1 | PSF-2.0 | Parser de XML seguro (barra XXE e billion laughs) no classificador de XML. |
| [google-genai](https://github.com/googleapis/python-genai) | 3.0.0 | Apache-2.0 | SDK do Gemini: classificação estruturada e embeddings. |
| [httpx](https://www.python-httpx.org/) | 0.28.1 | BSD-3-Clause | Download da PTAX e testes com transporte falso. |
| [PTAX / Banco Central do Brasil (Olinda)](https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/aplicacao#!/recursos) | n/a | Dados abertos | Cotações de fechamento de USD e EUR em `data/seed42/ptax.csv`. O BCB não publica PTAX de CNY. |
