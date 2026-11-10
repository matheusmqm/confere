# Avaliação

> Este documento reúne as definições das métricas. As tabelas de contagem por conjunto do dataset
> (processos, documentos, linhas, erros por tipo) são geradas pelo comando `gerar` (CF-39).

## Vazamento financeiro e "R$ evitado" (CF-85)

**Vazamento** é o dinheiro que sairia se uma cobrança indevida fosse paga. Por linha, a partir do
estado final da linha (a regra de maior severidade vence; empate pela ordem da regra):

| Estado da linha | Vazamento (em BRL) |
|---|---|
| `acima_tolerancia` | o excedente: `max(0, cobrado − previsto)`. É o excedente inteiro, não só o que passa da tolerância |
| `duplicada` | o valor da linha |
| `sem_provisao` | o valor da linha, **somente se** a decisão humana (ou o gabarito, no eval) disser que a cobrança não é legítima |
| `cambio_divergente` | a diferença de câmbio |
| `ok`, `abaixo_previsto`, demais | 0 |

O total do lote é separado em quatro partes (`VazamentoLote`):

- **Detectado**: soma do vazamento de todas as linhas.
- **Evitado** (o "R$ evitado" do painel): o que foi bloqueado automaticamente (severidade
  `bloquear`) + o que um humano contestou ou bloqueou. **Na demo** (o jurado não decide todas as
  exceções), conta também o em risco das exceções de severidade `revisar`
  (`modo_demo=True`).
- **Em risco**: detectado que ainda não tem decisão humana e não entrou em "evitado".
- **Vazado**: detectado que um humano decidiu aprovar.

No eval, `sem_provisao` usa o gabarito de legitimidade e as decisões humanas são simuladas pelo
gabarito; o relatório informa se foi rodado com `modo_demo` ou não.
