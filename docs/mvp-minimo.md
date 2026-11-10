# MVP mínimo (tudo no Supabase)

Fonte dos prompts: `docs/Confere_prompts_CF-1_a_CF-185(2).md`. Meta: subir front e back, enviar um
documento e ver o pipeline andar até uma decisão, **sem Docker**, banco e arquivos no Supabase.
O que não está aqui fica para depois. Legenda: [x] feito · [~] feito em versão reduzida · [ ] falta.

## Infra (Supabase)
- [x] CF-6/7/10/11 — projeto, Alembic, `.env`, bucket. Migrações 0001–0005 aplicadas no banco do Supabase.
- [x] `make dev` sem Docker (`migrate` + API + worker + web).
- [ ] `GEMINI_API_KEY` no `.env` — só para PDF e imagem. **Para CT-e em XML não precisa.**

## Caminho mínimo

| # | Prompt | Versão reduzida | Estado |
|---|---|---|---|
| 1 | CF-101 a 104, 106 | núcleo, documentos, infra, tenant, worker | [x] |
| 2 | CF-108 a 112, 117 | SSE, rotas, login de demo | [x] |
| 3 | CF-119 a 124, 126, 127, 130 | telas | [x] |
| 4 | CF-41 | seed do mundo sintético (`make seed`), sem `gerar`, sem PTAX, sem treino | [x] rodou no Supabase: 15 fornecedores, 50 processos, 633 provisões |
| 5 | CF-42 | `ingest/arquivo.py` (magic bytes, sha256, inspeção) | [x] |
| 6 | CF-105 | `POST /documentos` | [x] |
| 7 | CF-107 | orquestrador mínimo (abaixo) | [x] verificado com 5 CT-e (4 aprovados, 1 duplicata bloqueada) |

### O que o orquestrador mínimo usa de cada prompt
- E1/E2: CF-43 (classificar XML), CF-49 (extrator CT-e), CF-51 (validações), CF-45/50/52 para PDF (precisa de chave Gemini). Já prontos.
- E3: só a busca **exata** por referência (parte do CF-58). Sem fuzzy, sem Fellegi-Sunter.
- E4: só o **dicionário** de sinônimos (CF-64/65). Sem embeddings nem LLM: o que não achar vira `codigo_incerto`.
- E5: só BRL. Moeda estrangeira vira `moeda_sem_cotacao`.
- E6: casamento **guloso** por código (ideia do CF-77). Sem húngaro.
- E7: regras `duplicidade` e `tolerancia` (CF-81/82, prontas) + `sem_provisao`.
- E8: regra fixa do MVP (sem exceção → aprovada sozinha; revisar → em revisão; bloquear → bloqueada).
- E10: explicação por **template** (fallback do CF-98), sem LLM.

## Fica para depois (não é necessário agora)
CF-38/39 (gabarito, `gerar`), 44–47, 52–56, 58–63 completos, 66–69 (embeddings), 70–73 (PTAX), 74–76 (húngaro, CP-SAT),
83–84, 87–92 (score e τ), 93–96 (aprendizado), 97–100 (LLM de explicação), 113, 115, 116, 118,
128–129, 131–135, 136–185 (avaliação, qualidade, deploy, docs, pitch).

## Como testar (depois que tudo acima estiver [x])
1. `make seed` (carrega o mundo sintético no Supabase).
2. `uv run python infra/scripts/gerar_ctes_demo.py` (cria 21 CT-e XML em `data/demo_xml/documentos/`).
3. `make dev` e abrir `http://localhost:3000` → "Entrar na demo".
4. Arrastar os XML na Inbox. Esperado: a maioria aprovada sozinha; enviar o mesmo arquivo de novo
   (ou com outro nome) gera uma duplicata bloqueada, com "R$ evitado" no topo.

## O que já foi verificado
Login, upload de 5 CT-e XML, processamento no worker (cada documento leva uns 6 s por causa da
latência do Supabase), leitura pelas rotas e painel, tudo contra o banco do Supabase. O front
responde (home, `/api/*` pelo rewrite, login pelo proxy). **Não foi aberto no navegador**: o
visual e o SSE ao vivo ainda não foram vistos.

## Limites conhecidos (esperados nesta versão)
- PDF e imagem: precisam de `GEMINI_API_KEY`. Moeda estrangeira vira `moeda_sem_cotacao`.
- Só referência exata liga documento a processo; código de custo só pelo dicionário.
- Explicações em texto fixo (template), sem score nem τ.
- `make lint` ainda tem erros antigos: `domain.py`, `cte.py` e outros (E501, N818, RUF00x) e dois
  de `mypy` (`schema_gemini.py`, `test_erros.py`).
