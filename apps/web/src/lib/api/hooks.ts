"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";
import { api, desembrulhar } from "./client";
import type { components, paths } from "./schema";

export type DocumentosQuery = NonNullable<
  paths["/documentos"]["get"]["parameters"]["query"]
>;
export type ExcecoesQuery = NonNullable<
  paths["/excecoes"]["get"]["parameters"]["query"]
>;
export type ProcessosQuery = NonNullable<
  paths["/processos"]["get"]["parameters"]["query"]
>;
export type PainelQuery = NonNullable<
  paths["/painel"]["get"]["parameters"]["query"]
>;
export type DecisaoEntrada = components["schemas"]["DecisaoEntrada"];

type Opcoes<T> = Omit<UseQueryOptions<T>, "queryKey" | "queryFn">;

export function useEu() {
  return useQuery({
    queryKey: ["eu"],
    queryFn: async () => desembrulhar(await api.GET("/auth/eu")),
    retry: false,
    staleTime: 60_000,
  });
}

export function useDocumentos(
  query?: DocumentosQuery,
  opcoes?: Opcoes<components["schemas"]["PaginaDocumentos"]>,
) {
  return useQuery({
    queryKey: ["documentos", query ?? {}],
    queryFn: async () =>
      desembrulhar(await api.GET("/documentos", { params: { query } })),
    ...opcoes,
  });
}

export function useDocumento(id: string) {
  return useQuery({
    queryKey: ["documento", id],
    queryFn: async () =>
      desembrulhar(
        await api.GET("/documentos/{documento_id}", {
          params: { path: { documento_id: id } },
        }),
      ),
  });
}

export function useDocumentoArquivo(id: string) {
  return useQuery({
    queryKey: ["documento", id, "arquivo"],
    // URL assinada vale 300 s: renova antes de expirar.
    staleTime: 240_000,
    queryFn: async () =>
      desembrulhar(
        await api.GET("/documentos/{documento_id}/arquivo", {
          params: { path: { documento_id: id } },
        }),
      ),
  });
}

export function useExcecoes(query?: ExcecoesQuery) {
  return useQuery({
    queryKey: ["excecoes", query ?? {}],
    queryFn: async () =>
      desembrulhar(await api.GET("/excecoes", { params: { query } })),
  });
}

export function useProcessos(query?: ProcessosQuery) {
  return useQuery({
    queryKey: ["processos", query ?? {}],
    queryFn: async () =>
      desembrulhar(await api.GET("/processos", { params: { query } })),
  });
}

export function usePainel(
  query?: PainelQuery,
  opcoes?: Opcoes<components["schemas"]["PainelSaida"]>,
) {
  return useQuery({
    queryKey: ["painel", query ?? {}],
    queryFn: async () =>
      desembrulhar(await api.GET("/painel", { params: { query } })),
    ...opcoes,
  });
}

/**
 * Decisão humana sobre uma exceção. Otimista: o item some da fila na hora e volta se a API
 * recusar. Ao fim invalida tudo que a decisão pode ter mudado.
 */
export function useDecidirExcecao() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (v: { id: string; corpo: DecisaoEntrada }) =>
      desembrulhar(
        await api.POST("/excecoes/{excecao_id}/decisao", {
          params: { path: { excecao_id: v.id } },
          body: v.corpo,
        }),
      ),
    onMutate: async (v) => {
      await queryClient.cancelQueries({ queryKey: ["excecoes"] });
      const anteriores = queryClient.getQueriesData<
        components["schemas"]["ListaExcecoesSaida"]
      >({ queryKey: ["excecoes"] });
      queryClient.setQueriesData<components["schemas"]["ListaExcecoesSaida"]>(
        { queryKey: ["excecoes"] },
        (lista) =>
          lista && {
            ...lista,
            itens: lista.itens.filter((item) => item.id !== v.id),
          },
      );
      return { anteriores };
    },
    onError: (_erro, _v, contexto) => {
      contexto?.anteriores.forEach(([chave, dados]) =>
        queryClient.setQueryData(chave, dados),
      );
    },
    onSettled: () => {
      for (const chave of [
        "excecoes",
        "documentos",
        "documento",
        "painel",
        "processos",
      ]) {
        void queryClient.invalidateQueries({ queryKey: [chave] });
      }
    },
  });
}
