"use client";

import { LayoutGroup } from "framer-motion";
import { BotaoSoltarLote } from "@/components/app/demo";
import { EstadoErro, EstadoVazio } from "@/components/estados";
import { CartaoDocumento } from "@/components/inbox/cartao-documento";
import { ZonaUpload } from "@/components/inbox/zona-upload";
import { Skeleton } from "@/components/ui/skeleton";
import { useDocumentos } from "@/lib/api/hooks";
import { useProgresso } from "@/lib/stream";

const POR_COLUNA = 50;

const COLUNAS = [
  {
    id: "chegando",
    titulo: "Chegando",
    vazio: "Nada chegando agora.",
    estados: ["recebido", "processando"],
  },
  {
    id: "aprovados",
    titulo: "Aprovados",
    vazio: "Nenhuma fatura aprovada ainda.",
    estados: ["aprovado_auto", "aprovado_manual"],
  },
  {
    id: "revisar",
    titulo: "Revisar",
    vazio: "Nada para revisar. Bom sinal.",
    estados: ["em_revisao", "bloqueado"],
  },
] as const;

/** Inbox ao vivo: Chegando → Aprovados / Revisar (CF-124). O SSE roda no shell do app. */
export default function InboxPage() {
  const documentos = useDocumentos({ limite: 200 });
  const progresso = useProgresso();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-[28px] leading-9 font-semibold tracking-tight">
          Inbox
        </h1>
        <BotaoSoltarLote />
      </div>

      <ZonaUpload />

      {documentos.isError ? (
        <EstadoErro
          mensagem={documentos.error.message}
          aoTentarDeNovo={() => void documentos.refetch()}
        />
      ) : (
        <LayoutGroup>
          <div className="grid items-start gap-6 lg:grid-cols-3">
            {COLUNAS.map((coluna) => {
              const itens = (documentos.data?.itens ?? [])
                .filter((d) =>
                  (coluna.estados as readonly string[]).includes(d.status),
                )
                .slice(0, POR_COLUNA);
              return (
                <section
                  key={coluna.id}
                  aria-labelledby={`coluna-${coluna.id}`}
                  className="flex flex-col gap-3 rounded-lg bg-papel p-3"
                >
                  <h2
                    id={`coluna-${coluna.id}`}
                    className="flex items-center justify-between px-1 text-base font-semibold"
                  >
                    {coluna.titulo}
                    <span className="valor text-sm font-normal text-tinta-500">
                      {itens.length}
                    </span>
                  </h2>
                  {documentos.isPending ? (
                    <>
                      <Skeleton className="h-28 w-full" />
                      <Skeleton className="h-28 w-full" />
                    </>
                  ) : itens.length === 0 ? (
                    <EstadoVazio
                      titulo={coluna.vazio}
                      className="bg-background py-6"
                    />
                  ) : (
                    <ul className="flex flex-col gap-3">
                      {itens.map((documento) => (
                        <CartaoDocumento
                          key={documento.id}
                          documento={documento}
                          progresso={progresso[documento.id]}
                        />
                      ))}
                    </ul>
                  )}
                </section>
              );
            })}
          </div>
        </LayoutGroup>
      )}
    </div>
  );
}
