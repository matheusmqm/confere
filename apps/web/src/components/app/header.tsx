"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ChevronDown, LogOut } from "lucide-react";
import Link from "next/link";
import {
  BotaoResetarDemo,
  BotaoSoltarLote,
  MODO_DEMO,
} from "@/components/app/demo";
import { Logo } from "@/components/app/logo";
import { ContadorDinheiro } from "@/components/contador-dinheiro";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api } from "@/lib/api/client";
import { useEu, usePainel } from "@/lib/api/hooks";

/** Cabeçalho de 56 px: logo, "R$ evitado" (atualiza a cada 10 s e pelo SSE), demo e usuário. */
export function Header() {
  const queryClient = useQueryClient();
  const { data: eu } = useEu();
  const { data: painel } = usePainel(
    { lote: MODO_DEMO ? "demo" : "todos" },
    { refetchInterval: 10_000 },
  );

  async function sair() {
    await api.POST("/auth/sair");
    queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== "eu" });
    await queryClient.invalidateQueries({ queryKey: ["eu"] });
  }

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-4 border-b border-border bg-background px-4 xl:px-6">
      <Link href="/" aria-label="Confere, ir para a Inbox" className="shrink-0">
        <Logo />
      </Link>

      <div className="ml-auto flex items-center gap-4">
        <div className="flex flex-col items-end leading-tight">
          <span className="rotulo text-tinta-500">R$ evitado</span>
          <ContadorDinheiro
            valor={painel?.kpis.rs_evitado.valor}
            className="valor text-base font-medium text-verde-texto"
          />
        </div>

        <BotaoSoltarLote />
        <BotaoResetarDemo />

        <DropdownMenu>
          <DropdownMenuTrigger
            render={<Button variant="ghost" aria-label="Menu do usuário" />}
          >
            <span className="max-w-32 truncate">
              {eu?.usuario.nome ?? "Conta"}
            </span>
            <ChevronDown aria-hidden />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-52">
            <DropdownMenuLabel className="flex flex-col">
              <span className="font-medium text-foreground">
                {eu?.usuario.nome}
              </span>
              <span className="text-xs text-tinta-500">
                {eu?.usuario.email}
              </span>
              <span className="text-xs text-tinta-500">{eu?.empresa.nome}</span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => void sair()}>
              <LogOut aria-hidden />
              Sair
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
