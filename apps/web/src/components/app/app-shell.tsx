"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Header } from "@/components/app/header";
import { Logo } from "@/components/app/logo";
import { Sidebar } from "@/components/app/sidebar";
import { EstadoErro } from "@/components/estados";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError, desembrulhar } from "@/lib/api/client";
import { useEu } from "@/lib/api/hooks";
import { useStream } from "@/lib/stream";

function TelaEntrada() {
  const queryClient = useQueryClient();
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function entrar() {
    setCarregando(true);
    setErro(null);
    try {
      desembrulhar(await api.POST("/auth/demo"));
      await queryClient.invalidateQueries({ queryKey: ["eu"] });
    } catch (e) {
      setErro(
        e instanceof Error ? e.message : "Não foi possível entrar na demo.",
      );
    } finally {
      setCarregando(false);
    }
  }

  return (
    <main className="flex min-h-screen flex-1 items-center justify-center bg-papel p-6">
      <section className="flex w-full max-w-sm flex-col items-center gap-5 rounded-lg border border-border bg-card p-8 text-center">
        <Logo />
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-semibold">Cada fatura, conferida.</h1>
          <p className="text-sm text-tinta-500">
            Entre na demonstração para ver o Confere conferindo faturas de
            fornecedores.
          </p>
        </div>
        <Button
          size="lg"
          className="w-full"
          onClick={() => void entrar()}
          disabled={carregando}
        >
          {carregando ? "Entrando…" : "Entrar na demo"}
        </Button>
        {erro ? (
          <p role="alert" className="text-sm text-vermelho-texto">
            {erro}
          </p>
        ) : null}
      </section>
    </main>
  );
}

/** Navegação + cabeçalho. Sem sessão (401 em `/auth/eu`) mostra a tela de entrada. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const eu = useEu();
  const logado = eu.isSuccess;
  // O SSE é do shell (não da Inbox): o contador e as telas reagem em qualquer rota.
  useStream(logado);

  if (eu.isPending) {
    return (
      <div className="flex min-h-screen flex-col gap-4 p-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (eu.error instanceof ApiError && eu.error.status === 401)
    return <TelaEntrada />;
  if (eu.isError) {
    return (
      <div className="p-8">
        <EstadoErro
          mensagem={eu.error.message}
          aoTentarDeNovo={() => void eu.refetch()}
        />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <div className="flex flex-1">
        <Sidebar />
        <main className="min-w-0 flex-1 p-6 xl:p-8">{children}</main>
      </div>
    </div>
  );
}
