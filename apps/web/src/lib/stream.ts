"use client";

import {
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { useEffect, useState } from "react";

/** Mensagem do SSE `/stream` (evento `pipeline`). */
export interface EventoPipeline {
  documento_id: string | null;
  etapa: string;
  status: string;
  mensagem: string;
  dados: Record<string, unknown> | null;
  criado_em: string;
}

/** Progresso de um documento no pipeline, montado a partir dos eventos. */
export interface ProgressoDocumento {
  etapas: Record<string, string>; // etapa → status (ok | aviso | erro)
  mensagem: string;
  recebidoEm: string | null;
}

export type ProgressoPorDocumento = Record<string, ProgressoDocumento>;
export type EstadoConexao = "conectando" | "conectado" | "reconectando";

const CHAVE_PROGRESSO = ["progresso"] as const;
const ETAPAS_QUE_MUDAM_LISTAS = new Set([
  "recebido",
  "decidido",
  "erro",
  "reconferido",
]);
const ESPERA_REABRIR_MS = 5_000;
const JANELA_INVALIDACAO_MS = 300;

/** Lê o progresso por documento (alimentado por `useStream`). */
export function useProgresso(): ProgressoPorDocumento {
  const { data } = useQuery<ProgressoPorDocumento>({
    queryKey: CHAVE_PROGRESSO,
    queryFn: () => ({}),
    initialData: {},
    staleTime: Infinity,
    gcTime: Infinity,
  });
  return data;
}

function aplicarEvento(queryClient: QueryClient, evento: EventoPipeline) {
  const id = evento.documento_id;
  if (!id) return;
  queryClient.setQueryData<ProgressoPorDocumento>(
    CHAVE_PROGRESSO,
    (atual = {}) => {
      const anterior = atual[id] ?? {
        etapas: {},
        mensagem: "",
        recebidoEm: null,
      };
      return {
        ...atual,
        [id]: {
          etapas: { ...anterior.etapas, [evento.etapa]: evento.status },
          mensagem: evento.mensagem,
          recebidoEm:
            evento.etapa === "recebido"
              ? evento.criado_em
              : anterior.recebidoEm,
        },
      };
    },
  );
}

/**
 * Conexão SSE com o pipeline (CF-124). O navegador reconecta sozinho e reenvia `Last-Event-ID`;
 * se a conexão for encerrada de vez (ex. 401), abrimos outra depois de alguns segundos, já com
 * `?desde=<último id>`. Os eventos atualizam o cache do TanStack Query: progresso por documento
 * e, nas etapas que movem cartões (recebido, decidido, erro), as listas e o painel.
 */
export function useStream(ativo: boolean = true): EstadoConexao {
  const queryClient = useQueryClient();
  const [estado, setEstado] = useState<EstadoConexao>("conectando");

  useEffect(() => {
    if (!ativo) return;
    let fonte: EventSource | null = null;
    let religar: ReturnType<typeof setTimeout> | undefined;
    let invalidar: ReturnType<typeof setTimeout> | undefined;
    let ultimoId: string | null = null;
    let encerrado = false;
    let jaConectou = false;
    const pendentes = new Set<string>();

    const agendarInvalidacao = (...chaves: string[]) => {
      chaves.forEach((c) => pendentes.add(c));
      clearTimeout(invalidar);
      invalidar = setTimeout(() => {
        pendentes.forEach(
          (chave) => void queryClient.invalidateQueries({ queryKey: [chave] }),
        );
        pendentes.clear();
      }, JANELA_INVALIDACAO_MS);
    };

    const abrir = () => {
      const url = ultimoId ? `/api/stream?desde=${ultimoId}` : "/api/stream";
      fonte = new EventSource(url, { withCredentials: true });
      fonte.onopen = () => {
        setEstado("conectado");
        if (jaConectou) agendarInvalidacao("documentos", "painel", "excecoes");
        jaConectou = true;
      };
      fonte.addEventListener("pipeline", (mensagem) => {
        const evento = JSON.parse(
          (mensagem as MessageEvent<string>).data,
        ) as EventoPipeline;
        ultimoId = (mensagem as MessageEvent<string>).lastEventId || ultimoId;
        aplicarEvento(queryClient, evento);
        if (ETAPAS_QUE_MUDAM_LISTAS.has(evento.etapa)) {
          agendarInvalidacao("documentos", "painel", "excecoes", "processos");
          if (evento.documento_id) agendarInvalidacao("documento");
        }
      });
      fonte.onerror = () => {
        setEstado("reconectando");
        if (fonte?.readyState === EventSource.CLOSED && !encerrado) {
          fonte.close();
          religar = setTimeout(abrir, ESPERA_REABRIR_MS);
        }
      };
    };

    abrir();
    return () => {
      encerrado = true;
      clearTimeout(religar);
      clearTimeout(invalidar);
      fonte?.close();
    };
  }, [queryClient, ativo]);

  return estado;
}
