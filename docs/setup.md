# Setup do ambiente

## Python e dependências
```
uv sync --all-packages
```

## WeasyPrint (geração de faturas em PDF)
O WeasyPrint precisa de bibliotecas do sistema (Pango). Sem elas, `import weasyprint` falha;
os testes triviais do workspace não o importam.

- Ubuntu/Debian:
  ```
  sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0
  ```
- macOS (Homebrew):
  ```
  brew install pango
  ```
- Windows: instale o GTK3 runtime (ver a documentação do WeasyPrint).

## python-magic
Precisa da libmagic. Ubuntu/Debian: `sudo apt install libmagic1`. macOS: `brew install libmagic`.
No Windows o pacote `python-magic-bin` (já declarado em `confere-api`) traz a libmagic.

## Banco de dados e migrações (Alembic)

O `alembic.ini` fica em `apps/api/`. As migrações usam `DATABASE_URL_WORKER`
(conexão direta ou pooler em modo session, porta 5432), nunca o pooler transaction (6543).

### Local (docker compose)
```
docker compose up -d --wait
cd apps/api
DATABASE_URL_WORKER=postgresql+psycopg://confere:confere@localhost:5432/confere uv run alembic upgrade head
```
Os testes marcados `db` usam o banco `confere_test` (`TEST_DATABASE_URL` sobrescreve a URL).

### Supabase
O `.env` da raiz aponta para o Supabase, então **o `alembic` sem override migra o Supabase**.

1. No `.env`, preencha a senha do banco em `DATABASE_URL_WORKER`. Use a conexão direta
   (`db.<ref>.supabase.co:5432`) ou o pooler em modo session
   (`aws-1-<regiao>.pooler.supabase.com:5432`, usuário `postgres.<ref>`).
2. Rode:
   ```
   cd apps/api
   uv run alembic current        # confere o alvo antes
   uv run alembic upgrade head
   ```
3. As extensões `vector`, `pg_trgm` e `unaccent` são criadas pela migração `0001`
   (`CREATE EXTENSION IF NOT EXISTS`). No Supabase elas podem já existir.
4. `DATABASE_URL` (API) usa o pooler transaction na porta 6543; o `make_engine` troca para
   `NullPool` e `prepare_threshold=None` nesse caso.

## Variáveis de ambiente

- Copie `.env.example` para `.env` e preencha. O `.env` está no `.gitignore`; nunca versione valores reais.
- `apps/web/.env.example` tem só `NEXT_PUBLIC_API_URL`. O frontend não usa nenhuma chave do Supabase.
- Com `ENV=demo`, a API recusa subir se faltar `SUPABASE_SERVICE_ROLE_KEY`, `S3_*` ou `GEMINI_API_KEY`
  (a mensagem de erro lista o que falta).

## Segredos do GitHub Actions

Crie com `gh secret set NOME` (o valor é pedido no terminal ou lido do stdin):

| Segredo | Para quê |
|---|---|
| `GEMINI_API_KEY` | Chamadas reais ao Gemini (testes `llm`, demo) |
| `SUPABASE_URL` | URL do projeto Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | Chave service role (só backend) |
| `S3_ENDPOINT_URL` | Endpoint S3 do Storage |
| `S3_REGION` | Região do projeto |
| `S3_ACCESS_KEY_ID` | Chave de acesso S3 |
| `S3_SECRET_ACCESS_KEY` | Segredo da chave S3 |
| `DATABASE_URL` | Banco da API (pooler transaction, 6543) |
| `DATABASE_URL_WORKER` | Banco do worker e migrações (5432) |
| `FLY_API_TOKEN` | Deploy no Fly.io |

Exemplo: `gh secret set GEMINI_API_KEY` e cole o valor. O CI de PR não precisa de nenhum deles
(usa Postgres de serviço, `LLM_OFFLINE=true` e `PTAX_OFFLINE=true`).

## Hooks de pre-commit

Configurados em `.pre-commit-config.yaml`: `ruff` (check --fix) e `ruff-format`, `gitleaks`,
`check-added-large-files` (2 MB; exceto `data/seed42/` e `data/llm_cache/`), `end-of-file-fixer`,
`trailing-whitespace` e `prettier --check` só em `apps/web/` (precisa do `pnpm` e do frontend, CF-4).

```
uv run pre-commit install            # uma vez por clone
uv run pre-commit run --all-files    # roda tudo (só arquivos rastreados pelo git)
```

O `gitleaks` examina o que está **em staging** (`git add`) e barra o commit com `leaks found: 1`
(código de saída 1). Se for falso positivo, ajuste com um `.gitleaksignore`; nunca com `--no-verify`.
O mesmo scanner roda no CI (`gitleaks-action`).

Para testar o detector sem commitar, aponte o binário em cache para um arquivo qualquer:
`gitleaks dir <pasta> --no-banner`. A regra de chave do Google só dispara com o formato real,
`AIza` + 35 caracteres.

## Frontend (pnpm)

O `apps/web` usa pnpm (versão fixada em `packageManager`). Se o `pnpm` não existir:
`corepack enable` (no Windows sem administrador: `corepack enable --install-directory <pasta no PATH>`).

