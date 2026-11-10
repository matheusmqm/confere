"use client";

import { cn } from "cn";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { MODO_DEMO } from "@/components/app/demo";
import { EstadoErro, EstadoVazio } from "@/components/estados";
import {
  BarrasHorizontais,
  CurvaRiscoCobertura,
  Sparkline,
} from "@/components/painel/graficos";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { interpolarPorAlpha, useAvaliacao } from "@/lib/avaliacao";
import { usePainel } from "@/lib/api/hooks";
import { formatarBRL, formatarMoeda, paraNumero } from "@/lib/dinheiro";
import { rotuloTipoExcecao } from "@/lib/rotulos";

const porcento = new Intl.NumberFormat("pt-BR", {
  style: "percent",
  maximumFractionDigits: 1,
});

function formatarDuracao(segundos: number | null): string {
  if (segundos === null) return "—";
  if (segundos < 60) return `${segundos.toFixed(1).replace(".", ",")} s`;
  const min = Math.floor(segundos / 60);
  return `${min} min ${String(Math.round(segundos % 60)).padStart(2, "0")} s`;
}

/** Cartão de KPI com o baseline B0 (processo manual) ao lado. */
function Kpi({
  rotulo,
  valor,
  baseline,
}: {
  rotulo: string;
  valor: string;
  baseline: string;
}) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border bg-card p-4">
      <span className="rotulo text-tinta-500">{rotulo}</span>
      <span className="valor text-[28px] leading-10 font-medium tracking-tight">
        {valor}
      </span>
      <span className="text-[13px] text-tinta-500">
        <span className="font-medium text-tinta-700">B0 (manual):</span>{" "}
        {baseline}
      </span>
    </div>
  );
}

