"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { PackageOpen, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { api, desembrulhar } from "@/lib/api/client";

/** Os controles da demo só aparecem com `NEXT_PUBLIC_DEMO_MODE=true`. */
export const MODO_DEMO = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

function mensagemDe(erro: unknown): string {
  return erro instanceof Error
    ? erro.message
    : "Não foi possível concluir a operação.";
}

export function BotaoSoltarLote({ className }: { className?: string }) {
  const lote = useMutation({
    mutationFn: async () => desembrulhar(await api.POST("/demo/lote")),
    onSuccess: () =>
      toast.success("Lote da demo enviado. Os documentos vão chegando."),
    onError: (erro) => toast.error(mensagemDe(erro)),
  });
  if (!MODO_DEMO) return null;
  return (
    <Button
      className={className}
      onClick={() => lote.mutate()}
      disabled={lote.isPending}
    >
      <PackageOpen aria-hidden />
      Soltar lote da demo
    </Button>
  );
}

export function BotaoResetarDemo({ className }: { className?: string }) {
  const queryClient = useQueryClient();
  const reset = useMutation({
    mutationFn: async () =>
      desembrulhar(await api.POST("/demo/reset", { params: { query: {} } })),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: ["progresso"] });
      void queryClient.invalidateQueries();
      toast.success("Demo resetada.");
    },
    onError: (erro) => toast.error(mensagemDe(erro)),
  });
  if (!MODO_DEMO) return null;
  return (
    <Button
      variant="outline"
      className={className}
      disabled={reset.isPending}
      onClick={() => {
        if (
          window.confirm("Apagar os documentos, exceções e decisões da demo?")
        ) {
          reset.mutate();
        }
      }}
    >
      <RotateCcw aria-hidden />
      Resetar demo
    </Button>
  );
}
