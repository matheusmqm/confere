import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 p-8 text-center">
      <h1 className="text-4xl font-semibold tracking-tight">Confere</h1>
      <p className="text-lg text-muted-foreground">Cada fatura, conferida.</p>
      <Button>Soltar lote de demo</Button>
    </main>
  );
}