```
pnpm -C apps/web install
pnpm -C apps/web dev          # http://localhost:3000
pnpm -C apps/web typecheck    # gera os tipos de rota do Next e roda tsc
```

## Pré-visualização das faturas sintéticas (PDF)

```
uv run python -m confere_synth.render_preview      # grava data/preview/estilo_1.pdf ... estilo_6.pdf
```

A pasta `data/preview/` está no `.gitignore`. Sem as bibliotecas do WeasyPrint o comando grava só
os `.html` ao lado e sai com código 1.

**Windows (MSYS2):** instale o Pango no ambiente UCRT64 e aponte o WeasyPrint para as DLLs:

```
pacman -S mingw-w64-ucrt-x86_64-pango
set WEASYPRINT_DLL_DIRECTORIES=C:\msys64\ucrt64\bin     (PowerShell: $env:WEASYPRINT_DLL_DIRECTORIES = 'C:\msys64\ucrt64\bin')
```

Ubuntu/Debian e macOS: veja a seção do WeasyPrint acima.

## Gerar as faturas sintéticas (CF-33)

```
uv run python -m confere_synth.cli faturas --seed 42 --saida data/seed42
```

Gera o mundo (determinístico no seed), as faturas e extratos limpos e os PDFs em
`data/seed42/documentos/`, e grava `mundo.json`, `documentos.json` e `manifest.json` (com o
SHA-256 de cada PDF; chaves de outras etapas já presentes no manifest são preservadas).
Precisa das bibliotecas do WeasyPrint (veja a seção de pré-visualização); sem elas o comando
termina com código 1 e não grava nada.

## CT-e, DACTE e ruído de foto (CF-34, CF-35, CF-37)

```
uv run python -m confere_synth.cli ctes  --seed 42 --saida data/seed42   # XML do CT-e + DACTE (PDF)
uv run python -m confere_synth.cli ruido --seed 42 --saida data/seed42   # depois de `faturas`
```

- `ctes` não precisa do Pango (o DACTE usa fpdf2). O XML é **não assinado** e só para testes.
  Os DACTE ficam em `documentos/<id>_dacte.pdf` e entram no manifest com `tipo: "dacte"`,
  `origem_xml` e `incluir_no_lote: false`.
- `ruido` precisa dos PDFs de `faturas`. Reverte o ruído anterior antes de sortear (idempotente),
  mantém o PDF limpo ao lado e marca no manifest `ruido`, `arquivo_original` e, para o JPG,
  `foto_torta: true`.
- Os três comandos preservam no `manifest.json` as chaves que os outros já gravaram.

## PTAX congelada (CF-40)

```
uv run python infra/scripts/baixar_ptax.py        # grava data/seed42/ptax.csv
```

Baixa do BCB (Olinda) só o boletim de **Fechamento** de USD, EUR e CNY, de 2026-07-15 a 2026-11-30.
O script **não inventa** nada: datas ainda não publicadas ficam de fora (rode de novo depois de
30/11 para completar) e o CNY não é publicado pela PTAX, então não tem linhas. Fim de semana e
feriado também não entram (a regra do último dia útil é da CF-71). Leitura no core:
`confere_core.fx.tabela.TabelaPTAX.carregar(path).get(moeda, data)`.

## Classificação com LLM (CF-45)

O `GeminiClient` (`confere_core.llm.client`) usa o SDK `google-genai`; os testes usam o
`FakeLLMClient` e **não chamam a API**. Preços por milhão de tokens ficam em
`config/llm_precos.yaml` (valores de referência: conferir o preço vigente).

## Erros injetados (CF-36)

`config/erros.yaml` define a taxa de cada erro; `confere_synth.erros.injetar(rng, documentos,
mundo, cfg, ptax=...)` aplica, em ordem: valor acima → taxa não prevista → câmbio errado →
referência cruzada → duplicada. A quantidade é cota (`round(taxa x elegíveis)`, mínimo 1).

- **Câmbio errado** precisa de fatura em BRL de valor previsto em USD/EUR. O mundo ganhou um
  fornecedor nacional para isso, o NVOCC **Consolidadora Marítima Aurora Ltda.**: ele fatura em
  BRL pela PTAX de venda da emissão e mostra "USD 1.800,00 × taxa 5,6120 = R$ ..." mais a linha
  informativa "Taxa de câmbio aplicada". Sem cotação para a data, a emissão dessas faturas é
  limitada à última cotação de `data/seed42/ptax.csv`.
- `valor_erro_brl` usa a PTAX de venda da emissão (olha até 5 dias para trás) e fica nulo sem
  cotação (CNY, datas fora da tabela). Nada é inventado.
- Duplicadas: metade é cópia byte a byte do PDF original (o `renderizar` copia o arquivo; o
  original precisa estar renderizado antes) e metade é re-renderizada com emissão +1 dia.
- O `injetar` é puro; ligar a re-renderização dos documentos alterados e das cópias ao comando
  `gerar` é da CF-39.
