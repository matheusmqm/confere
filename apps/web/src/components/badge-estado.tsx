import { cn } from "cn";
import {
  Archive,
  Check,
  CheckCheck,
  FileWarning,
  Inbox,
  Loader,
  Lock,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";

export const ESTADOS_DOCUMENTO = [
  "recebido",
  "processando",
  "aprovado_auto",
  "aprovado_manual",
  "em_revisao",
  "bloqueado",
  "erro_arquivo",
  "arquivado",
] as const;

export type EstadoDocumento = (typeof ESTADOS_DOCUMENTO)[number];

interface Config {
  rotulo: string;
  icone: LucideIcon;
  /** Fundo, texto e borda do trio da identidade (traço, texto e fundo). */
  classes: string;
  girar?: boolean;
}

/**
 * Cor por significado: verde = aprovado, âmbar = revisão, vermelho = bloqueio, cobalto =
 * processando, cinza = recebido/arquivado. `roxo-ia` fica reservado a selos de IA.
 * Todo estado leva ícone + rótulo (nunca só cor).
 */
export const CONFIG_ESTADO: Record<EstadoDocumento, Config> = {
  recebido: {
    rotulo: "Recebido",
    icone: Inbox,
    classes: "bg-tinta-100 text-tinta-700 border-tinta-300",
  },
  processando: {
    rotulo: "Processando",
    icone: Loader,
    classes: "bg-cobalto-fundo text-cobalto-texto border-cobalto/40",
    girar: true,
  },
  aprovado_auto: {
    rotulo: "Aprovada sozinha",
    icone: Check,
    classes: "bg-verde-fundo text-verde-texto border-verde-conferido/40",
  },
  aprovado_manual: {
    rotulo: "Aprovada",
    icone: CheckCheck,
    classes: "bg-verde-fundo text-verde-texto border-verde-conferido/40",
  },
  em_revisao: {
    rotulo: "Em revisão",
    icone: TriangleAlert,
    classes: "bg-ambar-fundo text-ambar-texto border-ambar/50",
  },
  bloqueado: {
    rotulo: "Bloqueada",
    icone: Lock,
    classes: "bg-vermelho-fundo text-vermelho-texto border-vermelho/40",
  },
  erro_arquivo: {
    rotulo: "Erro no arquivo",
    icone: FileWarning,
    classes: "bg-ambar-fundo text-ambar-texto border-ambar/50",
  },
  arquivado: {
    rotulo: "Arquivado",
    icone: Archive,
    classes: "bg-tinta-100 text-tinta-500 border-tinta-300",
  },
};

export function rotuloEstado(estado: string): string {
  return estado in CONFIG_ESTADO
    ? CONFIG_ESTADO[estado as EstadoDocumento].rotulo
    : estado;
}

interface Props {
  estado: string;
  className?: string;
}

export function BadgeEstado({ estado, className }: Props) {
  const config =
    CONFIG_ESTADO[estado as EstadoDocumento] ?? CONFIG_ESTADO.recebido;
  const Icone = config.icone;
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1 rounded-sm border px-2 text-[13px] font-medium whitespace-nowrap",
        config.classes,
        className,
      )}
    >
      <Icone
        aria-hidden
        className={cn("size-3", config.girar && "animate-spin")}
      />
      {rotuloEstado(estado)}
    </span>
  );
}
