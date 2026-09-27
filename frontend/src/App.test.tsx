/**
 * WAFlow AI - Application Tests
 *
 * These tests verify the behavior of the application's
 * root component and its initial routing.
 *
 * The test should focus on what the user can actually see
 * and interact with rather than implementation details.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import App from "./App";

describe("App", () => {
  it("renders the WAFlow AI dashboard", () => {
    /**
     * Render the complete application.
     *
     * App includes:
     * - application providers
     * - React Router
     * - application layout
     * - sidebar
     * - topbar
     * - dashboard
     */
    render(<App />);

    /**
     * The root route redirects to /dashboard.
     *
     * Therefore, the dashboard heading should be available
     * when the application starts.
     */
    expect(
      screen.getByRole("heading", {
        name: "Dashboard",
        level: 1,
      }),
    ).toBeInTheDocument();

    /**
     * Verify that the WAFlow AI brand is visible.
     */
    expect(
      screen.getByText("WAFlow AI"),
    ).toBeInTheDocument();

    /**
     * Verify that the primary navigation is available.
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
  });
});