import { AppShell } from "@/components/app/app-shell";

// Todo o grupo (app) depende da sessão, que o cliente confirma em /auth/eu: não há casca estática
// para validar navegação instantânea.
export const instant = false;

export default function AppLayout({ children }: LayoutProps<"/">) {
  return <AppShell>{children}</AppShell>;
}
