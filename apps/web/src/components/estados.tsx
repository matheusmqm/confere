import { cn } from "cn";
import { CircleAlert, Inbox, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

/** Estados vazio e de erro compartilhados pelas telas (CF-133). */
export function EstadoVazio({
  titulo,
  descricao,
  icone: Icone = Inbox,
  className,
  children,
}: {
  titulo: string;
  descricao?: string;
  icone?: LucideIcon;
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-2 rounded-lg border border-dashed border-border px-6 py-10 text-center",
        className,
      )}
    >
      <Icone aria-hidden className="size-5 text-tinta-300" />
      <p className="text-[15px] font-semibold text-tinta-700">{titulo}</p>
      {descricao ? (
        <p className="max-w-sm text-sm text-tinta-500">{descricao}</p>
      ) : null}
      {children}
    </div>
  );
}

export function EstadoErro({
  mensagem = "Não foi possível carregar os dados.",
  aoTentarDeNovo,
  className,
}: {
  mensagem?: string;
  aoTentarDeNovo?: () => void;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center gap-2 rounded-lg border border-ambar/50 bg-ambar-fundo px-6 py-8 text-center",
        className,
      )}
    >
      <CircleAlert aria-hidden className="size-5 text-ambar-texto" />
      <p className="text-sm font-medium text-ambar-texto">{mensagem}</p>
      {aoTentarDeNovo ? (
        <Button variant="outline" size="sm" onClick={aoTentarDeNovo}>
          Tentar de novo
        </Button>
      ) : null}
    </div>
  );
}
