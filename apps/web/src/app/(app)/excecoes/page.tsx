"use client";

import { cn } from "cn";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { CelulaDinheiro } from "@/components/celula-dinheiro";
import {
  AcoesExcecao,
  acaoDeCorrecao,
} from "@/components/excecoes/acoes-excecao";
import { EstadoErro, EstadoVazio } from "@/components/estados";
import { SeloIA } from "@/components/selo-ia";
import { Skeleton } from "@/components/ui/skeleton";
import { useDecidirExcecao, useExcecoes } from "@/lib/api/hooks";
import type { components } from "@/lib/api/schema";
import { formatarBRL } from "@/lib/dinheiro";
import { rotuloTipoExcecao } from "@/lib/rotulos";

type Item = components["schemas"]["ExcecaoItem"];
type Acao = components["schemas"]["DecisaoEntrada"]["acao"];

const ROTULO_ACAO: Record<Acao, string> = {
  aprovar: "Aprovada",
  contestar: "Contestada",
  corrigir_processo: "Correção de processo enviada",
  corrigir_codigo: "Correção de código enviada",
  repassar: "Marcada para repasse",
  bloquear: "Bloqueada",
};

const ATALHOS: Record<
  string,
  "aprovar" | "contestar" | "corrigir" | "repassar"
> = {
  a: "aprovar",
  c: "contestar",
  e: "corrigir",
  r: "repassar",
};

