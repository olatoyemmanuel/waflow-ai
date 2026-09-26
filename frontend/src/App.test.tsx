import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import App from "./App";

describe("App", () => {
  it("renders the WAFlow AI application", () => {
    render(<App />);

    expect(
      screen.getByRole("heading", { name: "WAFlow AI" }),
    ).toBeInTheDocument();

    expect(
      screen.getByText("WhatsApp AI automation platform."),
    ).toBeInTheDocument();
  });
});
