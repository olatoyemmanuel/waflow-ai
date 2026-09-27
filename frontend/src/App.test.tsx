/**
 * WAFlow AI - Application Tests
 *
 * These tests verify the application's root rendering and
 * dashboard behavior without requiring a real backend server.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

describe("App", () => {
  beforeEach(() => {
    /**
     * Mock the backend health endpoint.
     *
     * This keeps the frontend test deterministic and means
     * the test does not depend on FastAPI being started.
     */
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            success: true,
            data: {
              status: "healthy",
            },
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
            },
          },
        ),
      ),
    );
  });

  afterEach(() => {
    /**
     * Restore the original global environment after every test.
     */
    vi.unstubAllGlobals();
  });

  it("renders the WAFlow AI dashboard", async () => {
    render(<App />);

    /**
     * Verify that the dashboard page is rendered.
     */
    expect(
      screen.getByRole("heading", {
        name: "Dashboard",
        level: 1,
      }),
    ).toBeInTheDocument();

    /**
     * Verify the WAFlow AI brand.
     */
    expect(
      screen.getByText("WAFlow AI"),
    ).toBeInTheDocument();

    /**
     * Verify primary navigation.
     */
    expect(
      screen.getByRole("link", {
        name: /Dashboard/,
      }),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("link", {
        name: /Inbox/,
      }),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("link", {
        name: /Customers/,
      }),
    ).toBeInTheDocument();

    /**
     * Wait for the mocked backend health request to complete.
     *
     * This confirms that the dashboard successfully consumes
     * the TanStack Query health integration.
     */
    await waitFor(() => {
      expect(
        screen.getByText(
          "FastAPI backend is healthy and responding correctly.",
        ),
      ).toBeInTheDocument();
    });
  });
});