function digitando(alvo: EventTarget | null): boolean {
  const el = alvo as HTMLElement | null;
  return (
    !!el &&
    (["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) ||
      el.isContentEditable)
  );
}

/** Fila de exceções por R$ em risco, com ação de 1 clique e atalhos de teclado (CF-127). */
export default function ExcecoesPage() {
  const [tipo, setTipo] = useState<string | undefined>();
  const [fornecedorId, setFornecedorId] = useState<string | undefined>();
  const [foco, setFoco] = useState(0);
  const lista = useExcecoes({
    status: "aberta",
    tipo,
    fornecedor_id: fornecedorId,
  });
  const semFiltro = useExcecoes({ status: "aberta" }); // base dos chips e do select
  const decidir = useDecidirExcecao();
  const itens = useMemo(() => lista.data?.itens ?? [], [lista.data]);
  const refs = useRef<Record<string, HTMLElement | null>>({});

  const fornecedores = useMemo(() => {
    const mapa = new Map<string, string>();
    for (const i of semFiltro.data?.itens ?? []) {
      if (i.fornecedor) mapa.set(i.fornecedor.id, i.fornecedor.nome);
    }
    return [...mapa].sort((a, b) => a[1].localeCompare(b[1], "pt-BR"));
  }, [semFiltro.data]);

  const focoAtual = Math.min(foco, Math.max(0, itens.length - 1));

  const agir = useCallback(
    (item: Item, acao: Acao) => {
      decidir.mutate(
        {
          id: item.id,
          corpo: {
            acao,
            linha_id: acao === "repassar" ? item.linha?.id : undefined,
          },
        },
        {
          onSuccess: () =>
            toast.success(
              `${ROTULO_ACAO[acao]}: ${rotuloTipoExcecao(item.tipo)}.`,
            ),
          onError: (erro) => toast.error(erro.message),
        },
      );
    },
    [decidir],
  );

  useEffect(() => {
    function aoTeclar(e: KeyboardEvent) {
      if (digitando(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const proximo = Math.min(
          itens.length - 1,
          Math.max(0, focoAtual + (e.key === "ArrowDown" ? 1 : -1)),
        );
        setFoco(proximo);
        refs.current[itens[proximo]?.id]?.scrollIntoView({ block: "nearest" });
        return;
      }
      const atalho = ATALHOS[e.key.toLowerCase()];
      const item = itens[focoAtual];
      if (!atalho || !item) return;
      e.preventDefault();
      if (atalho === "repassar" && !item.linha) return;
      agir(item, atalho === "corrigir" ? acaoDeCorrecao(item.tipo) : atalho);
    }
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, [itens, focoAtual, agir]);

  const facetas = semFiltro.data?.facetas ?? {};
  const total = Object.values(facetas).reduce((a, b) => a + b, 0);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[28px] leading-9 font-semibold tracking-tight">
            Exceções
          </h1>
          <p className="text-sm text-tinta-500">
            Ordenadas por valor em risco.
          </p>
        </div>
        <label className="flex flex-col gap-1 text-sm">
          <span className="rotulo text-tinta-500">Fornecedor</span>
          <select
            value={fornecedorId ?? ""}
            onChange={(e) => {
              setFornecedorId(e.target.value || undefined);
              setFoco(0);
            }}
            className="h-8 min-w-52 rounded-sm border border-input bg-background px-2 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <option value="">Todos os fornecedores</option>
            {fornecedores.map(([id, nome]) => (
              <option key={id} value={id}>
                {nome}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div
        role="group"
        aria-label="Filtrar por tipo"
        className="flex flex-wrap gap-2"
      >
        {[
          { id: undefined, rotulo: "Todas", n: total },
          ...Object.entries(facetas).map(([id, n]) => ({
            id,
            rotulo: rotuloTipoExcecao(id),
            n,
          })),
        ].map((chip) => (
          <button
            key={chip.id ?? "todas"}
            type="button"
            aria-pressed={tipo === chip.id}
            onClick={() => {
              setTipo(chip.id);
              setFoco(0);
            }}
            className={cn(
              "inline-flex h-7 items-center gap-1.5 rounded-sm border px-2.5 text-[13px] font-medium outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
              tipo === chip.id
                ? "border-cobalto bg-cobalto-fundo text-cobalto-texto"
                : "border-border bg-background text-tinta-700 hover:bg-papel",
            )}
          >
            {chip.rotulo}
            <span className="valor text-xs">{chip.n}</span>
          </button>
        ))}
      </div>

      <p className="text-xs text-tinta-500">
        Atalhos: <kbd className="valor">↑</kbd>/<kbd className="valor">↓</kbd>{" "}
        navegam · <kbd className="valor">A</kbd> aprovar ·{" "}
        <kbd className="valor">C</kbd> contestar ·{" "}
        <kbd className="valor">E</kbd> corrigir · <kbd className="valor">R</kbd>{" "}
        repassar
      </p>

      {lista.isError ? (
        <EstadoErro
          mensagem={lista.error.message}
          aoTentarDeNovo={() => void lista.refetch()}
        />
      ) : lista.isPending ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      ) : itens.length === 0 ? (
        <EstadoVazio
          titulo="Nenhuma exceção aberta"
          descricao="Tudo o que chegou foi conferido. Quando algo divergir, aparece aqui."
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {itens.map((item, indice) => (
            <li
              key={item.id}
              ref={(el) => {
                refs.current[item.id] = el;
              }}
              onClick={() => setFoco(indice)}
              aria-current={indice === focoAtual}
              className={cn(
                "flex flex-col gap-3 rounded-lg border bg-card p-4",
                indice === focoAtual
                  ? "border-cobalto ring-2 ring-cobalto/20"
                  : "border-border",
              )}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex flex-col gap-0.5">
                  <span className="text-base font-semibold">
                    {rotuloTipoExcecao(item.tipo)}
                  </span>
                  <span className="text-[13px] text-tinta-500">
                    {item.fornecedor?.nome ?? "Fornecedor não identificado"}
                    {item.processo ? (
                      <>
                        {" · "}
                        <span className="valor">{item.processo.codigo}</span>
                      </>
                    ) : null}
                    {" · "}
                    <Link
                      href={`/documentos/${item.documento.id}`}
                      className="text-cobalto-texto underline-offset-2 hover:underline"
                    >
                      <span className="valor">
                        {item.documento.numero ?? item.documento.nome}
                      </span>
                    </Link>
                  </span>
                </div>
                <div className="flex flex-col items-end">
                  <span className="rotulo text-tinta-500">Em risco</span>
                  <span className="valor text-sm font-medium">
                    {formatarBRL(item.valor_brl_em_risco)}
                  </span>
                </div>
              </div>

              {item.linha ? (
                <div className="flex items-center justify-between gap-3 rounded-sm bg-papel px-3 py-2 text-[13px]">
                  <span className="min-w-0 truncate">
                    {item.linha.descricao}
                  </span>
                  <CelulaDinheiro
                    valor={item.linha.valor}
                    moeda={item.linha.moeda}
                    className="w-auto"
                  />
                </div>
              ) : null}

              {item.explicacao ? (
                <div className="flex flex-col gap-1 rounded-sm border border-roxo-ia/40 bg-roxo-fundo px-3 py-2">
                  <SeloIA rotulo="IA explica" className="w-fit" />
                  <p className="text-sm text-tinta-900">{item.explicacao}</p>
                  {item.acao_sugerida ? (
                    <p className="text-[13px] text-tinta-700">
                      Sugestão: {item.acao_sugerida}
                    </p>
                  ) : null}
                </div>
              ) : null}

              <AcoesExcecao
                tipo={item.tipo}
                podeRepassar={!!item.linha}
                atalhos={indice === focoAtual}
                desabilitado={decidir.isPending}
                onAcao={(acao) => agir(item, acao)}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
