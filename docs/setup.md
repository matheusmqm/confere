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
