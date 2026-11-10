"use client";

import { cn } from "cn";
import { useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";

// O worker precisa ser configurado NESTE módulo, onde os componentes do react-pdf são usados.
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

/** Caixa de uma linha: coordenadas normalizadas de 0 a 1 (esquerda/topo → direita/base). */
export interface Caixa {
  linhaId: string;
  pagina: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  estado: string;
}

interface Props {
  url: string;
  tipoArquivo: string | null;
  caixas: Caixa[];
  ativa: string | null;
  aoPassarMouse: (linhaId: string | null) => void;
  /** Incrementado quando a linha é escolhida na tabela: pede rolagem até a caixa. */
  rolarPara: { linhaId: string; n: number } | null;
}

const COR_POR_ESTADO: Record<string, string> = {
  ok: "border-verde-conferido bg-verde-fundo/60",
  acima_tolerancia: "border-ambar bg-ambar-fundo/60",
  abaixo_previsto: "border-ambar bg-ambar-fundo/60",
  cambio_divergente: "border-ambar bg-ambar-fundo/60",
  sem_provisao: "border-ambar bg-ambar-fundo/60",
  duplicada: "border-vermelho bg-vermelho-fundo/60",
  pendente: "border-cobalto bg-cobalto-fundo/60",
};

function Camada({
  caixas,
  pagina,
  ativa,
  aoPassarMouse,
  registrar,
}: {
  caixas: Caixa[];
  pagina: number;
  ativa: string | null;
  aoPassarMouse: Props["aoPassarMouse"];
  registrar: (id: string, el: HTMLElement | null) => void;
}) {
  return (
    <div className="pointer-events-none absolute inset-0">
      {caixas
        .filter((c) => c.pagina === pagina)
        .map((c) => (
          <button
            key={c.linhaId}
            type="button"
            ref={(el) => registrar(c.linhaId, el)}
            aria-label="Linha destacada no documento"
            onMouseEnter={() => aoPassarMouse(c.linhaId)}
            onMouseLeave={() => aoPassarMouse(null)}
            onFocus={() => aoPassarMouse(c.linhaId)}
            onBlur={() => aoPassarMouse(null)}
            style={{
              left: `${c.x0 * 100}%`,
              top: `${c.y0 * 100}%`,
              width: `${(c.x1 - c.x0) * 100}%`,
              height: `${(c.y1 - c.y0) * 100}%`,
            }}
            className={cn(
              "pointer-events-auto absolute rounded-[2px] border outline-none",
              COR_POR_ESTADO[c.estado] ?? COR_POR_ESTADO.pendente,
              ativa === c.linhaId &&
                "border-2 border-cobalto bg-cobalto-fundo/70",
            )}
          />
        ))}
    </div>
  );
}

/** PDF (react-pdf) ou imagem com caixas das linhas sobrepostas (CF-126). */
export default function Visualizador({
  url,
  tipoArquivo,
  caixas,
  ativa,
  aoPassarMouse,
  rolarPara,
}: Props) {
  const raiz = useRef<HTMLDivElement>(null);
  const caixaRefs = useRef<Record<string, HTMLElement | null>>({});
  const [largura, setLargura] = useState(560);
  const [paginas, setPaginas] = useState(0);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    const el = raiz.current;
    if (!el) return;
    const observador = new ResizeObserver(([entrada]) =>
      setLargura(Math.max(280, Math.floor(entrada.contentRect.width))),
    );
    observador.observe(el);
    return () => observador.disconnect();
  }, []);

  useEffect(() => {
    if (rolarPara) {
      caixaRefs.current[rolarPara.linhaId]?.scrollIntoView({
        block: "center",
        behavior: "smooth",
      });
    }
  }, [rolarPara]);

  const registrar = (id: string, el: HTMLElement | null) => {
    caixaRefs.current[id] = el;
  };

  if (erro) {
    return (
      <p role="alert" className="p-6 text-sm text-ambar-texto">
        Não foi possível abrir o arquivo.
      </p>
    );
  }

  return (
    <div ref={raiz} className="flex flex-col gap-3">
      {tipoArquivo === "pdf" ? (
        <Document
          file={url}
          loading={
            <p className="p-6 text-sm text-tinta-500">Carregando documento…</p>
          }
          error={
            <p className="p-6 text-sm text-ambar-texto">
              Não foi possível abrir o PDF.
            </p>
          }
          onLoadSuccess={({ numPages }) => setPaginas(numPages)}
          onLoadError={() => setErro(true)}
        >
          {Array.from({ length: paginas }, (_, i) => i + 1).map((pagina) => (
            <div
              key={pagina}
              className="relative mb-3 overflow-hidden rounded-lg border border-border"
            >
              <Page
                pageNumber={pagina}
                width={largura}
                renderTextLayer={false}
                renderAnnotationLayer={false}
              />
              <Camada
                caixas={caixas}
                pagina={pagina}
                ativa={ativa}
                aoPassarMouse={aoPassarMouse}
                registrar={registrar}
              />
            </div>
          ))}
        </Document>
      ) : (
        <div className="relative overflow-hidden rounded-lg border border-border">
          {/* eslint-disable-next-line @next/next/no-img-element -- URL assinada e temporária */}
          <img
            src={url}
            alt="Documento enviado"
            className="block w-full"
            onError={() => setErro(true)}
          />
          <Camada
            caixas={caixas}
            pagina={1}
            ativa={ativa}
            aoPassarMouse={aoPassarMouse}
            registrar={registrar}
          />
        </div>
      )}
    </div>
  );
}
