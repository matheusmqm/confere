"use client";

import { animate } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { formatarBRL, paraNumero } from "@/lib/dinheiro";

/**
 * Valor em reais com count-up ao mudar. O texto final vem sempre da string exata da API; só os
 * quadros intermediários da animação usam número (ninguém lê esses valores como dinheiro).
 */
export function ContadorDinheiro({
  valor,
  className,
}: {
  valor: string | undefined;
  className?: string;
}) {
  const [exibido, setExibido] = useState<number | null>(null);
  const ultimo = useRef(0);

  useEffect(() => {
    if (valor === undefined) return;
    const destino = paraNumero(valor);
    const controle = animate(ultimo.current, destino, {
      duration: 0.8,
      ease: "easeOut",
      onUpdate: (n) => setExibido(n),
      onComplete: () => setExibido(null), // volta ao texto exato
    });
    ultimo.current = destino;
    return () => controle.stop();
  }, [valor]);

  if (valor === undefined) return <span className={className}>—</span>;
  return (
    <span className={className} aria-live="polite">
      {exibido === null ? formatarBRL(valor) : formatarBRL(exibido.toFixed(2))}
    </span>
  );
}
