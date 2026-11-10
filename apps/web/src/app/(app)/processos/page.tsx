import { EstadoVazio } from "@/components/estados";

export default function ProcessosPage() {
  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-[28px] leading-9 font-semibold tracking-tight">
        Processos
      </h1>
      <EstadoVazio
        titulo="Lista de processos em construção"
        descricao="Aqui ficam os processos de importação com o previsto × cobrado por código de custo."
      />
    </div>
  );
}
