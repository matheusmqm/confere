"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { BadgeEstado } from "@/components/badge-estado";
import { CelulaDinheiro } from "@/components/celula-dinheiro";
import { ProgressoPipeline } from "@/components/inbox/progresso-pipeline";
import type { components } from "@/lib/api/schema";
import { formatarBRL, sinalDe } from "@/lib/dinheiro";
import type { ProgressoDocumento } from "@/lib/stream";

type Resumo = components["schemas"]["DocumentoResumo"];

export function CartaoDocumento({
  documento,
  progresso,
}: {
  documento: Resumo;
  progresso?: ProgressoDocumento;
}) {
  const emRisco = sinalDe(documento.valor_brl_em_risco) > 0;
  return (
    <motion.li
      layout
      layoutId={documento.id}
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="list-none"
    >
      <Link
        href={`/documentos/${documento.id}`}
        className="flex flex-col gap-2 rounded-lg border border-border bg-card p-4 shadow-cartao outline-none hover:border-tinta-300 focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <div className="flex items-start justify-between gap-2">
          <span
            className="valor min-w-0 truncate text-sm font-medium"
            title={documento.nome_original}
          >
            {documento.nome_original}
          </span>
          <BadgeEstado estado={documento.status} />
        </div>
        <div className="flex items-end justify-between gap-2 text-[13px] text-tinta-500">
          <span className="min-w-0 truncate">
            {documento.fornecedor?.nome ?? "Fornecedor não identificado"}
          </span>
          {documento.total ? (
            <CelulaDinheiro
              valor={documento.total}
              moeda={documento.moeda ?? "BRL"}
              className="w-auto text-tinta-900"
            />
          ) : null}
        </div>
        {emRisco ? (
          <p className="rounded-sm bg-ambar-fundo px-2 py-1 text-[13px] font-medium text-ambar-texto">
            Em risco{" "}
            <span className="valor">
              {formatarBRL(documento.valor_brl_em_risco)}
            </span>
            {documento.n_excecoes > 1
              ? ` · ${documento.n_excecoes} exceções`
              : ""}
          </p>
        ) : null}
        <ProgressoPipeline
          etapas={progresso?.etapas}
          status={documento.status}
        />
      </Link>
    </motion.li>
  );
}
