/** Rótulos em pt-BR dos enums da API. */

export const ROTULO_TIPO_EXCECAO: Record<string, string> = {
  acima_tolerancia: "Acima da tolerância",
  sem_provisao: "Sem provisão",
  duplicada: "Duplicada",
  cambio_divergente: "Câmbio divergente",
  provisao_sem_fatura: "Provisão sem fatura",
  sem_processo: "Sem processo",
  confirmar_processo: "Confirmar processo",
  codigo_incerto: "Código incerto",
  extracao_inconsistente: "Extração inconsistente",
  documento_protegido: "Documento protegido",
  moeda_sem_cotacao: "Moeda sem cotação",
  possivel_duplicata_exata: "Possível duplicata exata",
};

export const ROTULO_ESTADO_LINHA: Record<string, string> = {
  ok: "Conferida",
  acima_tolerancia: "Acima da tolerância",
  abaixo_previsto: "Abaixo do previsto",
  sem_provisao: "Sem provisão",
  duplicada: "Duplicada",
  cambio_divergente: "Câmbio divergente",
  pendente: "Pendente",
};

export const ROTULO_SEVERIDADE: Record<string, string> = {
  info: "Informativo",
  revisar: "Revisar",
  bloquear: "Bloquear",
};

export function rotuloTipoExcecao(tipo: string): string {
  return ROTULO_TIPO_EXCECAO[tipo] ?? tipo;
}

/** Método de código que não é dicionário/regra é decisão de LLM e leva o selo "IA". */
export function metodoUsaIA(metodo: string | null | undefined): boolean {
  return !!metodo && /llm|ia|embedding|vetor/i.test(metodo);
}
