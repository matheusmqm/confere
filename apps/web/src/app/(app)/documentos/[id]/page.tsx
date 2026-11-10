"use client";

import { ArrowLeft } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { BadgeEstado } from "@/components/badge-estado";
import { CelulaDinheiro } from "@/components/celula-dinheiro";
import type { Caixa } from "@/components/documento/visualizador";
import { AcoesExcecao } from "@/components/excecoes/acoes-excecao";
import { EstadoErro } from "@/components/estados";
import { MedidorConfianca } from "@/components/medidor-confianca";
import { SeloIA } from "@/components/selo-ia";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useDecidirExcecao,
  useDocumento,
  useDocumentoArquivo,
} from "@/lib/api/hooks";
import type { components } from "@/lib/api/schema";
import { formatarData, formatarHora } from "@/lib/datas";
import { formatarBRL } from "@/lib/dinheiro";
import {
  metodoUsaIA,
  ROTULO_ESTADO_LINHA,
  rotuloTipoExcecao,
} from "@/lib/rotulos";
import { cn } from "cn";

type Detalhe = components["schemas"]["DocumentoDetalhe"];
type Linha = components["schemas"]["LinhaSaida"];

// react-pdf usa APIs do navegador: carregado só no cliente.
const Visualizador = dynamic(
  () => import("@/components/documento/visualizador"),
  {
    ssr: false,
    loading: () => <Skeleton className="h-[640px] w-full" />,
  },
);

const ROTULO_ETAPA: Record<string, string> = {
  recebido: "Recebido",
  lido: "Lido",
  extraido: "Extraído",
  processo: "Processo",
  codigos: "Códigos",
  casado: "Casado",
  decidido: "Decidido",
  reconferido: "Reconferido",
  erro: "Erro",
};

const BOLINHA_STATUS: Record<string, string> = {
  ok: "bg-verde-conferido",
  aviso: "bg-ambar",
  erro: "bg-vermelho",
};

function confiancaGeral(l: Linha): number | null {
  const valores = [l.conf_extracao, l.conf_processo, l.conf_codigo].filter(
    (v): v is number => typeof v === "number",
  );
  return valores.length ? Math.min(...valores) : null;
}

function caixasDe(linhas: Linha[]): Caixa[] {
  const caixas: Caixa[] = [];
  for (const l of linhas) {
    const b = l.bbox as (Partial<Caixa> & { pagina?: number }) | null;
    if (
      b &&
      typeof b.pagina === "number" &&
      [b.x0, b.y0, b.x1, b.y1].every((n) => typeof n === "number")
    ) {
      caixas.push({
        linhaId: l.id,
        pagina: b.pagina,
        x0: b.x0 as number,
        y0: b.y0 as number,
        x1: b.x1 as number,
        y1: b.y1 as number,
        estado: l.estado,
      });
    }
  }
  return caixas;
}

