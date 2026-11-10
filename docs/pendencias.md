# Pendências

Itens que dependem de insumo manual ou de módulo de outra tarefa.

## MVP 1 (CF-101 a CF-107)

- **CF-105 (`POST /documentos`) — bloqueada.** Faltam `inspecionar()` (CF-42, validação de arquivo: tipo, vazio, PDF corrompido ou protegido) e `caminho_storage(empresa_id, sha256, ext)`. As rotas `GET /documentos` e `GET /documentos/{id}` já existem (necessárias ao isolamento de tenant da CF-104).
- **CF-107 (orquestrador) — bloqueada.** O core ainda não tem: resolução de processo da E3 (`resolve`, só há `normalizar`), classificação de código por LLM e busca vetorial da E4 (`costcode`, só há dicionário e normalizador), cliente PTAX/câmbio da E5 (`fx`, só há `tabela`), `match` (E6), `decide` (E8) e `explain` (E10). Também faltam `FonteProcessosSQL`, o hook de `llm_call` (CF-54) e o resolvedor de fornecedor por alias. O handler `processar` do worker continua provisório (`worker/handlers.py`): marca o documento `em_revisao` e grava um evento.
- **CF-117 (login de demo) — feito.** `POST /auth/demo` procura o usuário `demo@confere.example` (constante em `controllers/auth.py`): sem o seed da demo ele responde 503 `demo_indisponivel`. O front chama a API por `/api/*` (rewrite em `apps/web/next.config.ts`, variável `API_URL` ou `NEXT_PUBLIC_API_URL`), então o cookie é `SameSite=Lax`. Em `ENV=demo` defina `SESSION_SECRET` (obrigatório). Em `local` e `test` vale também o header `X-Empresa-Id`.
- **CF-114 (demo) — parcial.** `POST /demo/reset` está pronto (só com `DEMO_MODE=true`; precisa de sessão, então `make demo-reset` com `curl` puro dá 401). Faltam: `POST /demo/lote` (hoje responde 501; depende do upload da CF-105) e o comando `lote-demo` do synth que gera `data/seed42/demo_lote.json` (depende do `gerar` da CF-39 e do gabarito da CF-38). O cache do LLM do lote (`data/llm_cache/`) só dá para popular depois disso, com `GEMINI_API_KEY`.
- **CF-110/111 — dependências do worker.** Editar uma provisão já casada enfileira um job `reprocessar`, mas o worker ainda não tem esse handler (vem com a CF-107). As ações `corrigir_codigo` e `corrigir_processo` respondem 501 até a CF-93 e a CF-94. Convenção usada para "repassar": a decisão grava `dados_json.linha_id`; o saldo da CF-110 lê isso.
- **CF-110 — câmbio da provisão.** O previsto em BRL converte pela PTAX de venda mais recente de `ptax_cache` (a tabela ainda não é preenchida pelo código); sem cotação o total sai com `cotacao_incompleta=true`.
- **CF-109 — arquivo local.** `GET /documentos/{id}/arquivo` com `STORAGE_BACKEND=local` devolve uma URL relativa (`/arquivos-locais/...`); o front deve prefixá-la com `/api`.
- **CF-112 — referência do painel.** Não há `eval/metricas.py` ainda para o teste de comparação do painel.
- **LISTEN/NOTIFY.** Opcional na CF-106, não implementado: o worker consulta a fila a cada 0,5 s (`config/worker.yaml`).
- **Testes.** Por decisão do MVP, nenhum teste foi escrito nem executado para a CF-101 a CF-106 (inclui o teste de isolamento e o "lint" de `session.get` da CF-104). O `apps/api/tests/test_migrations.py` ainda espera a versão `0001` e vai precisar de `0004`.
- **Catálogo de custos.** A tabela `codigo_custo` existe, mas ainda não é carregada de `config/codigos_custo.yaml` (carga inicial entra com o seed).

## Front-end (CF-119 a CF-130)

- **Tokens (CF-119).** Cores, fontes e raios vêm do sistema de design "Confere" (`tokens.json`). A identidade é só no tema claro: os valores de `.dark` em `globals.css` foram DERIVADOS e precisam de revisão do Design (CF-135). Em vez de `tailwind.config.ts`, o Tailwind v4 usa `@theme` no próprio `globals.css`. As cores estão em hex (exatas da identidade), não em HSL. Raios: `sm` 6 px e `lg` 10 px (identidade), `md` 8 px. `sombra-cartao` é quase nula de propósito (a identidade usa só borda); `sombra-popover` é a `sombra-flutuante`.
- **Logo (CF-120).** O logo é um SVG placeholder (`components/app/logo.tsx`) até a CF-164.
- **Contrato da API (CF-123).** `apps/api/openapi.json` é gerado com `DEMO_MODE=true` (inclui `/demo/*`). Rode `make gen-api` sempre que mudar rota ou schema; o CI falha se o diff não estiver commitado. `POST /documentos` ainda não está no OpenAPI (CF-105): a zona de upload usa `fetch` manual.
- **Rotas que o front espera e não existem.** `GET /avaliacao` (curva risco × cobertura e baselines B0–B3; formato em `lib/avaliacao.ts`) e `PUT /politica` (botão "Aplicar" do painel). Sem elas o painel mostra "Curva indisponível" e o botão avisa em toast.
- **Telas ainda vazias.** `/processos` e `/politica` são só títulos com estado vazio (as rotas `GET /processos` existem; falta a tela). Contestar não abre o rascunho de e-mail (CF-99 não existe). O "desfazer" da ação otimista da fila de exceções foi trocado por reverter em caso de erro.
- **Testes.** Nenhum teste de front foi escrito ou executado (Vitest da CF-121/122, Playwright da CF-124). Removi `src/app/page.test.tsx` junto com a home antiga, que a Inbox substituiu.
- **Verificado.** Só `pnpm lint` e `pnpm typecheck` (verdes). Nada foi aberto no navegador: o visual, o SSE ao vivo e o visualizador de PDF não foram vistos rodando.
