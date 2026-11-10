"use client";

import { cn } from "cn";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface Breakdown {
  extracao?: number | null;
  processo?: number | null;
  codigo?: number | null;
}

interface Props {
  valor: number | null | undefined;
  breakdown?: Breakdown;
  className?: string;
}

const pct = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Faixas de cor: abaixo de 0,6 vermelho, abaixo de 0,85 âmbar, senão verde. */
function faixa(valor: number) {
  if (valor < 0.6) return { barra: "bg-vermelho", rotulo: "baixa" };
  if (valor < 0.85) return { barra: "bg-ambar", rotulo: "média" };
  return { barra: "bg-verde-conferido", rotulo: "alta" };
}

function Linha({ nome, valor }: { nome: string; valor?: number | null }) {
  return (
    <div className="flex justify-between gap-4">
      <span>{nome}</span>
      <span className="valor">
        {valor === null || valor === undefined ? "—" : pct.format(valor)}
      </span>
    </div>
  );
}

/** Barra fina de 0 a 1 com a quebra extração/processo/código no tooltip (CF-122). */
export function MedidorConfianca({ valor, breakdown, className }: Props) {
  if (valor === null || valor === undefined) {
    return <span className="valor text-xs text-tinta-500">—</span>;
  }
  const limitado = Math.min(1, Math.max(0, valor));
  const { barra, rotulo } = faixa(limitado);
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <span
            role="meter"
            aria-label={`Confiança ${rotulo}`}
            aria-valuemin={0}
            aria-valuemax={1}
            aria-valuenow={limitado}
            aria-valuetext={`${pct.format(limitado)} (${rotulo})`}
            tabIndex={0}
            className={cn("inline-flex items-center gap-2", className)}
          />
        }
      >
        <span className="h-1.5 w-14 overflow-hidden rounded-full bg-tinta-100">
          <span
            className={cn("block h-full rounded-full", barra)}
            style={{ width: `${limitado * 100}%` }}
          />
        </span>
        <span className="valor text-xs text-tinta-700">
          {pct.format(limitado)}
        </span>
      </TooltipTrigger>
      <TooltipContent className="flex-col items-stretch gap-1">
        <Linha nome="Extração" valor={breakdown?.extracao} />
        <Linha nome="Processo" valor={breakdown?.processo} />
        <Linha nome="Código de custo" valor={breakdown?.codigo} />
      </TooltipContent>
    </Tooltip>
  );
}
