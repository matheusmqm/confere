"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

/** Estilo dos números dos eixos: Plex Mono 11 px em tinta-500 (identidade). */
const TICK = {
  fontFamily: "var(--font-mono)",
  fontSize: 11,
  fill: "var(--tinta-500)",
};
const NOME_EIXO = { fontSize: 12, fill: "var(--tinta-500)" };
const compacto = new Intl.NumberFormat("pt-BR", {
  notation: "compact",
  maximumFractionDigits: 1,
});
const porcento = new Intl.NumberFormat("pt-BR", {
  style: "percent",
  maximumFractionDigits: 1,
});
const reais = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

/** Sparkline de área, sem eixos (o valor exato aparece nos cartões e na tabela). */
export function Sparkline({
  dados,
  rotulo,
}: {
  dados: { x: string; y: number }[];
  rotulo: string;
}) {
  return (
    <div role="img" aria-label={rotulo} className="h-12 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={dados}
          margin={{ top: 2, right: 0, bottom: 0, left: 0 }}
        >
          <Area
            type="monotone"
            dataKey="y"
            stroke="var(--cobalto)"
            strokeWidth={1.5}
            fill="var(--cobalto-fundo)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export interface PontoCurva {
  alpha: number;
  cobertura: number;
  risco: number;
}

/** Curva risco × cobertura com o ponto da política em destaque. */
export function CurvaRiscoCobertura({
  curva,
  atual,
}: {
  curva: PontoCurva[];
  atual: { cobertura: number; risco: number };
}) {
  const dados = [...curva].sort((a, b) => a.cobertura - b.cobertura);
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={dados}
          margin={{ top: 8, right: 16, bottom: 24, left: 8 }}
        >
          <CartesianGrid stroke="var(--tinta-100)" vertical={false} />
          <XAxis
            dataKey="cobertura"
            type="number"
            domain={[0, 1]}
            tickFormatter={(v: number) => porcento.format(v)}
            tick={TICK}
            stroke="var(--tinta-300)"
            label={{
              value: "Cobertura (aprovado sem toque)",
              position: "insideBottom",
              offset: -14,
              ...NOME_EIXO,
            }}
          />
          <YAxis
            type="number"
            tickFormatter={(v: number) => porcento.format(v)}
            tick={TICK}
            stroke="var(--tinta-300)"
            width={56}
            label={{
              value: "Risco",
              angle: -90,
              position: "insideLeft",
              ...NOME_EIXO,
            }}
          />
          <Tooltip
            formatter={(v) => porcento.format(Number(v))}
            labelFormatter={(v) => `Cobertura ${porcento.format(Number(v))}`}
          />
          <Line
            type="monotone"
            dataKey="risco"
            name="Risco"
            stroke="var(--cobalto)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <ReferenceDot
            x={atual.cobertura}
            y={atual.risco}
            r={6}
            fill="var(--ambar)"
            stroke="var(--tinta-900)"
            strokeWidth={1.5}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Barras horizontais de R$ por categoria (ranking de fornecedores, tipos de exceção). */
export function BarrasHorizontais({
  dados,
  rotulo,
  nomeValor,
}: {
  dados: { nome: string; valor: number }[];
  rotulo: string;
  nomeValor: string;
}) {
  return (
    <div
      role="img"
      aria-label={rotulo}
      style={{ height: Math.max(120, dados.length * 36 + 32) }}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={dados}
          layout="vertical"
          margin={{ top: 4, right: 16, bottom: 20, left: 8 }}
        >
          <CartesianGrid stroke="var(--tinta-100)" horizontal={false} />
          <XAxis
            type="number"
            tickFormatter={(v: number) => compacto.format(v)}
            tick={TICK}
            stroke="var(--tinta-300)"
            label={{
              value: nomeValor,
              position: "insideBottom",
              offset: -12,
              ...NOME_EIXO,
            }}
          />
          <YAxis
            type="category"
            dataKey="nome"
            width={150}
            tick={{ ...TICK, fontFamily: "var(--font-sans)", fontSize: 12 }}
            stroke="var(--tinta-300)"
          />
          <Tooltip formatter={(v) => reais.format(Number(v))} />
          <Bar
            dataKey="valor"
            name={nomeValor}
            fill="var(--cobalto)"
            radius={[0, 4, 4, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
