import { cn } from "cn";

/** Os 6 passos da Inbox: lido → extraído → processo → códigos → casado → decidido (CF-125). */
export const PASSOS = [
  { etapa: "lido", rotulo: "Lido" },
  { etapa: "extraido", rotulo: "Extraído" },
  { etapa: "processo", rotulo: "Processo" },
  { etapa: "codigos", rotulo: "Códigos" },
  { etapa: "casado", rotulo: "Casado" },
  { etapa: "decidido", rotulo: "Decidido" },
] as const;

const FINAIS = new Set([
  "aprovado_auto",
  "aprovado_manual",
  "em_revisao",
  "bloqueado",
  "arquivado",
]);

interface Props {
  etapas?: Record<string, string>;
  /** Status do documento: um status final marca todos os passos como concluídos. */
  status: string;
}

export function ProgressoPipeline({ etapas, status }: Props) {
  const finalizado = FINAIS.has(status);
  const erro = status === "erro_arquivo" || etapas?.erro !== undefined;
  const concluidos = finalizado
    ? PASSOS.length
    : PASSOS.filter((p) => etapas?.[p.etapa] !== undefined).length;
  return (
    <div
      role="progressbar"
      aria-label="Progresso do processamento"
      aria-valuemin={0}
      aria-valuemax={PASSOS.length}
      aria-valuenow={concluidos}
      aria-valuetext={`${concluidos} de ${PASSOS.length} passos`}
      className="flex gap-1"
    >
      {PASSOS.map((passo, i) => {
        const feito = i < concluidos;
        const atual = !finalizado && i === concluidos && !erro;
        return (
          <span
            key={passo.etapa}
            title={passo.rotulo}
            className={cn(
              "h-1.5 flex-1 rounded-full",
              feito && !erro && "bg-verde-conferido",
              feito && erro && "bg-ambar",
              atual && "animate-pulse bg-cobalto",
              !feito && !atual && "bg-tinta-100",
            )}
          />
        );
      })}
    </div>
  );
}
