import { cn } from "cn";

/** Símbolo: quadrado arredondado com um tique que sai pelo canto. Placeholder até a CF-164. */
export function LogoSimbolo({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden
      className={cn("size-6", className)}
      fill="none"
      stroke="currentColor"
      strokeWidth={2.25}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M20 12.5V17a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3h7" />
      <path d="m8.5 11.5 3.5 3.5L21 6" />
    </svg>
  );
}

/** Lockup "confere": símbolo em verde-conferido + wordmark em Plex Sans 600. */
export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <LogoSimbolo className="text-verde-conferido" />
      <span className="text-lg leading-none font-semibold tracking-tight">
        confere
      </span>
      <span className="sr-only">Confere</span>
    </span>
  );
}
