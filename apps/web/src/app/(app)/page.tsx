import { InboxPage } from "@/components/inbox/inbox-page";

// A Inbox depende da sessão e do SSE, que o cliente confirma depois: não há casca estática
// para validar navegação instantânea.
export const instant = false;

export default function Page() {
  return <InboxPage />;
}