/** Tabela equivalente a um gráfico, para leitores de tela e para conferir os números. */
function TabelaAlternativa({
  titulo,
  colunas,
  linhas,
}: {
  titulo: string;
  colunas: string[];
  linhas: string[][];
}) {
  return (
    <details className="text-sm">
      <summary className="cursor-pointer text-cobalto-texto">
        Ver {titulo} como tabela
      </summary>
      <table className="mt-2 w-full border-collapse text-[13px]">
        <caption className="sr-only">{titulo}</caption>
        <thead>
          <tr className="bg-papel text-left">
            {colunas.map((c) => (
              <th
                key={c}
                scope="col"
                className="rotulo px-3 py-2 text-tinta-700"
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {linhas.map((linha, i) => (
            <tr key={i} className="border-t border-border">
              {linha.map((celula, j) => (
                <td
                  key={j}
                  className={cn("px-3 py-1.5", j > 0 && "valor text-right")}
                >
                  {celula}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

function Secao({
  titulo,
  children,
}: {
  titulo: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4">
      <h2 className="text-base font-semibold">{titulo}</h2>
      {children}
    </section>
  );
}

/** Painel de KPIs, curva risco × cobertura, ranking de fornecedores e baselines (CF-130). */
export default function PainelPage() {
  const [lote, setLote] = useState<"demo" | "todos">(
    MODO_DEMO ? "demo" : "todos",
  );
  const painel = usePainel({ lote }, { refetchInterval: 10_000 });
  const avaliacao = useAvaliacao();
  const [alpha, setAlpha] = useState<number | null>(null);
  const [aplicando, setAplicando] = useState(false);

  const curva = avaliacao.data?.curva;
  const alphas = useMemo(() => (curva ?? []).map((p) => p.alpha), [curva]);
  const alphaMin = alphas.length ? Math.min(...alphas) : 0;
  const alphaMax = alphas.length ? Math.max(...alphas) : 1;
  const alphaEscolhido = alpha ?? avaliacao.data?.alpha_atual ?? alphaMin;
  const estimado = curva ? interpolarPorAlpha(curva, alphaEscolhido) : null;

  async function aplicar() {
    setAplicando(true);
    try {
      const resposta = await fetch("/api/politica", {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ alpha: alphaEscolhido }),
      });
      if (!resposta.ok)
        throw new Error("A política ainda não pode ser alterada pela API.");
      toast.success("Política aplicada.");
    } catch (erro) {
      toast.error(
        erro instanceof Error ? erro.message : "Falha ao aplicar a política.",
      );
    } finally {
      setAplicando(false);
    }
  }

  if (painel.isError) {
    return (
      <EstadoErro
        mensagem={painel.error.message}
        aoTentarDeNovo={() => void painel.refetch()}
      />
    );
  }
  if (painel.isPending) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-8 w-40" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
        <Skeleton className="h-72" />
      </div>
    );
  }

  const { kpis, serie_temporal, ranking_fornecedores, por_tipo_excecao } =
    painel.data;
  const serie = serie_temporal.map((p) => ({
    x: new Date(p.instante).toLocaleString("pt-BR"),
    y: paraNumero(p.rs_evitado),
  }));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-[28px] leading-9 font-semibold tracking-tight">
          Painel
        </h1>
        <div role="group" aria-label="Lote" className="flex gap-1">
          {(["demo", "todos"] as const).map((opcao) => (
            <Button
              key={opcao}
              size="sm"
              variant={lote === opcao ? "default" : "outline"}
              aria-pressed={lote === opcao}
              onClick={() => setLote(opcao)}
            >
              {opcao === "demo" ? "Lote da demo" : "Todos os documentos"}
            </Button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <Kpi
          rotulo="R$ evitado"
          valor={formatarBRL(kpis.rs_evitado.valor)}
          baseline={formatarBRL(kpis.rs_evitado.baseline ?? "0")}
        />
        <Kpi
          rotulo="Sem toque"
          valor={porcento.format(kpis.pct_sem_toque.valor)}
          baseline={porcento.format(kpis.pct_sem_toque.baseline ?? 0)}
        />
        <Kpi
          rotulo="Tempo mediano"
          valor={formatarDuracao(kpis.tempo_mediano_s.valor)}
          baseline="processo manual"
        />
        <Kpi
          rotulo="Tempo p95"
          valor={formatarDuracao(kpis.tempo_p95_s.valor)}
          baseline="processo manual"
        />
        <Kpi
          rotulo="Custo de IA por fatura"
          valor={formatarMoeda(kpis.custo_ia_por_fatura_usd.valor, "USD")}
          baseline="sem IA"
        />
      </div>

      <Secao titulo="R$ evitado ao longo do tempo">
        {serie.length === 0 ? (
          <EstadoVazio titulo="Ainda não há documentos decididos neste período." />
        ) : (
          <>
            <Sparkline dados={serie} rotulo="R$ evitado ao longo do tempo" />
            <TabelaAlternativa
              titulo="a série de R$ evitado"
              colunas={["Instante", "Documentos", "R$ evitado"]}
              linhas={serie_temporal.map((p) => [
                new Date(p.instante).toLocaleString("pt-BR"),
                String(p.documentos),
                formatarBRL(p.rs_evitado),
              ])}
            />
          </>
        )}
      </Secao>

      <Secao titulo="Risco × cobertura">
        {avaliacao.isPending ? (
          <Skeleton className="h-72" />
        ) : !curva || curva.length === 0 || !estimado ? (
          <EstadoVazio
            titulo="Curva indisponível"
            descricao="Rode make eval para gerar a avaliação no conjunto de teste."
          />
        ) : (
          <>
            <CurvaRiscoCobertura curva={curva} atual={estimado} />
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <label className="flex flex-1 flex-col gap-2 text-sm">
                <span className="rotulo text-tinta-500">
                  α (risco máximo aceito):{" "}
                  <span className="valor text-tinta-900">
                    {alphaEscolhido.toFixed(3).replace(".", ",")}
                  </span>
                </span>
                <Slider
                  min={alphaMin}
                  max={alphaMax}
                  step={(alphaMax - alphaMin) / 100 || 0.001}
                  value={[alphaEscolhido]}
                  aria-label="Alfa"
                  onValueChange={(v) => setAlpha(Array.isArray(v) ? v[0] : v)}
                />
              </label>
              <p className="valor text-sm">
                Cobertura {porcento.format(estimado.cobertura)} · Risco{" "}
                {porcento.format(estimado.risco)}
              </p>
              <Button onClick={() => void aplicar()} disabled={aplicando}>
                Aplicar
              </Button>
            </div>
            <TabelaAlternativa
              titulo="a curva"
              colunas={["α", "Cobertura", "Risco"]}
              linhas={curva.map((p) => [
                p.alpha.toFixed(3).replace(".", ","),
                porcento.format(p.cobertura),
                porcento.format(p.risco),
              ])}
            />
          </>
        )}
      </Secao>

      <div className="grid gap-6 xl:grid-cols-2">
        <Secao titulo="Fornecedores com mais valor em risco">
          {ranking_fornecedores.length === 0 ? (
            <EstadoVazio titulo="Nenhum fornecedor com documentos neste período." />
          ) : (
            <>
              <BarrasHorizontais
                rotulo="Ranking de fornecedores por R$ em risco"
                nomeValor="R$ em risco"
                dados={ranking_fornecedores.map((f) => ({
                  nome: f.nome,
                  valor: paraNumero(f.rs_em_risco),
                }))}
              />
              <TabelaAlternativa
                titulo="o ranking de fornecedores"
                colunas={[
                  "Fornecedor",
                  "R$ em risco",
                  "R$ evitado",
                  "Documentos",
                  "Com exceção",
                  "Erro mais comum",
                ]}
                linhas={ranking_fornecedores.map((f) => [
                  f.nome,
                  formatarBRL(f.rs_em_risco),
                  formatarBRL(f.rs_evitado),
                  String(f.n_documentos),
                  porcento.format(f.pct_com_excecao),
                  f.tipo_mais_comum
                    ? rotuloTipoExcecao(f.tipo_mais_comum)
                    : "—",
                ])}
              />
            </>
          )}
        </Secao>

        <Secao titulo="Exceções por tipo">
          {por_tipo_excecao.length === 0 ? (
            <EstadoVazio titulo="Nenhuma exceção neste período." />
          ) : (
            <>
              <BarrasHorizontais
                rotulo="R$ por tipo de exceção"
                nomeValor="R$"
                dados={por_tipo_excecao.map((t) => ({
                  nome: rotuloTipoExcecao(t.tipo),
                  valor: paraNumero(t.rs),
                }))}
              />
              <TabelaAlternativa
                titulo="as exceções por tipo"
                colunas={["Tipo", "R$", "Quantidade"]}
                linhas={por_tipo_excecao.map((t) => [
                  rotuloTipoExcecao(t.tipo),
                  formatarBRL(t.rs),
                  String(t.quantidade),
                ])}
              />
            </>
          )}
        </Secao>
      </div>

      <Secao titulo="Baselines × Confere">
        {avaliacao.data ? (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <caption className="sr-only">
                Comparação entre os baselines B0 a B3 e o Confere
              </caption>
              <thead>
                <tr className="bg-papel text-left">
                  <th scope="col" className="rotulo px-3 py-2 text-tinta-700">
                    Método
                  </th>
                  <th
                    scope="col"
                    className="rotulo px-3 py-2 text-right text-tinta-700"
                  >
                    Sem toque
                  </th>
                  <th
                    scope="col"
                    className="rotulo px-3 py-2 text-right text-tinta-700"
                  >
                    R$ evitado
                  </th>
                  <th
                    scope="col"
                    className="rotulo px-3 py-2 text-right text-tinta-700"
                  >
                    Aprovações erradas
                  </th>
                </tr>
              </thead>
              <tbody>
                {avaliacao.data.baselines.map((b) => (
                  <tr
                    key={b.id}
                    className={cn(
                      "border-t border-border",
                      b.id.toLowerCase() === "confere" &&
                        "bg-verde-fundo font-medium",
                    )}
                  >
                    <th scope="row" className="px-3 py-2 text-left font-medium">
                      <span className="valor mr-2 text-tinta-500">{b.id}</span>
                      {b.nome}
                    </th>
                    <td className="valor px-3 py-2 text-right">
                      {porcento.format(b.sem_toque)}
                    </td>
                    <td className="valor px-3 py-2 text-right">
                      {formatarBRL(b.rs_evitado)}
                    </td>
                    <td className="valor px-3 py-2 text-right">
                      {b.erro_aprovado == null
                        ? "—"
                        : porcento.format(b.erro_aprovado)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EstadoVazio
            titulo="Baselines indisponíveis"
            descricao="A comparação B0–B3 vem da avaliação (make eval)."
          />
        )}
      </Secao>
    </div>
  );
}
