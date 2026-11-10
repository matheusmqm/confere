import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Home from "./page";

describe("Home", () => {
  it("mostra o título, o lema e o botão de demo", () => {
    render(<Home />);
    expect(
      screen.getByRole("heading", { name: "Confere" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Cada fatura, conferida.")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Soltar lote de demo" }),
    ).toBeInTheDocument();
  });
});
