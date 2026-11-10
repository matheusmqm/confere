import { notFound } from "next/navigation";
import { BadgeEstado, ESTADOS_DOCUMENTO } from "@/components/badge-estado";
import { CelulaDinheiro } from "@/components/celula-dinheiro";
import { MedidorConfianca } from "@/components/medidor-confianca";
import { SeloIA } from "@/components/selo-ia";

// Só em desenvolvimento: vitrine dos componentes (CF-121, CF-122).
export default function ComponentesPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-10 p-8">
      <h1 className="text-[28px] leading-9 font-semibold">Componentes</h1>

      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">BadgeEstado</h2>
        <ul className="flex flex-wrap gap-3">
          {ESTADOS_DOCUMENTO.map((estado) => (
            <li key={estado} className="flex flex-col items-start gap-1">
              <BadgeEstado estado={estado} />
              <span className="valor text-xs text-tinta-500">{estado}</span>
            </li>
          ))}
        </ul>
        <div className="flex items-center gap-3">
          <SeloIA />
          <span className="text-sm text-tinta-500">Selo da IA (roxo-ia)</span>
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">CelulaDinheiro</h2>
        <div className="grid w-72 gap-1 rounded-lg border border-border p-3">
          <CelulaDinheiro valor="12345.67" />
          <CelulaDinheiro valor="380" moeda="USD" />
          <CelulaDinheiro valor="230" diferenca />
          <CelulaDinheiro valor="-40" diferenca />
          <CelulaDinheiro valor="0" diferenca />
          <CelulaDinheiro valor={null} />
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">MedidorConfianca</h2>
        <div className="flex flex-col gap-2">
          <MedidorConfianca
            valor={0.42}
            breakdown={{ extracao: 0.9, processo: 0.42, codigo: 0.7 }}
          />
          <MedidorConfianca
            valor={0.78}
            breakdown={{ extracao: 0.95, processo: 0.78, codigo: 0.8 }}
          />
          <MedidorConfianca
            valor={0.97}
            breakdown={{ extracao: 0.99, processo: 0.97, codigo: 0.98 }}
          />
        </div>
      </section>
    </main>
  );
}
