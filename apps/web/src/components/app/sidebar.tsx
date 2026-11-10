"use client";

import { cn } from "cn";
import {
  ChartColumn,
  FolderOpen,
  Inbox,
  SlidersHorizontal,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const ITENS: { href: string; rotulo: string; icone: LucideIcon }[] = [
  { href: "/", rotulo: "Inbox", icone: Inbox },
  { href: "/excecoes", rotulo: "Exceções", icone: TriangleAlert },
  { href: "/processos", rotulo: "Processos", icone: FolderOpen },
  { href: "/painel", rotulo: "Painel", icone: ChartColumn },
  { href: "/politica", rotulo: "Política", icone: SlidersHorizontal },
];

function ativo(href: string, caminho: string) {
  return href === "/"
    ? caminho === "/" || caminho.startsWith("/documentos")
    : caminho === href || caminho.startsWith(`${href}/`);
}

/** Barra lateral: 240 px; abaixo de 1280 px colapsa para só ícones. */
export function Sidebar() {
  const caminho = usePathname();
  return (
    <nav
      aria-label="Navegação principal"
      className="sticky top-14 flex h-[calc(100vh-3.5rem)] w-14 shrink-0 flex-col gap-1 border-r border-sidebar-border bg-sidebar p-2 xl:w-60 xl:p-3"
    >
      {ITENS.map(({ href, rotulo, icone: Icone }) => {
        const selecionado = ativo(href, caminho);
        return (
          <Link
            key={href}
            href={href}
            title={rotulo}
            aria-label={rotulo}
            aria-current={selecionado ? "page" : undefined}
            className={cn(
              "flex h-9 items-center justify-center gap-3 rounded-sm px-2 text-sm font-medium outline-none focus-visible:ring-3 focus-visible:ring-ring/50 xl:justify-start",
              selecionado
                ? "bg-verde-fundo text-verde-texto"
                : "text-tinta-700 hover:bg-tinta-100",
            )}
          >
            <Icone
              aria-hidden
              className={cn(
                "size-4 shrink-0",
                selecionado && "text-verde-conferido",
              )}
            />
            <span className="hidden xl:inline">{rotulo}</span>
          </Link>
        );
      })}
    </nav>
  );
}
