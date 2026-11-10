import { notFound } from "next/navigation";

// Só em desenvolvimento (CF-119): mostra cores, fontes e raios dos tokens.
const CORES: { nome: string; classe: string }[] = [
  { nome: "tinta-900", classe: "bg-tinta-900" },
  { nome: "tinta-700", classe: "bg-tinta-700" },
  { nome: "tinta-500", classe: "bg-tinta-500" },
  { nome: "tinta-300", classe: "bg-tinta-300" },
  { nome: "tinta-100", classe: "bg-tinta-100" },
  { nome: "papel-50", classe: "bg-papel-50" },
  { nome: "branco", classe: "bg-branco" },
  { nome: "verde-conferido", classe: "bg-verde-conferido" },
  { nome: "verde-texto", classe: "bg-verde-texto" },
  { nome: "verde-fundo", classe: "bg-verde-fundo" },
  { nome: "cobalto", classe: "bg-cobalto" },
  { nome: "cobalto-texto", classe: "bg-cobalto-texto" },
  { nome: "cobalto-fundo", classe: "bg-cobalto-fundo" },
  { nome: "ambar", classe: "bg-ambar" },
  { nome: "ambar-texto", classe: "bg-ambar-texto" },
  { nome: "ambar-fundo", classe: "bg-ambar-fundo" },
  { nome: "vermelho", classe: "bg-vermelho" },
  { nome: "vermelho-texto", classe: "bg-vermelho-texto" },
  { nome: "vermelho-fundo", classe: "bg-vermelho-fundo" },
  { nome: "roxo-ia", classe: "bg-roxo-ia" },
  { nome: "roxo-texto", classe: "bg-roxo-texto" },
  { nome: "roxo-fundo", classe: "bg-roxo-fundo" },
];

const ESCALA_TINTA: { nome: string; classe: string }[] = [
  { nome: "tinta/80", classe: "bg-tinta/80" },
  { nome: "tinta/60", classe: "bg-tinta/60" },
  { nome: "tinta/40", classe: "bg-tinta/40" },
  { nome: "tinta/20", classe: "bg-tinta/20" },
  { nome: "tinta/10", classe: "bg-tinta/10" },
];

const RAIOS: { nome: string; classe: string }[] = [
  { nome: "sm · 6 px", classe: "rounded-sm" },
  { nome: "md · 8 px", classe: "rounded-md" },
  { nome: "lg · 10 px", classe: "rounded-lg" },
];

function Amostras({ itens }: { itens: { nome: string; classe: string }[] }) {
  return (
    <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
      {itens.map((item) => (
        <li key={item.nome} className="flex flex-col gap-1.5">
          <span
            className={`h-12 rounded-md border border-border ${item.classe}`}
          />
          <span className="valor text-xs text-tinta-700">{item.nome}</span>
        </li>
      ))}
    </ul>
  );
}

export default function TokensPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-10 p-8">
      <header>
        <h1 className="text-[28px] leading-9 font-semibold">
          Tokens de design
        </h1>
        <p className="text-sm text-tinta-500">
          Página de desenvolvimento. Troque o tema com a classe{" "}
          <code>dark</code> em <code>&lt;html&gt;</code>.
        </p>
      </header>

      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">Cores</h2>
        <Amostras itens={CORES} />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">Escala de tinta (opacidade)</h2>
        <Amostras itens={ESCALA_TINTA} />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">Fontes</h2>
        <p className="text-[28px] leading-9 font-semibold">
          IBM Plex Sans 600 · Inbox
        </p>
        <p className="text-[15px] leading-6">
          IBM Plex Sans 400 · A taxa foi cobrada acima da tabela vigente.
        </p>
        <p className="rotulo text-tinta-500">Valor em risco</p>
        <p className="valor text-[32px] leading-10 font-medium tracking-tight">
          R$ 48.372,15
        </p>
        <p className="valor text-sm">
          IBM Plex Mono 400 · MSCU1234567 · IMP-2026-0142
        </p>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">Raios e sombras</h2>
        <ul className="flex flex-wrap gap-4">
          {RAIOS.map((r) => (
            <li key={r.nome} className="flex flex-col items-center gap-1.5">
              <span
                className={`size-16 border border-tinta-300 bg-papel-50 ${r.classe}`}
              />
              <span className="valor text-xs">{r.nome}</span>
            </li>
          ))}
          <li className="flex flex-col items-center gap-1.5">
            <span className="size-16 rounded-lg border border-border bg-card shadow-cartao" />
            <span className="valor text-xs">sombra-cartao</span>
          </li>
          <li className="flex flex-col items-center gap-1.5">
            <span className="size-16 rounded-lg border border-border bg-popover shadow-popover" />
            <span className="valor text-xs">sombra-popover</span>
          </li>
        </ul>
      </section>
    </main>
  );
}
