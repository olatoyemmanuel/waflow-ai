/**
 * WAFlow AI health API.
 *
 * This is the first real frontend-to-backend integration.
 */

import { apiGet } from "./client";
import type { HealthResponse } from "./types";

/**
 * Fetch the current API health status.
 *
 * The backend endpoint is:
 *
 * GET /health
 *
 * Because VITE_API_URL already contains /api/v1,
 * the health endpoint will eventually become:
 *
 * /api/v1/health
 *
 * However, our current FastAPI health endpoint lives at /health.
 *
 * Therefore we intentionally call the root API URL's health endpoint
 * for the current development foundation.
 */
export function getHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>("/health");
}