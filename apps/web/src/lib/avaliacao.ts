"use client";

import { useQuery } from "@tanstack/react-query";
import type { PontoCurva } from "@/components/painel/graficos";

/**
 * Resposta esperada de `GET /avaliacao` (opcional: a rota ainda não existe na API).
 * Sai de `eval/relatorio.json` (`make eval`) e traz só o conjunto de teste.
 */
export interface Avaliacao {
  curva: PontoCurva[];
  alpha_atual: number;
  baselines: {
    id: string; // B0, B1, B2, B3, confere
    nome: string;
    sem_toque: number; // 0 a 1
    rs_evitado: string; // decimal em string
    erro_aprovado?: number | null; // fração de aprovações erradas
  }[];
}

/** `null` quando a rota não existe (404): a tela mostra o estado "indisponível". */
export function useAvaliacao() {
  return useQuery<Avaliacao | null>({
    queryKey: ["avaliacao"],
    staleTime: 60_000,
    queryFn: async () => {
      const resposta = await fetch("/api/avaliacao", {
        credentials: "include",
      });
      if (resposta.status === 404) return null;
      if (!resposta.ok)
        throw new Error("Não foi possível carregar a avaliação.");
      return (await resposta.json()) as Avaliacao;
    },
  });
}

/** Interpola linearmente cobertura e risco pelo alfa sobre os pontos da curva. */
export function interpolarPorAlpha(
  curva: PontoCurva[],
  alpha: number,
): { cobertura: number; risco: number } {
  const pontos = [...curva].sort((a, b) => a.alpha - b.alpha);
  if (pontos.length === 0) return { cobertura: 0, risco: 0 };
  if (alpha <= pontos[0].alpha) return pontos[0];
  const ultimo = pontos[pontos.length - 1];
  if (alpha >= ultimo.alpha) return ultimo;
  const i = pontos.findIndex((p) => p.alpha >= alpha);
  const a = pontos[i - 1];
  const b = pontos[i];
  const t = (alpha - a.alpha) / (b.alpha - a.alpha);
  return {
    cobertura: a.cobertura + t * (b.cobertura - a.cobertura),
    risco: a.risco + t * (b.risco - a.risco),
  };
}