function Cabecalho({ d }: { d: Detalhe }) {
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1
            className="truncate text-xl font-semibold"
            title={d.nome_original}
          >
            {d.fornecedor?.nome ?? "Fornecedor não identificado"}
          </h1>
          <p className="valor text-sm text-tinta-500">
            {d.numero ?? d.nome_original}
          </p>
        </div>
        <BadgeEstado estado={d.status} />
      </div>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
        <div>
          <dt className="rotulo text-tinta-500">Emissão</dt>
          <dd className="valor">{formatarData(d.emissao)}</dd>
        </div>
        <div>
          <dt className="rotulo text-tinta-500">Vencimento</dt>
          <dd className="valor">{formatarData(d.vencimento)}</dd>
        </div>
        <div>
          <dt className="rotulo text-tinta-500">Total</dt>
          <dd>
            <CelulaDinheiro
              valor={d.total}
              moeda={d.moeda ?? "BRL"}
              className="text-left font-medium"
            />
          </dd>
        </div>
        <div>
          <dt className="rotulo text-tinta-500">Score · τ</dt>
          <dd className="valor">
            {d.decisao.score != null
              ? d.decisao.score.toFixed(2).replace(".", ",")
              : "—"}
            {" · "}
            {d.decisao.tau != null
              ? d.decisao.tau.toFixed(2).replace(".", ",")
              : "—"}
          </dd>
        </div>
      </dl>
      {d.decisao.motivos.length ? (
        <p className="text-[13px] text-tinta-500">
          Motivos da decisão:{" "}
          {d.decisao.motivos.map((m) => rotuloTipoExcecao(m)).join(", ")}
        </p>
      ) : null}
      {d.avisos.length ? (
        <ul className="rounded-sm bg-ambar-fundo px-3 py-2 text-[13px] text-ambar-texto">
          {d.avisos.map((a, i) => (
            <li key={i}>{String(a)}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function TabelaLinhas({
  linhas,
  ativa,
  aoAtivar,
  aoEscolher,
}: {
  linhas: Linha[];
  ativa: string | null;
  aoAtivar: (id: string | null) => void;
  aoEscolher: (id: string) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-card">
      <Table>
        <TableHeader>
          <TableRow className="bg-papel">
            {[
              "Descrição",
              "Processo",
              "Código",
              "Confiança",
              "Cobrado",
              "Previsto",
              "Diferença",
              "Estado",
            ].map((c, i) => (
              <TableHead
                key={c}
                className={cn(
                  "rotulo text-tinta-700",
                  i >= 4 && i <= 6 && "text-right",
                )}
              >
                {c}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {linhas.map((l) => (
            <TableRow
              key={l.id}
              tabIndex={0}
              aria-selected={ativa === l.id}
              onMouseEnter={() => aoEscolher(l.id)}
              onMouseLeave={() => aoAtivar(null)}
              onFocus={() => aoEscolher(l.id)}
              onClick={() => aoEscolher(l.id)}
              className={cn(
                "cursor-pointer text-[13px] outline-none focus-visible:ring-2 focus-visible:ring-cobalto",
                ativa === l.id && "bg-cobalto-fundo",
              )}
            >
              <TableCell className="max-w-56 truncate" title={l.descricao}>
                {l.descricao}
              </TableCell>
              <TableCell className="valor">
                {l.processo?.codigo ?? "—"}
              </TableCell>
              <TableCell>
                <span className="inline-flex items-center gap-1.5">
                  <span className="valor">{l.codigo_custo ?? "—"}</span>
                  {metodoUsaIA(l.metodo_codigo) ? <SeloIA /> : null}
                </span>
              </TableCell>
              <TableCell>
                <MedidorConfianca
                  valor={confiancaGeral(l)}
                  breakdown={{
                    extracao: l.conf_extracao,
                    processo: l.conf_processo,
                    codigo: l.conf_codigo,
                  }}
                />
              </TableCell>
              <TableCell>
                <CelulaDinheiro valor={l.valor} moeda={l.moeda} />
              </TableCell>
              <TableCell>
                <CelulaDinheiro
                  valor={l.casamento?.provisao.valor}
                  moeda={l.casamento?.provisao.moeda}
                />
              </TableCell>
              <TableCell>
                <CelulaDinheiro valor={l.casamento?.diferenca_brl} diferenca />
              </TableCell>
              <TableCell>{ROTULO_ESTADO_LINHA[l.estado] ?? l.estado}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function Excecoes({ d }: { d: Detalhe }) {
  const decidir = useDecidirExcecao();
  if (d.excecoes.length === 0) {
    return (
      <p className="rounded-lg border border-border bg-card p-4 text-sm text-tinta-500">
        Nenhuma exceção neste documento.
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-3">
      {d.excecoes.map((e) => (
        <li
          key={e.id}
          className="flex flex-col gap-2 rounded-lg border border-border bg-card p-4"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-semibold">{rotuloTipoExcecao(e.tipo)}</span>
            <span className="valor text-sm font-medium">
              {formatarBRL(e.valor_brl_em_risco)}
              <span className="ml-2 text-xs font-normal text-tinta-500">
                {e.status === "aberta" ? "em risco" : "resolvida"}
              </span>
            </span>
          </div>
          {e.explicacao ? (
            <div className="flex flex-col gap-1 rounded-sm border border-roxo-ia/40 bg-roxo-fundo px-3 py-2">
              <SeloIA rotulo="IA explica" className="w-fit" />
              <p className="text-sm">{e.explicacao}</p>
              {e.acao_sugerida ? (
                <p className="text-[13px] text-tinta-700">
                  Sugestão: {e.acao_sugerida}
                </p>
              ) : null}
            </div>
          ) : null}
          {e.status === "aberta" ? (
            <AcoesExcecao
              tipo={e.tipo}
              podeRepassar={!!e.linha_id}
              desabilitado={decidir.isPending}
              onAcao={(acao) =>
                decidir.mutate(
                  {
                    id: e.id,
                    corpo: {
                      acao,
                      linha_id: acao === "repassar" ? e.linha_id : undefined,
                    },
                  },
                  {
                    onSuccess: () => toast.success("Decisão registrada."),
                    onError: (erro) => toast.error(erro.message),
                  },
                )
              }
            />
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function LinhaDoTempo({ d }: { d: Detalhe }) {
  return (
    <ol className="flex flex-col gap-2 rounded-lg border border-border bg-card p-4">
      {d.eventos.length === 0 ? (
        <li className="text-sm text-tinta-500">Sem eventos registrados.</li>
      ) : (
        d.eventos.map((e) => (
          <li key={e.id} className="flex items-start gap-3 text-[13px]">
            <span
              aria-hidden
              className={cn(
                "mt-1.5 size-2 shrink-0 rounded-full",
                BOLINHA_STATUS[e.status] ?? "bg-tinta-300",
              )}
            />
            <span className="valor w-20 shrink-0 text-tinta-500">
              {formatarHora(e.criado_em)}
            </span>
            <span className="w-24 shrink-0 font-medium">
              {ROTULO_ETAPA[e.etapa] ?? e.etapa}
            </span>
            <span className="text-tinta-700">{e.mensagem}</span>
          </li>
        ))
      )}
    </ol>
  );
}

/** Tela Documento: arquivo à esquerda com caixas; cabeçalho, linhas, exceções e eventos à direita. */
export default function DocumentoPage() {
  const { id } = useParams<{ id: string }>();
  const documento = useDocumento(id);
  const arquivo = useDocumentoArquivo(id);
  const [ativa, setAtiva] = useState<string | null>(null);
  const [rolar, setRolar] = useState<{ linhaId: string; n: number } | null>(
    null,
  );

  const caixas = useMemo(
    () => caixasDe(documento.data?.linhas ?? []),
    [documento.data],
  );

  if (documento.isError) {
    return (
      <EstadoErro
        mensagem={documento.error.message}
        aoTentarDeNovo={() => void documento.refetch()}
      />
    );
  }
  if (documento.isPending) {
    return (
      <div className="grid gap-6 xl:grid-cols-2">
        <Skeleton className="h-[640px]" />
        <Skeleton className="h-[640px]" />
      </div>
    );
  }
  const d = documento.data;

  return (
    <div className="flex flex-col gap-4">
      <Link
        href="/"
        className="inline-flex w-fit items-center gap-1 text-sm text-cobalto-texto hover:underline"
      >
        <ArrowLeft aria-hidden className="size-4" />
        Inbox
      </Link>

      <div className="grid items-start gap-6 xl:grid-cols-2">
        <section
          aria-label="Arquivo do documento"
          className="xl:sticky xl:top-20 xl:max-h-[calc(100vh-6rem)] xl:overflow-y-auto"
        >
          {d.tipo_arquivo === "xml" ? (
            <p className="rounded-lg border border-border bg-card p-4 text-sm text-tinta-500">
              Documentos XML não têm visualização.
            </p>
          ) : arquivo.isPending ? (
            <Skeleton className="h-[640px] w-full" />
          ) : arquivo.isError ? (
            <EstadoErro
              mensagem={arquivo.error.message}
              aoTentarDeNovo={() => void arquivo.refetch()}
            />
          ) : (
            <>
              {caixas.length === 0 ? (
                <p className="mb-3 rounded-sm bg-papel px-3 py-2 text-[13px] text-tinta-500">
                  Sem destaque disponível para este documento.
                </p>
              ) : null}
              <Visualizador
                url={arquivo.data.url}
                tipoArquivo={arquivo.data.tipo_arquivo}
                caixas={caixas}
                ativa={ativa}
                aoPassarMouse={setAtiva}
                rolarPara={rolar}
              />
            </>
          )}
        </section>

        <div className="flex min-w-0 flex-col gap-6">
          <Cabecalho d={d} />
          <section
            aria-labelledby="titulo-linhas"
            className="flex flex-col gap-2"
          >
            <h2 id="titulo-linhas" className="text-base font-semibold">
              Linhas
            </h2>
            <TabelaLinhas
              linhas={d.linhas}
              ativa={ativa}
              aoAtivar={setAtiva}
              aoEscolher={(linhaId) => {
                setAtiva(linhaId);
                setRolar((anterior) => ({
                  linhaId,
                  n: (anterior?.n ?? 0) + 1,
                }));
              }}
            />
          </section>
          <section
            aria-labelledby="titulo-excecoes"
            className="flex flex-col gap-2"
          >
            <h2 id="titulo-excecoes" className="text-base font-semibold">
              Exceções
            </h2>
            <Excecoes d={d} />
          </section>
          <section
            aria-labelledby="titulo-eventos"
            className="flex flex-col gap-2"
          >
            <h2 id="titulo-eventos" className="text-base font-semibold">
              Linha do tempo
            </h2>
            <LinhaDoTempo d={d} />
          </section>
        </div>
      </div>
    </div>
  );
}
