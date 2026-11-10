import { cn } from "cn";
import { formatarMoeda, sinalDe } from "@/lib/dinheiro";

interface Props {
  valor: string | null | undefined;
  moeda?: string;
  /** Diferença: mostra "+" e colore (positiva em vermelho, negativa em verde). */
  diferenca?: boolean;
  className?: string;
}

/** Valor em dinheiro: Plex Mono, algarismos tabulares, alinhado à direita (CF-122). */
export function CelulaDinheiro({
  valor,
  moeda = "BRL",
  diferenca = false,
  className,
}: Props) {
  if (valor === null || valor === undefined) {
    return (
      <span className={cn("valor block text-right text-tinta-500", className)}>
        —
      </span>
    );
  }
  const sinal = diferenca ? sinalDe(valor) : 0;
  return (
    <span
      className={cn(
        "valor block text-right text-sm whitespace-nowrap",
        sinal > 0 && "text-vermelho-texto",
        sinal < 0 && "text-verde-texto",
        className,
      )}
    >
      {formatarMoeda(valor, moeda, { sinal: diferenca })}
    </span>
  );
}
