/**
 * Formatação de dinheiro sem passar por `float` (CF-122).
 *
 * A API manda valores como string decimal (`"1495.20"`). Aqui a string é separada em
 * sinal/inteiro/decimais manualmente: nenhum arredondamento acontece, e dígitos além do segundo
 * decimal são preservados. Só os milhares usam `Intl.NumberFormat('pt-BR')`, sobre um BigInt.
 */

export const SINAL_MENOS = "−"; // "−", não o hífen

const SIMBOLOS: Record<string, string> = {
  BRL: "R$",
  USD: "US$",
  EUR: "€",
  CNY: "CN¥",
  GBP: "£",
};

const agrupador = new Intl.NumberFormat("pt-BR", { useGrouping: true });

interface Partes {
  negativo: boolean;
  zero: boolean;
  inteiro: string;
  decimais: string;
}

function partir(valor: string): Partes {
  const m = /^([+-])?(\d+)(?:\.(\d+))?$/.exec(valor.trim());
  if (!m) throw new Error(`Valor decimal inválido: ${JSON.stringify(valor)}`);
  const inteiro = m[2].replace(/^0+(?=\d)/, "");
  const decimais = (m[3] ?? "").padEnd(2, "0");
  const zero = /^0+$/.test(inteiro) && /^0*$/.test(decimais);
  return { negativo: m[1] === "-" && !zero, zero, inteiro, decimais };
}

export interface OpcoesFormato {
  /** Mostra "+" nos positivos (diferenças). Negativos sempre levam "−". */
  sinal?: boolean;
}

/** `"12345.67"` → `"12.345,67"` (sem símbolo nem sinal). */
export function formatarNumero(valor: string): string {
  const { inteiro, decimais } = partir(valor);
  return `${agrupador.format(BigInt(inteiro))},${decimais}`;
}

/** Sinal do valor: -1, 0 ou 1. */
export function sinalDe(valor: string): -1 | 0 | 1 {
  const { negativo, zero } = partir(valor);
  return zero ? 0 : negativo ? -1 : 1;
}

/** Valor numérico só para animação e gráficos; nunca para exibir dinheiro. */
export function paraNumero(valor: string): number {
  return Number(valor);
}

/** `"12345.67"` → `"R$ 12.345,67"`; `"-40"` → `"− R$ 40,00"`. */
export function formatarBRL(valor: string, opcoes?: OpcoesFormato): string {
  return formatarMoeda(valor, "BRL", opcoes);
}

/** Valor em qualquer moeda: `("380", "USD")` → `"US$ 380,00"`. */
export function formatarMoeda(
  valor: string,
  moeda: string = "BRL",
  opcoes: OpcoesFormato = {},
): string {
  const { negativo, zero } = partir(valor);
  const simbolo = SIMBOLOS[moeda] ?? moeda;
  const prefixo = negativo
    ? `${SINAL_MENOS} `
    : opcoes.sinal && !zero
      ? "+ "
      : "";
  return `${prefixo}${simbolo} ${formatarNumero(valor)}`;
}
