/**
 * Global test setup for WAFlow AI.
 *
 * This imports the Vitest-specific Jest DOM integration.
 * It extends Vitest's expect() assertions with DOM matchers such as:
 *
 * expect(element).toBeInTheDocument()
 *
 * Using the "/vitest" entrypoint is important because it also provides
 * the correct TypeScript type augmentation for Vitest.
 */
import "@testing-library/jest-dom/vitest";
