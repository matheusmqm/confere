import createClient from "openapi-fetch";
import type { paths } from "./schema";

/**
 * Cliente tipado da API (CF-123). `baseUrl: "/api"` passa pelo rewrite do Next.js, então o cookie
 * de sessão é same-site. Os tipos vêm de `schema.d.ts`, gerado por `make gen-api`.
 */
export const api = createClient<paths>({
  baseUrl: "/api",
  credentials: "include",
});

/** Erro de negócio da API: corpo `{"erro": codigo, "mensagem": texto em pt-BR}`. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly codigo: string,
    mensagem: string,
  ) {
    super(mensagem);
    this.name = "ApiError";
  }
}

interface RespostaApi<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** Devolve `data` ou lança `ApiError` com a mensagem em pt-BR da API. */
export function desembrulhar<T>({ data, error, response }: RespostaApi<T>): T {
  if (!response.ok || error !== undefined) {
    const corpo = (error ?? {}) as { erro?: string; mensagem?: string };
    throw new ApiError(
      response.status,
      corpo.erro ?? "erro_http",
      corpo.mensagem ?? "Não foi possível concluir a operação.",
    );
  }
  return data as T;
}
