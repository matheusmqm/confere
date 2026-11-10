# ADR-001: Decisões de arquitetura

- **Status:** aceito
- **Data:** 2026-11-10

## Contexto

O Confere é um projeto do Hack Brasil 2026, feito por uma pessoa, com prazo curto e volume de demonstração (dezenas de processos, centenas de faturas). O sistema precisa ser confiável ao decidir sobre dinheiro, barato de operar e avaliável com métricas honestas. Cada peça de infraestrutura a mais é uma conta, uma chave e um ponto de falha para manter sozinho.

## Decisão

### 1. Fila de jobs em tabela Postgres (`SKIP LOCKED`)
O worker pega jobs de uma tabela com `SELECT ... FOR UPDATE SKIP LOCKED`, em vez de Redis/Celery. Há menos peças, o estado da fila fica no mesmo banco (e na mesma transação) do resto, e o volume de demo não exige mais.

### 2. LLM só onde precisa
O LLM classifica PDF, extrai dados de PDF, mapeia cobrança para código de custo e redige a explicação. XML, validações, casamento, regras e a decisão de aprovar são código determinístico. Toda saída de LLM é presa a um schema, e o texto de documento é tratado como dado, nunca como instrução.

### 3. Supabase como fornecedor único
Postgres, pgvector e Storage ficam no Supabase, no lugar de Neon + Cloudflare R2.

### 4. Monorepo com núcleo puro
`packages/core` contém o pipeline E1–E10 como funções puras sobre modelos Pydantic, sem banco nem HTTP. `apps/api` faz todo o I/O (persistência, fila, Storage, HTTP) e chama o core.

### 5. Dados 100% sintéticos com gabarito por linha
Processos, faturas, CNPJs e nomes são gerados (seed 42) e marcados como fictícios. Cada linha injetada com erro tem gabarito.

## Consequências

1. **Fila:** o worker precisa de conexão direta ou pooler em modo *session* (porta 5432); o pooler em modo *transaction* (6543) não serve a ele. A fila não escala como um broker dedicado, o que é aceitável aqui.
2. **LLM:** custo baixo e previsível, testes determinísticos na maior parte do pipeline e defesa estrutural contra prompt injection, já que o LLM nunca aprova nada. A qualidade da extração continua dependendo do modelo e precisa de avaliação própria.
3. **Supabase:** menos contas e chaves. Em contrapartida, o plano gratuito não tem branch de banco por PR; o projeto pausa após 7 dias sem uso, então há um job de keep-alive (CF-154); e valem os limites de 500 MB de banco e 1 GB de arquivos.
4. **Núcleo puro:** a avaliação offline (`eval/run.py`) roda exatamente o mesmo código da produção, sem mocks de banco. O custo é manter a fronteira: o core não pode importar `confere_api` nem SQLAlchemy.
5. **Dados sintéticos:** atende ao regulamento (nenhum dado pessoal real) e permite métricas confiáveis, medidas só no conjunto de teste, separado por processo. O risco é o mundo sintético ser mais fácil que o real; as métricas devem ser apresentadas como tal.

## Alternativas consideradas

1. **Redis + Celery/RQ, ou fila gerenciada:** mais robustos em escala, mas somam um serviço, uma conta e mais configuração, sem ganho para o volume de demo.
2. **LLM de ponta a ponta (inclusive casamento e decisão):** mais simples de escrever, porém caro, não determinístico, difícil de testar e vulnerável a prompt injection em documentos.
3. **Neon + Cloudflare R2:** bom custo e branch de banco, mas dois fornecedores, mais chaves e mais configuração para uma pessoa só.
4. **Pipeline dentro da API, acessando o banco direto:** mais rápido de começar, mas impede a avaliação offline com o mesmo código e mistura regra com I/O.
5. **Dados reais anonimizados:** mais realistas, mas proibidos pelo regulamento e sem gabarito confiável por linha.
