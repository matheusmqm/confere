"use client";

import { Check, Pencil, Repeat2, ShieldX } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { components } from "@/lib/api/schema";

type Acao = components["schemas"]["DecisaoEntrada"]["acao"];

/** Ação "Corrigir" depende do tipo: processo ou código de custo. */
export function acaoDeCorrecao(tipo: string): Acao {
  return tipo === "sem_processo" || tipo === "confirmar_processo"
    ? "corrigir_processo"
    : "corrigir_codigo";
}

interface Props {
  tipo: string;
  podeRepassar: boolean;
  desabilitado?: boolean;
  /** Mostra a tecla de atalho ao lado do rótulo. */
  atalhos?: boolean;
  onAcao: (acao: Acao) => void;
}

/** Botões de 1 clique da exceção (também usados na tela do documento). */
export function AcoesExcecao({
  tipo,
  podeRepassar,
  desabilitado,
  atalhos,
  onAcao,
}: Props) {
  const tecla = (t: string) =>
    atalhos ? (
      <kbd className="valor ml-1 rounded-sm border border-tinta-300 px-1 text-[11px]">
        {t}
      </kbd>
    ) : null;
  return (
    <div className="flex flex-wrap gap-2">
      <Button
        size="sm"
        disabled={desabilitado}
        onClick={() => onAcao("aprovar")}
      >
        <Check aria-hidden />
        Aprovar
        {tecla("A")}
      </Button>
      <Button
        size="sm"
        variant="outline"
        disabled={desabilitado}
        onClick={() => onAcao("contestar")}
      >
        <ShieldX aria-hidden />
        Contestar
        {tecla("C")}
      </Button>
      <Button
        size="sm"
        variant="outline"
        disabled={desabilitado}
        onClick={() => onAcao(acaoDeCorrecao(tipo))}
      >
        <Pencil aria-hidden />
        Corrigir
        {tecla("E")}
      </Button>
      <Button
        size="sm"
        variant="outline"
        disabled={desabilitado || !podeRepassar}
        onClick={() => onAcao("repassar")}
      >
        <Repeat2 aria-hidden />
        Repassar
        {tecla("R")}
      </Button>
    </div>
  );
}
