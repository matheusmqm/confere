"use client";

import { useQueryClient } from "@tanstack/react-query";
import { cn } from "cn";
import { Upload } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

const MAX_ARQUIVOS_POR_ENVIO = 50;

/** Envio multipart em lotes de 50. `POST /documentos` não está no OpenAPI ainda (CF-105). */
async function enviar(arquivos: File[]): Promise<void> {
  for (let i = 0; i < arquivos.length; i += MAX_ARQUIVOS_POR_ENVIO) {
    const corpo = new FormData();
    for (const arquivo of arquivos.slice(i, i + MAX_ARQUIVOS_POR_ENVIO)) {
      corpo.append("arquivos", arquivo);
    }
    const resposta = await fetch("/api/documentos", {
      method: "POST",
      body: corpo,
      credentials: "include",
    });
    if (!resposta.ok) {
      const erro = (await resposta.json().catch(() => null)) as {
        mensagem?: string;
      } | null;
      throw new Error(erro?.mensagem ?? "Não foi possível enviar os arquivos.");
    }
  }
}

/** Zona de arrastar e soltar (ou clicar) para enviar faturas. */
export function ZonaUpload({ className }: { className?: string }) {
  const queryClient = useQueryClient();
  const entrada = useRef<HTMLInputElement>(null);
  const [sobre, setSobre] = useState(false);
  const [enviando, setEnviando] = useState(false);

  async function processar(lista: FileList | null) {
    const arquivos = Array.from(lista ?? []);
    if (arquivos.length === 0) return;
    setEnviando(true);
    try {
      await enviar(arquivos);
      toast.success(
        arquivos.length === 1
          ? "1 arquivo enviado."
          : `${arquivos.length} arquivos enviados.`,
      );
      await queryClient.invalidateQueries({ queryKey: ["documentos"] });
    } catch (erro) {
      toast.error(erro instanceof Error ? erro.message : "Falha no envio.");
    } finally {
      setEnviando(false);
      if (entrada.current) entrada.current.value = "";
    }
  }

  return (
    <label
      onDragOver={(e) => {
        e.preventDefault();
        setSobre(true);
      }}
      onDragLeave={() => setSobre(false)}
      onDrop={(e) => {
        e.preventDefault();
        setSobre(false);
        void processar(e.dataTransfer.files);
      }}
      className={cn(
        "flex cursor-pointer items-center justify-center gap-3 rounded-lg border border-dashed px-4 py-5 text-sm transition-colors focus-within:ring-3 focus-within:ring-ring/50",
        sobre
          ? "border-cobalto bg-cobalto-fundo text-cobalto-texto"
          : "border-tinta-300 text-tinta-700 hover:bg-papel",
        className,
      )}
    >
      <Upload aria-hidden className="size-4" />
      <span>
        {enviando
          ? "Enviando…"
          : "Arraste faturas (PDF, imagem ou XML) aqui ou clique para escolher"}
      </span>
      <input
        ref={entrada}
        type="file"
        multiple
        accept=".pdf,.png,.jpg,.jpeg,.xml,application/pdf,image/png,image/jpeg,text/xml,application/xml"
        className="sr-only"
        onChange={(e) => void processar(e.target.files)}
      />
    </label>
  );
}
