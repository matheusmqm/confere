import { EstadoVazio } from "@/components/estados";

export default function PoliticaPage() {
  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-[28px] leading-9 font-semibold tracking-tight">
        Política
      </h1>
      <EstadoVazio
        titulo="Política de tolerâncias em construção"
        descricao="Aqui você define o quanto de diferença é aceitável antes de pedir revisão."
      />
    </div>
  );
}
