import { cn } from "cn";
import { Sparkles } from "lucide-react";

/** Selo "IA": reservado ao que a IA fez ou sugeriu (roxo-ia). */
export function SeloIA({
  className,
  rotulo = "IA",
}: {
  className?: string;
  rotulo?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1 rounded-sm border border-roxo-ia/40 bg-roxo-fundo px-1.5 text-xs font-medium text-roxo-texto",
        className,
      )}
    >
      <Sparkles aria-hidden className="size-3" />
      {rotulo}
    </span>
  );
}
